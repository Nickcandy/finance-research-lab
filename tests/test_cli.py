import pytest

from finance_research_lab import cli
from finance_research_lab.agent_models import AgentRun, AgentStep
from finance_research_lab.cli import build_parser


def test_trace_news_cli_requires_url() -> None:
    parser = build_parser()

    args = parser.parse_args(["trace-news", "--url", "https://news.example.com/article"])

    assert args.url == "https://news.example.com/article"


def test_trace_news_cli_rejects_removed_headline_input() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["trace-news", "--headline", "AI capex increases"])


def test_trace_news_cli_forwards_only_trace_arguments(monkeypatch) -> None:
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return _successful_run("news_trace", kwargs["output_path"])

    monkeypatch.setattr(cli, "run_news_trace_workflow", fake_run)

    assert cli.main(["trace-news", "--url", "https://news.example.com/article"]) == 0
    assert set(captured) == {"url", "watchlist_path", "output_path", "a_share_universe_path"}


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
    assert args.evidence_cache == "data/akshare_cache"
    assert args.market_cache == "data/baostock_cache"
    assert not args.refresh_evidence


def test_research_agent_cli_rejects_removed_headline_input() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["research-agent", "--headline", "AI capex increases"])


def test_research_agent_cli_forwards_evidence_options(monkeypatch, tmp_path) -> None:
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return _successful_run("research_agent", kwargs["output_path"])

    monkeypatch.setattr(cli, "run_research_agent_workflow", fake_run)
    cache = tmp_path / "cache"
    market_cache = tmp_path / "market-cache"

    assert (
        cli.main(
            [
                "research-agent",
                "--url",
                "https://news.example.com/article",
                "--evidence-cache",
                str(cache),
                "--market-cache",
                str(market_cache),
                "--refresh-evidence",
            ]
        )
        == 0
    )
    assert captured["evidence_cache_path"] == str(cache)
    assert captured["market_cache_path"] == str(market_cache)
    assert captured["refresh_evidence"] is True


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


def test_sync_a_share_evidence_cli_accepts_symbols() -> None:
    parser = build_parser()

    args = parser.parse_args(["sync-a-share-evidence", "--symbols", "300308.SZ", "600519.SH"])

    assert args.symbols == ["300308.SZ", "600519.SH"]
    assert args.cache == "data/akshare_cache"
    assert args.market_cache == "data/baostock_cache"
    assert args.lookback_days == 5


def test_sync_a_share_evidence_cli_returns_error_on_provider_failure(monkeypatch, capsys) -> None:
    class FailingProvider:
        def __init__(self, *args, **kwargs):
            pass

        def announcements(self, symbol):
            raise RuntimeError(f"cannot sync {symbol}")

    monkeypatch.setattr(cli, "AkShareEvidenceProvider", FailingProvider)

    assert cli.main(["sync-a-share-evidence", "--symbols", "300308.SZ"]) == 1
    assert "cannot sync 300308.SZ" in capsys.readouterr().err


def test_sync_a_share_evidence_uses_market_cache_and_waits_between_symbols(
    monkeypatch, tmp_path
) -> None:
    captured = {}
    sleeps = []

    class CompanyProvider:
        def __init__(self, cache, refresh):
            captured["company"] = (cache, refresh)

        def announcements(self, symbol):
            return ()

        def financials(self, symbol):
            return ()

        def market(self, symbol, lookback_days):
            raise AssertionError("fallback should not run")

    class MarketProvider:
        def __init__(self, cache, refresh):
            captured["market"] = (cache, refresh)

        def market(self, symbol, lookback_days):
            return type("Snapshot", (), {"trade_date": "2026-07-10"})()

    monkeypatch.setattr(cli, "AkShareEvidenceProvider", CompanyProvider)
    monkeypatch.setattr(cli, "BaoStockMarketProvider", MarketProvider)
    monkeypatch.setattr(cli, "sleep", sleeps.append)
    company_cache = tmp_path / "company"
    market_cache = tmp_path / "market"

    exit_code = cli.main(
        [
            "sync-a-share-evidence",
            "--symbols",
            "300308.SZ",
            "600519.SH",
            "--cache",
            str(company_cache),
            "--market-cache",
            str(market_cache),
        ]
    )

    assert exit_code == 0
    assert captured == {
        "company": (str(company_cache), True),
        "market": (str(market_cache), True),
    }
    assert sleeps == [1]


def _successful_run(name: str, output_path: str) -> AgentRun:
    return AgentRun(name, [AgentStep("done", "test", "success", "ok")], output_path)
