from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Any, Callable
from urllib.parse import parse_qs, unquote, urlsplit

from .daily_radar_snapshot import InvalidRadarSnapshot, read_daily_radar_snapshot
from .event_analysis import (
    InvalidEventAnalysis,
    event_analysis_path,
    generate_event_analysis,
    read_event_analysis,
    write_failed_event_analysis,
)
from .event_catalog import InvalidEventCatalog, event_catalog_path, read_event_catalog
from .llm.chat_completions_client import ChatCompletionsClient
from .llm.usage import LLMUsageSession
from .workflow import run_daily_radar_workflow
from .watchlist_store import WatchlistConflict, WatchlistStore, WatchlistSymbolNotFound

_EVENT_ANALYSIS_RE = re.compile(r"^/api/radars/latest/events/(evt_[0-9a-f]{16})/analysis$")
_EVENT_REPORT_RE = re.compile(r"^/api/radars/latest/events/(evt_[0-9a-f]{16})/report$")


class EventNotFound(LookupError):
    pass


class CatalogUnavailable(RuntimeError):
    pass


class AnalysisInProgress(RuntimeError):
    pass


class AnalysisNotApplicable(RuntimeError):
    pass


class RadarGenerationInProgress(RuntimeError):
    pass


@dataclass(frozen=True)
class AnalysisConfig:
    watchlist_path: str | Path = "data/watchlist.example.csv"
    a_share_universe_path: str | Path = "data/a_share_universe.csv"
    evidence_cache_path: str | Path = "data/akshare_cache"
    market_cache_path: str | Path = "data/baostock_cache"


@dataclass(frozen=True)
class GenerationConfig:
    snapshot_path: str | Path
    event_cache_path: str | Path = "data/event_cache/ths"
    watchlist_path: str | Path = "data/watchlist.example.csv"
    a_share_universe_path: str | Path = "data/a_share_universe.csv"
    evidence_cache_path: str | Path = "data/akshare_cache"
    market_cache_path: str | Path = "data/baostock_cache"

    @property
    def markdown_path(self) -> Path:
        return Path(self.snapshot_path).with_suffix(".md")


class RadarGenerationService:
    def __init__(
        self,
        config: GenerationConfig,
        generate: Callable[[GenerationConfig], dict[str, Any]] | None = None,
    ) -> None:
        self.config = config
        self._generate = generate or _generate_daily_radar
        self._lock = Lock()

    def run(self) -> dict[str, Any]:
        if not self._lock.acquire(blocking=False):
            raise RadarGenerationInProgress("daily radar generation is already running")
        try:
            return self._generate(self.config)
        finally:
            self._lock.release()


def _generate_daily_radar(config: GenerationConfig) -> dict[str, Any]:
    client = ChatCompletionsClient(usage_session=LLMUsageSession("daily_radar_web"))
    run = run_daily_radar_workflow(
        output_path=config.markdown_path,
        event_cache_path=config.event_cache_path,
        watchlist_path=config.watchlist_path,
        a_share_universe_path=config.a_share_universe_path,
        evidence_cache_path=config.evidence_cache_path,
        market_cache_path=config.market_cache_path,
        refresh_evidence=False,
        json_output_path=config.snapshot_path,
        llm_client=client,
    )
    if not run.steps or run.steps[-1].status == "error":
        message = run.steps[-1].summary if run.steps else "daily radar generation failed"
        raise RuntimeError(message)
    snapshot = read_daily_radar_snapshot(config.snapshot_path)
    return {"status": "succeeded", "run_id": snapshot["run"]["id"]}


