"""Bounded OpenAI-compatible gateway; no workflow or tenant policy lives here."""

import asyncio
import json
import logging
import math
import time
from collections.abc import AsyncIterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.core.config import settings

logger = logging.getLogger(__name__)
MAX_COMPLETION_TOKENS = 2048
MAX_RESPONSE_CHARACTERS = 16_000
MAX_REPORTED_TOKEN_COUNT = 10_000_000
MAX_EXECUTION_CALLS = 3
MAX_EXECUTION_PROMPT_TOKENS = 12_000
MAX_EXECUTION_COMPLETION_TOKENS = 1_200


@dataclass
class _ExecutionTokenBudget:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def reserve(self, messages: list[dict[str, str]], max_tokens: int) -> None:
        estimated_prompt_tokens = sum((len(message["content"]) + 3) // 4 for message in messages)
        if (
            self.calls >= MAX_EXECUTION_CALLS
            or self.prompt_tokens + estimated_prompt_tokens > MAX_EXECUTION_PROMPT_TOKENS
            or self.completion_tokens + max_tokens > MAX_EXECUTION_COMPLETION_TOKENS
        ):
            raise AIProviderError(
                "execution_token_budget_exceeded",
                "AI execution token budget was exceeded",
            )
        self.calls += 1
        self.prompt_tokens += estimated_prompt_tokens
        self.completion_tokens += max_tokens


_current_execution_budget: ContextVar[_ExecutionTokenBudget | None] = ContextVar(
    "ai_execution_token_budget", default=None
)


class AIProviderError(RuntimeError):
    """Provider failure carrying a safe, stable diagnostic code."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@contextmanager
def execution_token_budget():
    """Bound aggregate model calls for one durable AI execution."""
    token = _current_execution_budget.set(_ExecutionTokenBudget())
    try:
        yield
    finally:
        _current_execution_budget.reset(token)


class _CompletionContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=1, max_length=MAX_RESPONSE_CHARACTERS)

    @field_validator("content")
    @classmethod
    def content_is_plain_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or "\x00" in normalized:
            raise ValueError("completion content is empty or malformed")
        return normalized


def is_provider_configured() -> bool:
    return bool(settings.ai_provider_base_url and settings.ai_model)


def _safe_usage(raw_usage: object) -> dict[str, int]:
    if not isinstance(raw_usage, dict):
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    result: dict[str, int] = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = raw_usage.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or (isinstance(value, float) and not math.isfinite(value)):
            value = 0
        result[key] = min(MAX_REPORTED_TOKEN_COUNT, max(0, int(value)))
    return result


def _prepare_request(messages: list[dict[str, str]], max_tokens: int) -> tuple[str, dict[str, str]]:
    if not 1 <= max_tokens <= MAX_COMPLETION_TOKENS:
        raise ValueError("max_tokens is outside the configured completion budget")
    if not messages or any(
        not isinstance(message, dict)
        or set(message) != {"role", "content"}
        or message.get("role") not in {"system", "user", "assistant"}
        or not isinstance(message.get("content"), str)
        or len(message["content"]) > MAX_RESPONSE_CHARACTERS
        for message in messages
    ):
        raise ValueError("AI messages do not match the bounded provider contract")
    budget = _current_execution_budget.get()
    if budget is not None:
        budget.reserve(messages, max_tokens)

    base_url = (settings.ai_provider_base_url or "").rstrip("/")
    if not base_url or not settings.ai_model:
        raise AIProviderError("provider_not_configured", "AI provider is not configured")
    parsed_url = urlsplit(base_url)
    local_http_host = parsed_url.scheme == "http" and parsed_url.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }
    if (
        (parsed_url.scheme != "https" and not local_http_host)
        or not parsed_url.hostname
        or parsed_url.username
        or parsed_url.password
        or parsed_url.query
        or parsed_url.fragment
    ):
        raise AIProviderError(
            "provider_url_invalid",
            "AI provider URL must use HTTPS outside local development",
        )
    headers = {"content-type": "application/json"}
    if settings.ai_provider_api_key:
        headers["authorization"] = f"Bearer {settings.ai_provider_api_key.get_secret_value()}"
    return f"{base_url}/chat/completions", headers


async def generate_completion(
    messages: list[dict[str, str]], *, max_tokens: int = 400
) -> tuple[str, dict[str, int], str | None]:
    """Call the configured provider with bounded output, timeout, and safe telemetry."""
    import httpx

    url, headers = _prepare_request(messages, max_tokens)
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=settings.ai_provider_timeout_seconds) as client:
            response = await client.post(
                url,
                headers=headers,
                json={
                    "model": settings.ai_model,
                    "messages": messages,
                    "max_completion_tokens": max_tokens,
                },
            )
    except httpx.TimeoutException as exc:
        logger.warning(
            "ai_provider_request_failed provider=openai_compatible model=%s code=provider_timeout elapsed_ms=%d",
            settings.ai_model,
            round((time.monotonic() - started) * 1000),
        )
        raise AIProviderError("provider_timeout", "AI provider request timed out") from exc
    except httpx.RequestError as exc:
        logger.warning(
            "ai_provider_request_failed provider=openai_compatible model=%s code=provider_unreachable elapsed_ms=%d",
            settings.ai_model,
            round((time.monotonic() - started) * 1000),
        )
        raise AIProviderError("provider_unreachable", "AI provider could not be reached") from exc
    elapsed_ms = round((time.monotonic() - started) * 1000)
    if response.is_error:
        logger.warning(
            "ai_provider_request_failed provider=openai_compatible model=%s code=provider_http_%d elapsed_ms=%d",
            settings.ai_model,
            response.status_code,
            elapsed_ms,
        )
        raise AIProviderError(
            f"provider_http_{response.status_code}",
            f"AI provider returned HTTP {response.status_code}",
        )
    try:
        body = response.json()
        if not isinstance(body, dict):
            raise TypeError("invalid response root")
        choices = body.get("choices")
        first_choice = choices[0] if isinstance(choices, list) and choices else None
        message = first_choice.get("message") if isinstance(first_choice, dict) else None
        validated = _CompletionContent.model_validate(
            {"content": message.get("content") if isinstance(message, dict) else None}
        )
    except (ValueError, TypeError, ValidationError, json.JSONDecodeError) as exc:
        logger.warning(
            "ai_provider_request_failed provider=openai_compatible model=%s code=provider_invalid_response elapsed_ms=%d",
            settings.ai_model,
            elapsed_ms,
        )
        raise AIProviderError(
            "provider_invalid_response", "AI provider returned an invalid response"
        ) from exc

    usage = _safe_usage(body.get("usage"))
    logger.info(
        "ai_provider_request_completed provider=openai_compatible model=%s elapsed_ms=%d prompt_tokens=%d completion_tokens=%d total_tokens=%d",
        settings.ai_model,
        elapsed_ms,
        usage["prompt_tokens"],
        usage["completion_tokens"],
        usage["total_tokens"],
    )
    return validated.content, usage, settings.ai_model

@dataclass(frozen=True)
class CompletionDelta:
    text: str


@dataclass(frozen=True)
class CompletionEnd:
    usage: dict[str, int]
    model_name: str | None


async def stream_completion(
    messages: list[dict[str, str]], *, max_tokens: int = 400
) -> AsyncIterator[CompletionDelta | CompletionEnd]:
    """Read actual provider deltas with bounded framing, output, and wall time."""
    import httpx

    url, headers = _prepare_request(messages, max_tokens)
    usage: dict[str, int] = {}
    characters = 0
    finished = False
    try:
        async with asyncio.timeout(settings.ai_provider_timeout_seconds):
            async with httpx.AsyncClient(timeout=settings.ai_provider_timeout_seconds) as client:
                async with client.stream(
                    "POST", url, headers=headers, json={
                        "model": settings.ai_model, "messages": messages,
                        "max_completion_tokens": max_tokens, "stream": True,
                        "stream_options": {"include_usage": True},
                    },
                ) as response:
                    if not response.is_success:
                        raise AIProviderError(
                            f"provider_http_{response.status_code}", "AI streaming request failed"
                        )
                    buffer = b""
                    received = 0
                    async for chunk in response.aiter_bytes(chunk_size=None):
                        received += len(chunk)
                        if received > 2_000_000:
                            raise ValueError("stream exceeds wire limit")
                        buffer += chunk
                        while b"\n" in buffer:
                            raw, buffer = buffer.split(b"\n", 1)
                            if not raw.startswith(b"data:"):
                                continue
                            data = raw[5:].strip()
                            if data == b"[DONE]":
                                if not finished or not characters:
                                    raise ValueError("stream has no completed answer")
                                yield CompletionEnd(usage, settings.ai_model)
                                return
                            event = json.loads(data)
                            if not isinstance(event, dict) or "error" in event:
                                raise ValueError("invalid stream event")
                            if event.get("usage") is not None:
                                usage = _safe_usage(event["usage"])
                            choices = event.get("choices", [])
                            if not isinstance(choices, list) or len(choices) > 1:
                                raise ValueError("invalid stream choices")
                            if not choices:
                                continue
                            choice = choices[0]
                            if not isinstance(choice, dict) or not isinstance(choice.get("delta"), dict):
                                raise ValueError("invalid stream delta")
                            delta = choice["delta"].get("content")
                            if delta is not None and (not isinstance(delta, str) or "\x00" in delta):
                                raise ValueError("invalid stream content")
                            reason = choice.get("finish_reason")
                            if reason not in {None, "stop", "length"}:
                                raise ValueError("provider blocked or interrupted completion")
                            if delta:
                                characters += len(delta)
                                if characters > 12_000 or finished:
                                    raise ValueError("invalid stream output length")
                                yield CompletionDelta(delta)
                            finished = finished or reason in {"stop", "length"}
                        if len(buffer) > 64_000:
                            raise ValueError("stream line exceeds limit")
    except (httpx.TimeoutException, TimeoutError) as exc:
        raise AIProviderError("provider_timeout", "AI stream timed out") from exc
    except httpx.RequestError as exc:
        raise AIProviderError("provider_unreachable", "AI stream was interrupted") from exc
    except (TypeError, ValueError) as exc:
        raise AIProviderError("provider_invalid_response", "AI stream returned invalid data") from exc
    raise AIProviderError("provider_unreachable", "AI stream ended before completion")
