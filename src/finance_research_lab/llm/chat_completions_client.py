from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .base import LLMResponse
from .usage import LLMUsageSession

UrlOpen = Callable[[Request, int], Any]

DEFAULT_LLM_BASE_URL = "https://api.openai.com/v1"
DEFAULT_LLM_MODEL = "gpt-4o-mini"
DEFAULT_LLM_RESPONSE_FORMAT = "json_schema"
DEFAULT_LLM_TIMEOUT_SECONDS = 60
SUPPORTED_RESPONSE_FORMATS = {"json_schema", "json_object"}


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
        response_format: str | None = None,
        timeout_seconds: int | None = None,
        urlopen: UrlOpen = _default_urlopen,
        env_path: str | Path = ".env",
        usage_session: LLMUsageSession | None = None,
    ) -> None:
        self.api_key = api_key or _config_value("LLM_API_KEY", env_path)
        self.model = model or _config_value("LLM_MODEL", env_path) or DEFAULT_LLM_MODEL
        self.base_url = (
            base_url or _config_value("LLM_BASE_URL", env_path) or DEFAULT_LLM_BASE_URL
        ).rstrip("/")
        self.response_format = (
            response_format
            or _config_value("LLM_RESPONSE_FORMAT", env_path)
            or DEFAULT_LLM_RESPONSE_FORMAT
        )
        if self.response_format not in SUPPORTED_RESPONSE_FORMATS:
            raise ValueError(f"Unsupported LLM_RESPONSE_FORMAT: {self.response_format}")
        self.timeout_seconds = timeout_seconds or _int_config_value(
            "LLM_TIMEOUT_SECONDS",
            env_path,
            DEFAULT_LLM_TIMEOUT_SECONDS,
        )
        self.urlopen = urlopen
        self.usage_session = usage_session

    def structured_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        schema_name: str,
        schema: dict[str, Any],
        temperature: float = 0.2,
        timeout: int | None = None,
        scope_id: str = "",
    ) -> LLMResponse:
        if not self.api_key:
            raise ValueError("LLM_API_KEY is not set")

        body = {
            "model": self.model,
            "messages": self._messages(messages, schema),
            "temperature": temperature,
            "response_format": self._response_format(schema_name, schema),
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
            with self.urlopen(request, timeout or self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
            self._record_failure(schema_name, scope_id, "transport_error")
            raise RuntimeError(f"LLM request failed: {exc}") from exc

        usage_tokens = _usage(payload)
        try:
            message = _response_message(payload)
        except RuntimeError as exc:
            self._record_failure(
                schema_name,
                scope_id,
                "invalid_response",
                model=_response_model(payload, self.model),
                usage_tokens=usage_tokens,
            )
            raise RuntimeError(f"LLM response was invalid: {exc}") from exc
        input_tokens, output_tokens, cache_hit_tokens, cache_miss_tokens = usage_tokens
        refusal = message.get("refusal")
        if refusal:
            self._record_failure(
                schema_name,
                scope_id,
                "provider_refusal",
                model=_response_model(payload, self.model),
                usage_tokens=usage_tokens,
            )
            raise RuntimeError(f"LLM refused structured response: {refusal}")

        content = message.get("content")
        if not isinstance(content, str):
            self._record_failure(
                schema_name,
                scope_id,
                "invalid_response",
                model=_response_model(payload, self.model),
                usage_tokens=usage_tokens,
            )
            raise RuntimeError("LLM response did not include text content")

        result = LLMResponse(
            content=content,
            model=str(payload.get("model", self.model)),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_input_tokens=cache_hit_tokens,
            cache_miss_input_tokens=cache_miss_tokens,
            raw=payload,
        )
        self._record_success(schema_name, scope_id, result)
        return result

    def tool_completion(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        temperature: float = 0.2,
        timeout: int | None = None,
        scope_id: str = "",
    ) -> LLMResponse:
        """Request one OpenAI-compatible tool-calling turn."""

        if not self.api_key:
            raise ValueError("LLM_API_KEY is not set")
        body = {
            "model": self.model,
            "messages": messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": temperature,
        }
        request = Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self.urlopen(request, timeout or self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, OSError, json.JSONDecodeError) as exc:
            self._record_failure("evidence_tools", scope_id, "transport_error")
            raise RuntimeError(f"LLM tool request failed: {exc}") from exc
        usage_tokens = _usage(payload)
        try:
            message = _response_message(payload)
        except RuntimeError as exc:
            self._record_failure(
                "evidence_tools",
                scope_id,
                "invalid_response",
                model=_response_model(payload, self.model),
                usage_tokens=usage_tokens,
            )
            raise RuntimeError(f"LLM tool response was invalid: {exc}") from exc
        if message.get("refusal"):
            self._record_failure(
                "evidence_tools",
                scope_id,
                "provider_refusal",
                model=_response_model(payload, self.model),
                usage_tokens=usage_tokens,
            )
            raise RuntimeError(f"LLM refused tool response: {message['refusal']}")
        input_tokens, output_tokens, cache_hit_tokens, cache_miss_tokens = usage_tokens
        result = LLMResponse(
            content=message.get("content") if isinstance(message.get("content"), str) else "",
            model=str(payload.get("model", self.model)),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_hit_input_tokens=cache_hit_tokens,
            cache_miss_input_tokens=cache_miss_tokens,
            raw=message,
        )
        self._record_success("evidence_tools", scope_id, result)
        return result

    def _record_success(
        self,
        operation: str,
        scope_id: str,
        response: LLMResponse,
    ) -> None:
        if self.usage_session is None:
            return
        self.usage_session.record_success(
            operation=operation,
            model=response.model,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            cache_hit_input_tokens=response.cache_hit_input_tokens,
            cache_miss_input_tokens=response.cache_miss_input_tokens,
            scope_id=scope_id,
        )

    def _record_failure(
        self,
        operation: str,
        scope_id: str,
        category: str,
        *,
        model: str | None = None,
        usage_tokens: tuple[int | None, int | None, int | None, int | None] = (
            None,
            None,
            None,
            None,
        ),
    ) -> None:
        if self.usage_session is None:
            return
        self.usage_session.record_failure(
            operation=operation,
            model=model or self.model,
            failure_category=category,
            scope_id=scope_id,
            input_tokens=usage_tokens[0],
            output_tokens=usage_tokens[1],
            cache_hit_input_tokens=usage_tokens[2],
            cache_miss_input_tokens=usage_tokens[3],
        )

    def _messages(
        self,
        messages: list[dict[str, Any]],
        schema: dict[str, Any],
    ) -> list[dict[str, str]]:
        if self.response_format != "json_object":
            return messages
        schema_text = json.dumps(schema, ensure_ascii=False)
        return [
            *messages,
            {
                "role": "system",
                "content": (
                    "Output json only. The response must be one JSON object and must include all "
                    f"required fields from this JSON Schema: {schema_text}"
                ),
            },
        ]

    def _response_format(self, schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:
        if self.response_format == "json_object":
            return {"type": "json_object"}
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": schema,
            },
        }


def _config_value(key: str, env_path: str | Path) -> str:
    value = os.environ.get(key)
    if value:
        return value
    return _read_dotenv(env_path).get(key, "")


def _optional_usage_int(usage: object, key: str) -> int | None:
    if not isinstance(usage, dict) or key not in usage:
        return None
    value = usage[key]
    if not isinstance(value, (int, float, str)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _response_message(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise RuntimeError("response must be a JSON object")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise RuntimeError("response did not include a choice")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise RuntimeError("response did not include a message")
    return message


def _usage(payload: object) -> tuple[int | None, int | None, int | None, int | None]:
    if not isinstance(payload, dict):
        return None, None, None, None
    usage = payload.get("usage", {})
    return (
        _optional_usage_int(usage, "prompt_tokens"),
        _optional_usage_int(usage, "completion_tokens"),
        _optional_usage_int(usage, "prompt_cache_hit_tokens"),
        _optional_usage_int(usage, "prompt_cache_miss_tokens"),
    )


def _response_model(payload: object, default: str) -> str:
    if not isinstance(payload, dict):
        return default
    return str(payload.get("model", default))


def _int_config_value(key: str, env_path: str | Path, default: int) -> int:
    value = _config_value(key, env_path)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer") from exc


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
