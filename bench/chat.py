"""Minimal OpenAI-compatible chat client for oMLX (standard library only)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})


class ChatError(RuntimeError):
    """Raised when a chat request cannot be completed."""


class ChatClient:
    """Posts to /v1/chat/completions and returns the first choice plus usage.

    oMLX serves a thinking model, so a reply may carry `reasoning_content` next to
    (or instead of) `content`. Callers must decide what an empty `content` means;
    this client keeps both fields.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_s: float = 900.0,
        retries: int = 2,
        backoff_s: float = 3.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout_s = timeout_s
        self.retries = retries
        self.backoff_s = backoff_s

    def _post(self, body: Dict[str, Any]) -> Dict[str, Any]:
        data = json.dumps(body).encode("utf-8")
        req = Request(
            f"{self.base_url}/v1/chat/completions",
            data=data,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urlopen(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """Return {content, reasoning, finish_reason, usage, latency_s}."""
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        last_error: Optional[BaseException] = None
        for attempt in range(self.retries + 1):
            started = time.monotonic()
            try:
                payload = self._post(body)
            except HTTPError as exc:
                last_error = exc
                if exc.code in RETRY_STATUSES and attempt < self.retries:
                    logger.warning("HTTP %s from chat, retry %d", exc.code, attempt + 1)
                    time.sleep(self.backoff_s * (attempt + 1))
                    continue
                raise ChatError(f"HTTP {exc.code} from chat endpoint") from exc
            except (URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.retries:
                    logger.warning("Chat request failed (%s), retry %d", exc, attempt + 1)
                    time.sleep(self.backoff_s * (attempt + 1))
                    continue
                raise ChatError(f"chat request failed: {exc}") from exc
            latency = time.monotonic() - started
            return _normalize(payload, latency)
        raise ChatError(f"chat request failed: {last_error}")


def _normalize(payload: Dict[str, Any], latency_s: float) -> Dict[str, Any]:
    choices = payload.get("choices") or []
    if not choices:
        raise ChatError(f"no choices in chat response: {list(payload)[:6]}")
    first = choices[0] or {}
    message = first.get("message") or {}
    usage = payload.get("usage") or {}
    return {
        "content": message.get("content") or "",
        "reasoning": message.get("reasoning_content") or "",
        "finish_reason": first.get("finish_reason"),
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "cached_tokens": (usage.get("prompt_tokens_details") or {}).get("cached_tokens"),
        },
        "server_timing": {
            key: usage.get(key)
            for key in ("time_to_first_token", "total_time", "prompt_tokens_per_second")
            if key in usage
        },
        "latency_s": round(latency_s, 3),
    }
