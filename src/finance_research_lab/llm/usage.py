from __future__ import annotations

import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_LLM_USAGE_STORE = "data/agent_runs.sqlite3"
NANO_CNY = Decimal("1000000000")


@dataclass(frozen=True)
class _ModelPrice:
    cache_hit_input: Decimal
    cache_miss_input: Decimal
    output: Decimal


# CNY per one million tokens, checked against DeepSeek pricing on 2026-07-19.
DEEPSEEK_PRICES = {
    "deepseek-v4-flash": _ModelPrice(Decimal("0.02"), Decimal("1"), Decimal("2")),
    "deepseek-v4-pro": _ModelPrice(Decimal("0.025"), Decimal("3"), Decimal("6")),
}


@dataclass(frozen=True)
class LLMUsageSummary:
    run_call_count: int
    run_input_tokens: int
    run_output_tokens: int
    run_cost_nano_cny: int
    run_unpriced_calls: int
    run_estimated_calls: int
    run_failed_calls: int
    daily_call_count: int
    daily_input_tokens: int
    daily_output_tokens: int
    daily_cost_nano_cny: int
    daily_unpriced_calls: int
    warnings: tuple[str, ...] = ()

    @property
    def run_cost_cny(self) -> Decimal:
        return Decimal(self.run_cost_nano_cny) / NANO_CNY

    @property
    def daily_cost_cny(self) -> Decimal:
        return Decimal(self.daily_cost_nano_cny) / NANO_CNY

    @property
    def complete(self) -> bool:
        return (
            not self.warnings
            and self.run_unpriced_calls == 0
            and self.daily_unpriced_calls == 0
        )


