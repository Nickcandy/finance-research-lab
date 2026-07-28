from __future__ import annotations

import csv
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from threading import Lock

from .models import AShareCompany, WatchlistItem
from .news_trace import load_a_share_universe, load_watchlist


class WatchlistConflict(ValueError):
    pass


class WatchlistSymbolNotFound(LookupError):
    pass


class WatchlistStore:
    def __init__(self, watchlist_path: str | Path, universe_path: str | Path) -> None:
        self.watchlist_path = Path(watchlist_path)
        self.universe_path = Path(universe_path)
        self._lock = Lock()

    def list(self) -> list[WatchlistItem]:
        with self._lock:
            return load_watchlist(self.watchlist_path)

    def search(self, query: str, *, limit: int = 20) -> list[AShareCompany]:
        term = query.strip().casefold()
        if not term:
            return []
        matches = [
            company
            for company in load_a_share_universe(self.universe_path)
            if term in company.symbol.casefold() or term in company.name.casefold()
        ]
        return matches[:limit]

    def add(self, symbol: str) -> WatchlistItem:
        normalized = symbol.strip().upper()
        with self._lock:
            items = load_watchlist(self.watchlist_path)
            if any(item.symbol == normalized for item in items):
                raise WatchlistConflict(f"{normalized} is already in watchlist")
            company = next(
                (
                    value
                    for value in load_a_share_universe(self.universe_path)
                    if value.symbol == normalized
                ),
                None,
            )
            if company is None:
                raise WatchlistSymbolNotFound(f"A-share symbol not found: {normalized}")
            item = WatchlistItem(
                symbol=company.symbol,
                name=company.name,
                market=company.market,
                themes=company.themes,
                industry=company.industry,
            )
            self._write((*items, item))
            return item

    def remove(self, symbol: str) -> WatchlistItem:
        normalized = symbol.strip().upper()
        with self._lock:
            items = load_watchlist(self.watchlist_path)
            existing = next((item for item in items if item.symbol == normalized), None)
            if existing is None:
                raise WatchlistSymbolNotFound(f"watchlist symbol not found: {normalized}")
            self._write(tuple(item for item in items if item.symbol != normalized))
            return existing

    def _write(self, items: tuple[WatchlistItem, ...]) -> None:
        self.watchlist_path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self.watchlist_path.name}.",
            suffix=".tmp",
            dir=self.watchlist_path.parent,
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=("symbol", "name", "market", "themes", "thesis", "risks", "industry"),
                    lineterminator="\n",
                )
                writer.writeheader()
                for item in items:
                    row = asdict(item)
                    row["themes"] = ";".join(item.themes)
                    writer.writerow(row)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.watchlist_path)
        finally:
            temporary.unlink(missing_ok=True)