class EventAnalysisService:
    def __init__(self, snapshot_path: str | Path, config: AnalysisConfig) -> None:
        self.snapshot_path = Path(snapshot_path)
        self.config = config
        self._lock = Lock()
        self._active: tuple[str, str, str] | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="event-analysis")

    def enrich_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        run_id = snapshot["run"]["id"]
        with self._lock:
            active = self._active
        for event in snapshot["all_events"]:
            if event.get("analysis_status") == "not_applicable":
                continue
            if active and active[:2] == (run_id, event["id"]):
                event["analysis_status"] = active[2]
                continue
            path = event_analysis_path(self.snapshot_path, run_id, event["id"])
            if path.is_file():
                try:
                    analysis = read_event_analysis(path, run_id=run_id, event_id=event["id"])
                except InvalidEventAnalysis:
                    event["analysis_status"] = "failed"
                else:
                    event["analysis_status"] = analysis["status"]
        return snapshot

    def start(self, event_id: str) -> tuple[HTTPStatus, dict[str, Any]]:
        snapshot, event, rank = self._load_event(event_id)
        run_id = snapshot["run"]["id"]
        output_path = event_analysis_path(self.snapshot_path, run_id, event_id)
        try:
            existing = read_event_analysis(output_path, run_id=run_id, event_id=event_id)
        except FileNotFoundError:
            existing = None
        if existing and existing["status"] == "succeeded":
            return HTTPStatus.OK, existing

        with self._lock:
            if self._active is not None:
                if self._active[:2] == (run_id, event_id):
                    return HTTPStatus.ACCEPTED, self._status_payload(*self._active)
                raise AnalysisInProgress("another event analysis is already running")
            self._active = (run_id, event_id, "queued")
            self._executor.submit(self._run, event, run_id, event_id, rank, output_path)
            return HTTPStatus.ACCEPTED, self._status_payload(run_id, event_id, "queued")

    def get(self, event_id: str) -> tuple[HTTPStatus, dict[str, Any]]:
        snapshot, _ = self._load_summary(event_id)
        run_id = snapshot["run"]["id"]
        with self._lock:
            active = self._active
        if active and active[:2] == (run_id, event_id):
            return HTTPStatus.ACCEPTED, self._status_payload(*active)
        path = event_analysis_path(self.snapshot_path, run_id, event_id)
        return HTTPStatus.OK, read_event_analysis(path, run_id=run_id, event_id=event_id)

    def _load_event(self, event_id: str) -> tuple[dict[str, Any], Any, int]:
        snapshot, summary = self._load_summary(event_id)
        if summary.get("exclusion_reason") == "pure_stock_price_update":
            raise AnalysisNotApplicable("pure stock price updates are not research events")
        run_id = snapshot["run"]["event_catalog_id"]
        path = event_catalog_path(self.snapshot_path, run_id)
        try:
            events = read_event_catalog(path, run_id)
        except (FileNotFoundError, InvalidEventCatalog) as exc:
            raise CatalogUnavailable(str(exc) or "event catalog unavailable") from exc
        event = events.get(event_id)
        if event is None:
            raise EventNotFound("market event not found in catalog")
        return snapshot, event, summary["rank"]

    def _load_summary(self, event_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        snapshot = read_daily_radar_snapshot(self.snapshot_path)
        summary = next(
            (item for item in snapshot["all_events"] if item["id"] == event_id),
            None,
        )
        if summary is None:
            raise EventNotFound("market event not found in latest radar")
        return snapshot, summary

    def _run(self, event: Any, run_id: str, event_id: str, rank: int, path: Path) -> None:
        with self._lock:
            self._active = (run_id, event_id, "running")
        try:
            generate_event_analysis(
                event,
                run_id=run_id,
                event_id=event_id,
                rank=rank,
                output_path=path,
                watchlist_path=self.config.watchlist_path,
                a_share_universe_path=self.config.a_share_universe_path,
                evidence_cache_path=self.config.evidence_cache_path,
                market_cache_path=self.config.market_cache_path,
            )
        except Exception as exc:
            write_failed_event_analysis(
                run_id=run_id,
                event_id=event_id,
                error=str(exc),
                output_path=path,
            )
        finally:
            with self._lock:
                self._active = None

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    @staticmethod
    def _status_payload(run_id: str, event_id: str, status: str) -> dict[str, Any]:
        return {"run_id": run_id, "event_id": event_id, "status": status}


class RadarServer(ThreadingHTTPServer):
    analysis_service: EventAnalysisService
    generation_service: RadarGenerationService
    watchlist_store: WatchlistStore

    def server_close(self) -> None:
        if hasattr(self, "analysis_service"):
            self.analysis_service.close()
        super().server_close()


class RadarRequestHandler(BaseHTTPRequestHandler):
    def __init__(
        self,
        *args: Any,
        snapshot_path: str | Path,
        analysis_service: EventAnalysisService,
        generation_service: RadarGenerationService,
        watchlist_store: WatchlistStore,
        **kwargs: Any,
    ) -> None:
        self.snapshot_path = Path(snapshot_path)
        self.analysis_service = analysis_service
        self.generation_service = generation_service
        self.watchlist_store = watchlist_store
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/api/watchlist":
            self._write_json(HTTPStatus.OK, {"items": [_watchlist_payload(item) for item in self.watchlist_store.list()]})
            return
        if parsed.path == "/api/stocks/search":
            query = parse_qs(parsed.query).get("q", [""])[0]
            self._write_json(HTTPStatus.OK, {"items": [_company_payload(item) for item in self.watchlist_store.search(query)]})
            return
        if self.path == "/api/health":
            self._write_json(
                HTTPStatus.OK,
                {"status": "ok", "radar_available": self.snapshot_path.is_file()},
            )
            return
        if self.path == "/api/radars/latest":
            self._write_latest_radar()
            return
        analysis_match = _EVENT_ANALYSIS_RE.match(self.path)
        if analysis_match:
            self._write_analysis(analysis_match.group(1))
            return
        report_match = _EVENT_REPORT_RE.match(self.path)
        if report_match:
            self._write_report(report_match.group(1))
            return
        self._write_not_found()

    def do_POST(self) -> None:
        if self.path == "/api/watchlist":
            self._add_watchlist_item()
            return
        if self.path == "/api/radars/generate":
            self._generate_radar()
            return
        match = _EVENT_ANALYSIS_RE.match(self.path)
        if not match:
            self._write_not_found()
            return
        try:
            status, payload = self.analysis_service.start(match.group(1))
        except Exception as exc:
            self._write_service_error(exc)
        else:
            self._write_json(status, payload)

    def do_DELETE(self) -> None:
        prefix = "/api/watchlist/"
        if not self.path.startswith(prefix):
            self._write_not_found()
            return
        try:
            item = self.watchlist_store.remove(unquote(self.path[len(prefix):]))
        except Exception as exc:
            self._write_service_error(exc)
        else:
            self._write_json(HTTPStatus.OK, _watchlist_payload(item))

    def _add_watchlist_item(self) -> None:
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 4096:
                raise ValueError("invalid request body")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            symbol = payload.get("symbol") if isinstance(payload, dict) else None
            if not isinstance(symbol, str) or not symbol.strip():
                raise ValueError("symbol is required")
            item = self.watchlist_store.add(symbol)
        except Exception as exc:
            self._write_service_error(exc)
        else:
            self._write_json(HTTPStatus.CREATED, _watchlist_payload(item))

    def _generate_radar(self) -> None:
        try:
            payload = self.generation_service.run()
        except Exception as exc:
            self._write_service_error(exc)
        else:
            self._write_json(HTTPStatus.OK, payload)

    def _write_latest_radar(self) -> None:
        try:
            snapshot = read_daily_radar_snapshot(self.snapshot_path)
        except FileNotFoundError:
            self._write_json(
                HTTPStatus.NOT_FOUND,
                {"error": "radar_not_found", "message": "Daily radar snapshot not found"},
            )
        except InvalidRadarSnapshot as exc:
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": "invalid_radar_snapshot", "message": str(exc)},
            )
        else:
            self._write_json(HTTPStatus.OK, self.analysis_service.enrich_snapshot(snapshot))

    def _write_analysis(self, event_id: str) -> None:
        try:
            status, payload = self.analysis_service.get(event_id)
        except FileNotFoundError:
            self._write_json(
                HTTPStatus.NOT_FOUND,
                {"error": "analysis_not_found", "message": "Event analysis not found"},
            )
        except Exception as exc:
            self._write_service_error(exc)
        else:
            self._write_json(status, payload)

    def _write_report(self, event_id: str) -> None:
        try:
            _, payload = self.analysis_service.get(event_id)
        except Exception as exc:
            self._write_service_error(exc)
            return
        if payload.get("status") != "succeeded":
            self._write_json(
                HTTPStatus.CONFLICT,
                {"error": "analysis_not_succeeded", "message": "Event analysis is not ready"},
            )
            return
        self._write_body(HTTPStatus.OK, payload["markdown"].encode("utf-8"), "text/markdown; charset=utf-8")

    def _write_service_error(self, exc: Exception) -> None:
        if isinstance(exc, EventNotFound):
            status, code = HTTPStatus.NOT_FOUND, "event_not_found"
        elif isinstance(exc, CatalogUnavailable):
            status, code = HTTPStatus.UNPROCESSABLE_ENTITY, "event_catalog_unavailable"
        elif isinstance(exc, AnalysisInProgress):
            status, code = HTTPStatus.CONFLICT, "analysis_in_progress"
        elif isinstance(exc, AnalysisNotApplicable):
            status, code = HTTPStatus.UNPROCESSABLE_ENTITY, "analysis_not_applicable"
        elif isinstance(exc, RadarGenerationInProgress):
            status, code = HTTPStatus.CONFLICT, "radar_generation_in_progress"
        elif isinstance(exc, WatchlistConflict):
            status, code = HTTPStatus.CONFLICT, "watchlist_conflict"
        elif isinstance(exc, WatchlistSymbolNotFound):
            status, code = HTTPStatus.NOT_FOUND, "watchlist_symbol_not_found"
        elif isinstance(exc, (ValueError, json.JSONDecodeError, UnicodeDecodeError)):
            status, code = HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_request"
        elif isinstance(exc, InvalidRadarSnapshot):
            status, code = HTTPStatus.INTERNAL_SERVER_ERROR, "invalid_radar_snapshot"
        elif isinstance(exc, InvalidEventAnalysis):
            status, code = HTTPStatus.INTERNAL_SERVER_ERROR, "invalid_event_analysis"
        elif isinstance(exc, FileNotFoundError):
            status, code = HTTPStatus.NOT_FOUND, "analysis_not_found"
        else:
            status, code = HTTPStatus.INTERNAL_SERVER_ERROR, "analysis_failed"
        self._write_json(status, {"error": code, "message": str(exc)})

    def _write_not_found(self) -> None:
        self._write_json(
            HTTPStatus.NOT_FOUND,
            {"error": "endpoint_not_found", "message": "API endpoint not found"},
        )

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self._write_body(
            status,
            json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _write_body(self, status: HTTPStatus, encoded: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        return


def create_server(
    host: str,
    port: int,
    snapshot_path: str | Path,
    *,
    analysis_config: AnalysisConfig | None = None,
) -> RadarServer:
    config = analysis_config or AnalysisConfig()
    service = EventAnalysisService(snapshot_path, config)
    generation_service = RadarGenerationService(
        GenerationConfig(
            snapshot_path=snapshot_path,
            watchlist_path=config.watchlist_path,
            a_share_universe_path=config.a_share_universe_path,
            evidence_cache_path=config.evidence_cache_path,
            market_cache_path=config.market_cache_path,
        )
    )
    watchlist_store = WatchlistStore(config.watchlist_path, config.a_share_universe_path)
    handler = partial(
        RadarRequestHandler,
        snapshot_path=snapshot_path,
        analysis_service=service,
        generation_service=generation_service,
        watchlist_store=watchlist_store,
    )
    server = RadarServer((host, port), handler)
    server.analysis_service = service
    server.generation_service = generation_service
    server.watchlist_store = watchlist_store
    return server


def _watchlist_payload(item: Any) -> dict[str, Any]:
    return {
        "symbol": item.symbol,
        "name": item.name,
        "market": item.market,
        "themes": list(item.themes),
        "thesis": item.thesis,
        "risks": item.risks,
        "industry": item.industry,
    }


def _company_payload(item: Any) -> dict[str, Any]:
    return {
        "symbol": item.symbol,
        "name": item.name,
        "market": item.market,
        "industry": item.industry,
        "themes": list(item.themes),
    }


def serve(
    host: str,
    port: int,
    snapshot_path: str | Path,
    *,
    analysis_config: AnalysisConfig | None = None,
) -> None:
    server = create_server(host, port, snapshot_path, analysis_config=analysis_config)
    print(f"serving latest radar on http://{host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
