from datetime import date

from finance_research_lab.models import NewsTrace
from finance_research_lab.report import render_news_trace


def test_render_news_trace_contains_core_sections() -> None:
    trace = NewsTrace(
        headline="稳定币监管框架推进",
        source="manual",
        news_type="政策 / 监管",
        payer="支付公司",
        receiver="稳定币发行方",
        value_chain=["监管", "发行", "支付"],
        direct_beneficiaries=[],
        indirect_beneficiaries=[],
        sentiment_mappings=[],
        stage="待判断",
        action_state="等验证",
        verification_points=["查官方文件"],
    )
    md = render_news_trace(trace, date(2026, 6, 16))
    assert "# 热点追源：稳定币监管框架推进" in md
    assert "## 3. 市场映射" in md
    assert "- [ ] 查官方文件" in md
