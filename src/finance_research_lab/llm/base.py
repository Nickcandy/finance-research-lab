from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class LLMResponse:
    """Normalized response returned by any model adapter.

    The rest of the project should depend on this shape instead of depending on
    OpenAI, Claude, Qwen, LangChain, or another provider directly.
    """

    content: str
    model: str
    input_tokens: int | None = 0
    output_tokens: int | None = 0
    cache_hit_input_tokens: int | None = None
    cache_miss_input_tokens: int | None = None
    raw: Any = None


class LLMClient:
    """Small interface for pluggable model clients."""

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float = 0.2,
    ) -> LLMResponse:
        raise NotImplementedError

    def tool_call(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]],
        *,
        model: str,
        temperature: float = 0.2,
    ) -> LLMResponse:
        raise NotImplementedError
