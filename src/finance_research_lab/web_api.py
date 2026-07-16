from __future__ import annotations

import json
from functools import partial
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .daily_radar_snapshot import InvalidRadarSnapshot, read_daily_radar_snapshot


class RadarRequestHandler(BaseHTTPRequestHandler):
    def __init__(self, *args: Any, snapshot_path: str | Path, **kwargs: Any) -> None:
        self.snapshot_path = Path(snapshot_path)
        super().__init__(*args, **kwargs)

    def do_GET(self) -> None:
        if self.path == "/api/health":
            self._write_json(
                HTTPStatus.OK,
                {"status": "ok", "radar_available": self.snapshot_path.is_file()},
            )
            return
        if self.path == "/api/radars/latest":
            self._write_latest_radar()
            return
        self._write_json(
            HTTPStatus.NOT_FOUND,
            {"error": "endpoint_not_found", "message": "API endpoint not found"},
        )

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
            self._write_json(HTTPStatus.OK, snapshot)

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: Any) -> None:
        return


def create_server(host: str, port: int, snapshot_path: str | Path) -> ThreadingHTTPServer:
    handler = partial(RadarRequestHandler, snapshot_path=snapshot_path)
    return ThreadingHTTPServer((host, port), handler)


def serve(host: str, port: int, snapshot_path: str | Path) -> None:
    server = create_server(host, port, snapshot_path)
    print(f"serving latest radar on http://{host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
