from __future__ import annotations


def build_context_messages(
    *,
    task: str,
    market_context: str,
    tool_results: list[str],
    output_schema: str,
    max_chars: int = 4000,
) -> list[dict[str, str]]:
    """Build a compact prompt with stable sections and a simple char budget.

    This is deliberately small: V0 only needs a predictable place to put task,
    market context, tool summaries, and output constraints. Later versions can
    replace this with token counting, RAG, and summarization without changing the
    workflow code that calls it.
    """

    system = (
        "你是投资研究 Agent，只输出研究辅助、风险边界和可复盘假设。"
        "所有候选标的都需要支持证据、反对证据和证伪条件。"
    )
    user = _join_sections(
        [
            ("任务", task),
            ("市场上下文", market_context),
            ("工具结果摘要", "\n".join(tool_results)),
            ("输出格式", output_schema),
        ]
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": _truncate(user, max_chars)},
    ]


def _join_sections(sections: list[tuple[str, str]]) -> str:
    return "\n\n".join(f"## {title}\n{content}" for title, content in sections if content)


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    suffix = "\n\n[内容已按上下文预算截断]"
    keep = max(0, max_chars - len(suffix))
    return text[:keep].rstrip() + suffix
