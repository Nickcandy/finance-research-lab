from finance_research_lab.agents.context import build_context_messages
from finance_research_lab.agents.tools import ToolRegistry, ToolSpec
from finance_research_lab.llm.mock_client import MockLLMClient


def test_mock_llm_client_returns_configured_completion() -> None:
    client = MockLLMClient(completion="今日重点关注 AI 数据中心产业链。")

    response = client.complete(
        messages=[{"role": "user", "content": "生成今日机会雷达"}],
        model="mock-research-model",
    )

    assert response.content == "今日重点关注 AI 数据中心产业链。"
    assert response.model == "mock-research-model"
    assert response.input_tokens > 0


def test_tool_registry_executes_registered_tool_with_schema() -> None:
    registry = ToolRegistry()

    def add(a: int, b: int) -> int:
        return a + b

    registry.register(
        ToolSpec(
            name="add",
            description="Add two numbers",
            parameters={
                "type": "object",
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
            },
            handler=add,
        )
    )

    result = registry.execute("add", {"a": 2, "b": 3})

    assert result.tool_name == "add"
    assert result.status == "success"
    assert result.output == 5
    assert registry.to_openai_tools()[0]["function"]["name"] == "add"


def test_build_context_messages_keeps_stable_sections_and_budget() -> None:
    messages = build_context_messages(
        task="生成投资机会雷达",
        market_context="AI 数据中心新闻；稳定币监管新闻",
        tool_results=["read_watchlist: 3 items", "trace_news: 2 events"],
        output_schema="Markdown sections: 核心结论、机会、风险、验证点",
        max_chars=220,
    )

    assert [message["role"] for message in messages] == ["system", "user"]
    user_content = messages[1]["content"]
    assert "任务" in user_content
    assert "市场上下文" in user_content
    assert "工具结果摘要" in user_content
    assert len(user_content) <= 220
