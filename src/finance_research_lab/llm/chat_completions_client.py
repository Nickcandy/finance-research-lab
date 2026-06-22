from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .base import LLMResponse

UrlOpen = Callable[[Request, int], Any]

DEFAULT_LLM_BASE_URL = "https://api.openai.com/v1"
DEFAULT_LLM_MODEL = "gpt-4o-mini"


def _default_urlopen(request: Request, timeout: int) -> Any:
    return urlopen(request, timeout=timeout)


class ChatCompletionsClient:
    """Minimal OpenAI-compatible Chat Completions client using stdlib only."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        urlopen: UrlOpen = _default_urlopen,
        env_path: str | Path = ".env",
    ) -> None:
        self.api_key = api_key or _config_value("LLM_API_KEY", env_path)
        self.model = model or _config_value("LLM_MODEL", env_path) or DEFAULT_LLM_MODEL
        self.base_url = (
            base_url or _config_value("LLM_BASE_URL", env_path) or DEFAULT_LLM_BASE_URL
        ).rstrip("/")
        self.urlopen = urlopen

    def structured_completion(
        self,
        *,
        messages: list[dict[str, str]],
        schema_name: str,
        schema: dict[str, Any],
        temperature: float = 0.2,
        timeout: int = 30,
    ) -> LLMResponse:
        if not self.api_key:
            raise ValueError("LLM_API_KEY is not set")

        body = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with self.urlopen(request, timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        message = payload.get("choices", [{}])[0].get("message", {})
        refusal = message.get("refusal")
        if refusal:
            raise RuntimeError(f"LLM refused structured response: {refusal}")

        content = message.get("content")
        if not isinstance(content, str):
            raise RuntimeError("LLM response did not include text content")

        usage = payload.get("usage", {})
        return LLMResponse(
            content=content,
            model=str(payload.get("model", self.model)),
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            raw=payload,
        )


def _config_value(key: str, env_path: str | Path) -> str:
    value = os.environ.get(key)
    if value:
        return value
    return _read_dotenv(env_path).get(key, "")


def _read_dotenv(path: str | Path) -> dict[str, str]:
    env_file = Path(path)
    if not env_file.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values
