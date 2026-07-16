from __future__ import annotations

import argparse
import sys
from time import sleep

from .akshare_evidence import AkShareEvidenceProvider
from .a_share_universe import sync_a_share_universe_from_akshare
from .baostock_market import BaoStockMarketProvider
from .market_evidence import FallbackMarketProvider
from .workflow import (
    run_daily_radar_workflow,
    run_news_trace_workflow,
    run_radar_workflow,
    run_research_agent_workflow,
)


def trace_news(args: argparse.Namespace) -> int:
    run = run_news_trace_workflow(
        url=args.url,
        watchlist_path=args.watchlist,
        output_path=args.output,
        a_share_universe_path=args.a_share_universe,
    )
    for step in run.steps:
        print(f"[{step.status}] {step.step_name} via {step.tool_name}: {step.summary}")
    if not run.steps or run.steps[-1].status == "error":
        return 1
    print(f"wrote {run.output_path}")
    return 0


def radar_cmd(args: argparse.Namespace) -> int:
    run = run_radar_workflow(
        urls=args.urls,
        watchlist_path=args.watchlist,
        output_path=args.output,
        a_share_universe_path=args.a_share_universe,
    )
    for step in run.steps:
        print(f"[{step.status}] {step.step_name} via {step.tool_name}: {step.summary}")
    if not run.steps or run.steps[-1].status == "error":
        return 1
    print(f"wrote {run.output_path}")
    return 0


def daily_radar_cmd(args: argparse.Namespace) -> int:
    run = run_daily_radar_workflow(
        output_path=args.output,
        event_cache_path=args.event_cache,
        watchlist_path=args.watchlist,
        a_share_universe_path=args.a_share_universe,
        evidence_cache_path=args.evidence_cache,
        market_cache_path=args.market_cache,
        refresh_evidence=args.refresh_evidence,
        json_output_path=args.json_output,
    )
    for step in run.steps:
        print(f"[{step.status}] {step.step_name} via {step.tool_name}: {step.summary}")
    if not run.steps or run.steps[-1].status == "error":
        return 1
    print(f"wrote {run.output_path}")
    print(f"wrote {args.json_output}")
    return 0


def research_agent_cmd(args: argparse.Namespace) -> int:
    run = run_research_agent_workflow(
        url=args.url,
        watchlist_path=args.watchlist,
        output_path=args.output,
        a_share_universe_path=args.a_share_universe,
        evidence_cache_path=args.evidence_cache,
        market_cache_path=args.market_cache,
        refresh_evidence=args.refresh_evidence,
    )
    for step in run.steps:
        print(f"[{step.status}] {step.step_name} via {step.tool_name}: {step.summary}")
    if not run.steps or run.steps[-1].status == "error":
        return 1
    print(f"wrote {run.output_path}")
    return 0


def sync_a_share_universe_cmd(args: argparse.Namespace) -> int:
    if args.source != "akshare":
        raise ValueError(f"unsupported A-share universe source: {args.source}")
    try:
        companies = sync_a_share_universe_from_akshare(args.output)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"wrote {args.output} ({len(companies)} companies)")
    return 0


