from __future__ import annotations

import argparse
from .workflow import run_news_trace_workflow


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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finance research lab CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    trace = subparsers.add_parser("trace-news", help="Generate a Markdown news-trace report")
    trace.add_argument("--url", required=True, help="Static HTML news article URL")
    trace.add_argument("--watchlist", default="data/watchlist.example.csv", help="CSV watchlist path")
    trace.add_argument("--output", default="reports/news-trace.md", help="Output Markdown path")
    trace.set_defaults(func=trace_news)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
