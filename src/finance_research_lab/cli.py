from __future__ import annotations

import argparse
from .workflow import run_news_trace_workflow, run_radar_workflow, run_research_agent_workflow


def trace_news(args: argparse.Namespace) -> int:
    run = run_news_trace_workflow(
        url=args.url,
        watchlist_path=args.watchlist,
        output_path=args.output,
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
    )
    for step in run.steps:
        print(f"[{step.status}] {step.step_name} via {step.tool_name}: {step.summary}")
    if not run.steps or run.steps[-1].status == "error":
        return 1
    print(f"wrote {run.output_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finance research lab CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    trace = subparsers.add_parser("trace-news", help="Generate a Markdown news-trace report")
    trace.add_argument("--url", required=True, help="Static HTML news article URL")
    trace.add_argument("--watchlist", default="data/watchlist.example.csv", help="CSV watchlist path")
    trace.add_argument("--output", default="reports/news-trace.md", help="Output Markdown path")
    trace.set_defaults(func=trace_news)

    radar = subparsers.add_parser("radar", help="Generate a daily opportunity radar report")
    radar.add_argument("--urls", nargs="+", required=True, help="Static HTML news article URLs")
    radar.add_argument("--watchlist", default="data/watchlist.example.csv", help="CSV watchlist path")
    radar.add_argument("--output", default="reports/opportunity-radar.md", help="Output Markdown path")
    radar.set_defaults(func=radar_cmd)

    agent = subparsers.add_parser("research-agent", help="Generate a task/evidence Agent report")
    agent.add_argument("--url", required=True, help="Static HTML news article URL")
    agent.add_argument("--watchlist", default="data/watchlist.example.csv", help="CSV watchlist path")
    agent.add_argument("--output", default="reports/agent-report.md", help="Output Markdown path")
    agent.set_defaults(func=research_agent_cmd)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
