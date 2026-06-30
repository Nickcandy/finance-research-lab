import pytest

from finance_research_lab import cli
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
    assert args.a_share_universe == "data/a_share_universe.example.csv"
    assert args.output == "reports/opportunity-radar.md"


def test_research_agent_cli_requires_url() -> None:
    parser = build_parser()

    args = parser.parse_args(["research-agent", "--url", "https://news.example.com/article"])

    assert args.url == "https://news.example.com/article"
    assert args.watchlist == "data/watchlist.example.csv"
    assert args.a_share_universe == "data/a_share_universe.example.csv"
    assert args.output == "reports/agent-report.md"


def test_research_agent_cli_rejects_removed_headline_input() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["research-agent", "--headline", "AI capex increases"])


def test_sync_a_share_universe_cli_defaults_to_akshare() -> None:
    parser = build_parser()

    args = parser.parse_args(["sync-a-share-universe"])

    assert args.source == "akshare"
    assert args.output == "data/a_share_universe.csv"


def test_sync_a_share_universe_cli_returns_error_on_sync_failure(monkeypatch, capsys) -> None:
    def fail_sync(output: str) -> list[object]:
        raise RuntimeError(f"cannot sync {output}")

    monkeypatch.setattr(cli, "sync_a_share_universe_from_akshare", fail_sync)

    exit_code = cli.main(["sync-a-share-universe", "--output", "tmp.csv"])

    assert exit_code == 1
    assert "cannot sync tmp.csv" in capsys.readouterr().err