class LLMUsageSession:
    """Persist and summarize LLM usage for one workflow run."""

    def __init__(
        self,
        entrypoint: str,
        *,
        store_path: str | Path | None = None,
        run_id: str | None = None,
        now: Callable[[], datetime] | None = None,
        env_path: str | Path = ".env",
    ) -> None:
        self.entrypoint = entrypoint
        self.run_id = run_id or uuid.uuid4().hex
        self.store_path = Path(
            store_path or _config_value("LLM_USAGE_STORE", env_path) or DEFAULT_LLM_USAGE_STORE
        )
        self._now = now or (lambda: datetime.now(SHANGHAI))
        self._warnings: list[str] = []
        self._warning_lock = threading.Lock()
        self._available = self._initialize()

    def record_success(
        self,
        *,
        operation: str,
        model: str,
        input_tokens: int | None,
        output_tokens: int | None,
        cache_hit_input_tokens: int | None = None,
        cache_miss_input_tokens: int | None = None,
        scope_id: str = "",
    ) -> None:
        cost_nano, cost_status = _price_usage(
            model,
            input_tokens,
            output_tokens,
            cache_hit_input_tokens,
            cache_miss_input_tokens,
        )
        self._record(
            operation=operation,
            model=model,
            status="succeeded",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_input_tokens=cache_hit_input_tokens,
            cache_miss_input_tokens=cache_miss_input_tokens,
            cost_nano_cny=cost_nano,
            cost_status=cost_status,
            scope_id=scope_id,
            failure_category="",
        )

    def record_failure(
        self,
        *,
        operation: str,
        model: str,
        failure_category: str,
        scope_id: str = "",
        input_tokens: int | None = None,
        output_tokens: int | None = None,
        cache_hit_input_tokens: int | None = None,
        cache_miss_input_tokens: int | None = None,
    ) -> None:
        cost_nano, cost_status = _price_usage(
            model,
            input_tokens,
            output_tokens,
            cache_hit_input_tokens,
            cache_miss_input_tokens,
        )
        self._record(
            operation=operation,
            model=model,
            status="failed",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_input_tokens=cache_hit_input_tokens,
            cache_miss_input_tokens=cache_miss_input_tokens,
            cost_nano_cny=cost_nano,
            cost_status=cost_status,
            scope_id=scope_id,
            failure_category=failure_category,
        )

    def summary(self) -> LLMUsageSummary:
        if not self._available:
            return LLMUsageSummary(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, self.warnings)
        usage_date = _shanghai_time(self._now()).date().isoformat()
        try:
            with self._connect() as connection:
                run = _summary_row(connection, "run_id = ?", (self.run_id,))
                daily = _summary_row(connection, "usage_date = ?", (usage_date,))
        except sqlite3.Error as exc:
            self._warn(f"LLM 计费汇总不可用：{exc}")
            return LLMUsageSummary(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, self.warnings)
        return LLMUsageSummary(
            run_call_count=run[0],
            run_input_tokens=run[1],
            run_output_tokens=run[2],
            run_cost_nano_cny=run[3],
            run_unpriced_calls=run[4],
            run_estimated_calls=run[5],
            run_failed_calls=run[6],
            daily_call_count=daily[0],
            daily_input_tokens=daily[1],
            daily_output_tokens=daily[2],
            daily_cost_nano_cny=daily[3],
            daily_unpriced_calls=daily[4],
            warnings=self.warnings,
        )

    @property
    def warnings(self) -> tuple[str, ...]:
        with self._warning_lock:
            return tuple(self._warnings)

    def _initialize(self) -> bool:
        try:
            self.store_path.parent.mkdir(parents=True, exist_ok=True)
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode=WAL")
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS llm_calls (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        call_id TEXT NOT NULL UNIQUE,
                        run_id TEXT NOT NULL,
                        entrypoint TEXT NOT NULL,
                        scope_id TEXT NOT NULL,
                        operation TEXT NOT NULL,
                        model TEXT NOT NULL,
                        status TEXT NOT NULL,
                        input_tokens INTEGER,
                        output_tokens INTEGER,
                        cache_hit_input_tokens INTEGER,
                        cache_miss_input_tokens INTEGER,
                        cost_nano_cny INTEGER,
                        cost_status TEXT NOT NULL,
                        failure_category TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        usage_date TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS llm_calls_run_id ON llm_calls(run_id)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS llm_calls_usage_date ON llm_calls(usage_date)"
                )
        except (OSError, sqlite3.Error) as exc:
            self._warn(f"LLM 计费记录不可用：{exc}")
            return False
        return True

    def _record(
        self,
        *,
        operation: str,
        model: str,
        status: str,
        input_tokens: int | None,
        output_tokens: int | None,
        cache_hit_input_tokens: int | None,
        cache_miss_input_tokens: int | None,
        cost_nano_cny: int | None,
        cost_status: str,
        scope_id: str,
        failure_category: str,
    ) -> None:
        if not self._available:
            return
        created_at = _shanghai_time(self._now())
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO llm_calls (
                        call_id, run_id, entrypoint, scope_id, operation, model, status,
                        input_tokens, output_tokens, cache_hit_input_tokens,
                        cache_miss_input_tokens, cost_nano_cny, cost_status, failure_category,
                        created_at, usage_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        uuid.uuid4().hex,
                        self.run_id,
                        self.entrypoint,
                        scope_id,
                        operation,
                        model,
                        status,
                        input_tokens,
                        output_tokens,
                        cache_hit_input_tokens,
                        cache_miss_input_tokens,
                        cost_nano_cny,
                        cost_status,
                        failure_category,
                        created_at.isoformat(timespec="seconds"),
                        created_at.date().isoformat(),
                    ),
                )
        except sqlite3.Error as exc:
            self._warn(f"LLM 计费写入不完整：{exc}")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.store_path, timeout=30)

    def _warn(self, warning: str) -> None:
        with self._warning_lock:
            if warning not in self._warnings:
                self._warnings.append(warning)


