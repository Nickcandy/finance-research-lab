from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from decimal import Decimal
import sqlite3
from zoneinfo import ZoneInfo

from finance_research_lab.llm.usage import (
    LLMUsageSession,
    format_usage_line,
    render_usage_markdown,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_deepseek_v4_pro_usage_is_priced_from_cache_tokens(tmp_path) -> None:
    session = LLMUsageSession(
        "daily_radar",
        store_path=tmp_path / "usage.sqlite3",
        run_id="run-1",
        now=lambda: datetime(2026, 7, 19, 10, tzinfo=SHANGHAI),
    )

    session.record_success(
        operation="research_report",
        model="deepseek-v4-pro",
        input_tokens=3_000_000,
        output_tokens=1_000_000,
        cache_hit_input_tokens=1_000_000,
        cache_miss_input_tokens=2_000_000,
        scope_id="event-1",
    )

    summary = session.summary()
    assert summary.run_call_count == 1
    assert summary.run_input_tokens == 3_000_000
    assert summary.run_output_tokens == 1_000_000
    assert summary.run_cost_cny == Decimal("12.025")
    assert summary.run_unpriced_calls == 0
    assert summary.complete
    with sqlite3.connect(tmp_path / "usage.sqlite3") as connection:
        row = connection.execute(
            "SELECT entrypoint, scope_id, operation, model, status FROM llm_calls"
        ).fetchone()
        columns = {item[1] for item in connection.execute("PRAGMA table_info(llm_calls)")}
    assert row == (
        "daily_radar",
        "event-1",
        "research_report",
        "deepseek-v4-pro",
        "succeeded",
    )
    assert {"prompt", "content", "raw_response", "api_key"}.isdisjoint(columns)


def test_missing_cache_split_uses_conservative_cache_miss_price(tmp_path) -> None:
    session = LLMUsageSession(
        "research_agent",
        store_path=tmp_path / "usage.sqlite3",
        run_id="run-1",
    )

    session.record_success(
        operation="research_tasks",
        model="deepseek-v4-flash",
        input_tokens=1_000_000,
        output_tokens=500_000,
    )

    summary = session.summary()
    assert summary.run_cost_cny == Decimal("2")
    assert summary.run_estimated_calls == 1
    assert summary.complete


def test_unknown_model_keeps_tokens_and_marks_cost_incomplete(tmp_path) -> None:
    session = LLMUsageSession(
        "trace_news",
        store_path=tmp_path / "usage.sqlite3",
        run_id="run-1",
    )

    session.record_success(
        operation="research_report",
        model="custom-model",
        input_tokens=100,
        output_tokens=20,
    )

    summary = session.summary()
    assert summary.run_input_tokens == 100
    assert summary.run_output_tokens == 20
    assert summary.run_cost_cny == Decimal("0")
    assert summary.run_unpriced_calls == 1
    assert not summary.complete
    assert "费用不完整" in format_usage_line(summary)


def test_failed_request_is_recorded_as_unpriced(tmp_path) -> None:
    session = LLMUsageSession(
        "radar",
        store_path=tmp_path / "usage.sqlite3",
        run_id="run-1",
    )

    session.record_failure(
        operation="research_report",
        model="deepseek-v4-pro",
        failure_category="transport_error",
    )

    summary = session.summary()
    assert summary.run_call_count == 1
    assert summary.run_failed_calls == 1
    assert summary.run_unpriced_calls == 1
    assert not summary.complete


def test_daily_summary_uses_shanghai_calendar_date(tmp_path) -> None:
    store = tmp_path / "usage.sqlite3"
    first = LLMUsageSession(
        "daily_radar",
        store_path=store,
        run_id="run-1",
        now=lambda: datetime(2026, 7, 19, 23, 59, tzinfo=SHANGHAI),
    )
    first.record_success(
        operation="research_report",
        model="deepseek-v4-flash",
        input_tokens=1,
        output_tokens=1,
    )
    second = LLMUsageSession(
        "daily_radar",
        store_path=store,
        run_id="run-2",
        now=lambda: datetime(2026, 7, 20, 0, 1, tzinfo=SHANGHAI),
    )
    second.record_success(
        operation="research_report",
        model="deepseek-v4-flash",
        input_tokens=2,
        output_tokens=2,
    )

    summary = second.summary()
    assert summary.run_call_count == 1
    assert summary.daily_call_count == 1
    assert summary.daily_input_tokens == 2


def test_concurrent_sessions_do_not_lose_usage_rows(tmp_path) -> None:
    store = tmp_path / "usage.sqlite3"

    def write(index: int) -> None:
        session = LLMUsageSession(
            "event_analysis",
            store_path=store,
            run_id=f"run-{index}",
            now=lambda: datetime(2026, 7, 19, 10, tzinfo=SHANGHAI),
        )
        session.record_success(
            operation="research_report",
            model="deepseek-v4-flash",
            input_tokens=10,
            output_tokens=5,
            scope_id=f"event-{index}",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(write, range(20)))

    summary = LLMUsageSession(
        "audit",
        store_path=store,
        run_id="audit",
        now=lambda: datetime(2026, 7, 19, 12, tzinfo=SHANGHAI),
    ).summary()
    assert summary.daily_call_count == 20


def test_usage_markdown_does_not_expose_request_content(tmp_path) -> None:
    session = LLMUsageSession(
        "daily_radar",
        store_path=tmp_path / "usage.sqlite3",
        run_id="run-1",
    )
    session.record_success(
        operation="research_report",
        model="deepseek-v4-flash",
        input_tokens=100,
        output_tokens=20,
    )

    markdown = render_usage_markdown(session.summary())
    assert markdown.startswith("## LLM 使用与费用")
    assert "本次运行" in markdown
    assert "今日累计" in markdown
    assert "prompt" not in markdown.lower()


def test_store_failure_is_visible_without_interrupting_usage(tmp_path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("blocked", encoding="utf-8")
    session = LLMUsageSession(
        "daily_radar",
        store_path=blocker / "usage.sqlite3",
        run_id="run-1",
    )

    session.record_success(
        operation="research_report",
        model="deepseek-v4-flash",
        input_tokens=100,
        output_tokens=20,
    )

    summary = session.summary()
    assert summary.run_call_count == 0
    assert not summary.complete
    assert "计费记录不可用" in render_usage_markdown(summary)