def sync_a_share_evidence_cmd(args: argparse.Namespace) -> int:
    company_provider = AkShareEvidenceProvider(args.cache, refresh=True)
    market_provider = FallbackMarketProvider(
        BaoStockMarketProvider(args.market_cache, refresh=True),
        company_provider,
    )
    try:
        for index, symbol in enumerate(args.symbols):
            announcements = company_provider.announcements(symbol)
            financials = company_provider.financials(symbol)
            market = market_provider.market(symbol, args.lookback_days)
            print(
                f"synced {symbol}: {len(announcements)} announcements, "
                f"{len(financials)} financial periods, market {market.trade_date}"
            )
            if index < len(args.symbols) - 1:
                sleep(1)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finance research lab CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    trace = subparsers.add_parser("trace-news", help="Generate a Markdown news-trace report")
    trace.add_argument("--url", required=True, help="Static HTML news article URL")
    trace.add_argument("--watchlist", default="data/watchlist.example.csv", help="CSV watchlist path")
    trace.add_argument(
        "--a-share-universe",
        default="data/a_share_universe.example.csv",
        help="CSV A-share universe path",
    )
    trace.add_argument("--output", default="reports/news-trace.md", help="Output Markdown path")
    trace.set_defaults(func=trace_news)

    radar = subparsers.add_parser("radar", help="Generate a daily opportunity radar report")
    radar.add_argument("--urls", nargs="+", required=True, help="Static HTML news article URLs")
    radar.add_argument("--watchlist", default="data/watchlist.example.csv", help="CSV watchlist path")
    radar.add_argument(
        "--a-share-universe",
        default="data/a_share_universe.example.csv",
        help="CSV A-share universe path",
    )
    radar.add_argument("--output", default="reports/opportunity-radar.md", help="Output Markdown path")
    radar.set_defaults(func=radar_cmd)

    daily_radar = subparsers.add_parser(
        "daily-radar",
        help="Discover and render the latest 24-hour market events",
    )
    daily_radar.add_argument(
        "--event-cache",
        default="data/event_cache/ths",
        help="THS event snapshot cache path",
    )
    daily_radar.add_argument(
        "--output",
        default="reports/daily-radar.md",
        help="Output Markdown path",
    )
    daily_radar.add_argument(
        "--json-output",
        default="reports/daily-radar.json",
        help="Output DailyRadarSnapshot JSON path",
    )
    daily_radar.add_argument(
        "--watchlist",
        default="data/watchlist.example.csv",
        help="CSV watchlist context path",
    )
    daily_radar.add_argument(
        "--a-share-universe",
        default="data/a_share_universe.csv",
        help="CSV A-share universe path",
    )
    daily_radar.add_argument(
        "--evidence-cache",
        default="data/akshare_cache",
        help="AkShare evidence cache path",
    )
    daily_radar.add_argument(
        "--market-cache",
        default="data/baostock_cache",
        help="BaoStock market cache path",
    )
    daily_radar.add_argument(
        "--refresh-evidence",
        action="store_true",
        help="Refresh all candidate evidence caches",
    )
    daily_radar.set_defaults(func=daily_radar_cmd)

    agent = subparsers.add_parser("research-agent", help="Generate a task/evidence Agent report")
    agent.add_argument("--url", required=True, help="Static HTML news article URL")
    agent.add_argument("--watchlist", default="data/watchlist.example.csv", help="CSV watchlist path")
    agent.add_argument(
        "--a-share-universe",
        default="data/a_share_universe.example.csv",
        help="CSV A-share universe path",
    )
    agent.add_argument("--output", default="reports/agent-report.md", help="Output Markdown path")
    agent.add_argument("--evidence-cache", default="data/akshare_cache", help="AkShare evidence cache path")
    agent.add_argument("--market-cache", default="data/baostock_cache", help="BaoStock market cache path")
    agent.add_argument("--refresh-evidence", action="store_true", help="Refresh all evidence caches")
    agent.set_defaults(func=research_agent_cmd)

    sync_universe = subparsers.add_parser(
        "sync-a-share-universe",
        help="Fetch A-share basics and write the local universe CSV",
    )
    sync_universe.add_argument("--source", default="akshare", choices=["akshare"], help="Data source")
    sync_universe.add_argument(
        "--output",
        default="data/a_share_universe.csv",
        help="Output CSV A-share universe path",
    )
    sync_universe.set_defaults(func=sync_a_share_universe_cmd)

    sync_evidence = subparsers.add_parser(
        "sync-a-share-evidence", help="Fetch and cache A-share evidence"
    )
    sync_evidence.add_argument("--symbols", nargs="+", required=True, help="A-share symbols, e.g. 300308.SZ")
    sync_evidence.add_argument("--cache", default="data/akshare_cache", help="Evidence cache path")
    sync_evidence.add_argument(
        "--market-cache", default="data/baostock_cache", help="BaoStock market cache path"
    )
    sync_evidence.add_argument("--lookback-days", type=int, default=5, help="Trading days for market evidence")
    sync_evidence.set_defaults(func=sync_a_share_evidence_cmd)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
