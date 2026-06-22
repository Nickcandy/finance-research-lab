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