def format_usage_line(summary: LLMUsageSummary) -> str:
    line = (
        f"LLM 使用：本次 {summary.run_call_count} 次，"
        f"输入 {summary.run_input_tokens}，输出 {summary.run_output_tokens}，"
        f"已计价 ¥{_format_cny(summary.run_cost_cny)}；"
        f"今日 {summary.daily_call_count} 次，已计价 ¥{_format_cny(summary.daily_cost_cny)}"
    )
    if summary.run_unpriced_calls or summary.daily_unpriced_calls:
        line += (
            f"；费用不完整（本次 {summary.run_unpriced_calls} 次、"
            f"今日 {summary.daily_unpriced_calls} 次未计价）"
        )
    if summary.warnings:
        line += f"；{'；'.join(summary.warnings)}"
    return line


def render_usage_markdown(summary: LLMUsageSummary) -> str:
    lines = [
        "## LLM 使用与费用",
        "",
        (
            f"- 本次运行：{summary.run_call_count} 次调用，输入 {summary.run_input_tokens} tokens，"
            f"输出 {summary.run_output_tokens} tokens，已计价 ¥{_format_cny(summary.run_cost_cny)}"
        ),
        (
            f"- 今日累计：{summary.daily_call_count} 次调用，输入 {summary.daily_input_tokens} tokens，"
            f"输出 {summary.daily_output_tokens} tokens，已计价 ¥{_format_cny(summary.daily_cost_cny)}"
        ),
    ]
    if summary.run_estimated_calls:
        lines.append(f"- 其中 {summary.run_estimated_calls} 次按缓存未命中价格保守估算")
    if summary.run_unpriced_calls or summary.daily_unpriced_calls:
        lines.append(
            f"- 费用不完整：本次 {summary.run_unpriced_calls} 次、"
            f"今日 {summary.daily_unpriced_calls} 次调用无法计价"
        )
    lines.extend(f"- 警告：{warning}" for warning in summary.warnings)
    return "\n".join(lines)


def _price_usage(
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    cache_hit_input_tokens: int | None,
    cache_miss_input_tokens: int | None,
) -> tuple[int | None, str]:
    price = DEEPSEEK_PRICES.get(model)
    if price is None or input_tokens is None or output_tokens is None:
        return None, "unknown_model" if price is None else "unavailable"
    estimated = cache_hit_input_tokens is None or cache_miss_input_tokens is None
    if estimated:
        hit_tokens = 0
        miss_tokens = input_tokens
    else:
        hit_tokens = cache_hit_input_tokens
        miss_tokens = cache_miss_input_tokens
    cost = (
        Decimal(hit_tokens) * price.cache_hit_input
        + Decimal(miss_tokens) * price.cache_miss_input
        + Decimal(output_tokens) * price.output
    ) * Decimal("1000")
    return int(cost.quantize(Decimal("1"), rounding=ROUND_HALF_UP)), (
        "estimated" if estimated else "priced"
    )


def _summary_row(
    connection: sqlite3.Connection,
    where: str,
    parameters: tuple[str, ...],
) -> tuple[int, int, int, int, int, int, int]:
    row = connection.execute(
        f"""
        SELECT
            COUNT(*),
            COALESCE(SUM(input_tokens), 0),
            COALESCE(SUM(output_tokens), 0),
            COALESCE(SUM(cost_nano_cny), 0),
            COALESCE(SUM(CASE WHEN cost_nano_cny IS NULL THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN cost_status = 'estimated' THEN 1 ELSE 0 END), 0),
            COALESCE(SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END), 0)
        FROM llm_calls WHERE {where}
        """,
        parameters,
    ).fetchone()
    assert row is not None
    return tuple(int(value) for value in row)  # type: ignore[return-value]


def _shanghai_time(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=SHANGHAI)
    return value.astimezone(SHANGHAI)


def _format_cny(value: Decimal) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".") or "0"


def _config_value(key: str, env_path: str | Path) -> str:
    value = os.environ.get(key)
    if value:
        return value
    path = Path(env_path)
    if not path.exists():
        return ""
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        current_key, current_value = line.split("=", 1)
        if current_key.strip() == key:
            return current_value.strip().strip('"').strip("'")
    return ""
