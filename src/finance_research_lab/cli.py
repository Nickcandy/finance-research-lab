from __future__ import annotations

import argparse
from pathlib import Path

from .news_trace import build_trace, load_watchlist
from .report import render_news_trace


def trace_news(args: argparse.Namespace) -> int:
    watchlist = load_watchlist(args.watchlist)
    trace = build_trace(args.headline, args.source, watchlist)
    markdown = render_news_trace(trace)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown, encoding="utf-8")
    print(f"wrote {output}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finance research lab CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    trace = subparsers.add_parser("trace-news", help="Generate a Markdown news-trace report")
    trace.add_argument("--headline", required=True, help="News headline, URL title, or hot topic")
    trace.add_argument("--source", default="manual", help="Source name or URL")
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
