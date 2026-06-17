from __future__ import annotations

from .base import LLMClient, LLMResponse


class MockLLMClient(LLMClient):
    """Deterministic model adapter for tests and local demos."""

    def __init__(self, completion: str = "") -> None:
        self.completion = completion

    def complete(
        self,
        messages: list[dict[str, str]],
        *,
        model: str,
        temperature: float = 0.2,
    ) -> LLMResponse:
        input_text = "\n".join(message.get("content", "") for message in messages)
        return LLMResponse(
            content=self.completion,
            model=model,
            input_tokens=_rough_token_count(input_text),
            output_tokens=_rough_token_count(self.completion),
            raw={"temperature": temperature},
        )

    def tool_call(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, object]],
        *,
        model: str,
        temperature: float = 0.2,
    ) -> LLMResponse:
        response = self.complete(messages, model=model, temperature=temperature)
        return LLMResponse(
            content=response.content,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            raw={"tools": tools, "temperature": temperature},
        )


def _rough_token_count(text: str) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)
