import pytest

from finance_research_lab.cli import build_parser


def test_trace_news_cli_requires_url() -> None:
    parser = build_parser()

    args = parser.parse_args(["trace-news", "--url", "https://news.example.com/article"])

    assert args.url == "https://news.example.com/article"


def test_trace_news_cli_rejects_removed_headline_input() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["trace-news", "--headline", "AI capex increases"])


def test_radar_cli_accepts_multiple_urls_with_defaults() -> None:
    parser = build_parser()

    args = parser.parse_args(["radar", "--urls", "https://news.example.com/one", "https://news.example.com/two"])

    assert args.urls == ["https://news.example.com/one", "https://news.example.com/two"]
    assert args.watchlist == "data/watchlist.example.csv"
    assert args.output == "reports/opportunity-radar.md"


def test_research_agent_cli_requires_url() -> None:
    parser = build_parser()

    args = parser.parse_args(["research-agent", "--url", "https://news.example.com/article"])

    assert args.url == "https://news.example.com/article"
    assert args.watchlist == "data/watchlist.example.csv"
    assert args.output == "reports/agent-report.md"


def test_research_agent_cli_rejects_removed_headline_input() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["research-agent", "--headline", "AI capex increases"])
