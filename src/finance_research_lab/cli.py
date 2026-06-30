from __future__ import annotations

import argparse
import sys
from .a_share_universe import sync_a_share_universe_from_akshare
from .workflow import run_news_trace_workflow, run_radar_workflow, run_research_agent_workflow


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


def research_agent_cmd(args: argparse.Namespace) -> int:
    run = run_research_agent_workflow(
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

    agent = subparsers.add_parser("research-agent", help="Generate a task/evidence Agent report")
    agent.add_argument("--url", required=True, help="Static HTML news article URL")
    agent.add_argument("--watchlist", default="data/watchlist.example.csv", help="CSV watchlist path")
    agent.add_argument(
        "--a-share-universe",
        default="data/a_share_universe.example.csv",
        help="CSV A-share universe path",
    )
    agent.add_argument("--output", default="reports/agent-report.md", help="Output Markdown path")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
