"""Minimal OpenAI-compatible chat client for oMLX (standard library only)."""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

RETRY_STATUSES = frozenset({409, 429, 500, 502, 503, 504})
BUSY_STATUSES = frozenset({409})
ERROR_BODY_CHARS = 300

DEFAULT_RETRIES = 2
DEFAULT_BACKOFF_S = 3.0
DEFAULT_BUSY_BACKOFF_S = 15.0
DEFAULT_READY_TIMEOUT_S = 600.0
READY_POLL_INTERVAL_S = 5.0
MIN_READY_POLL_INTERVAL_S = 0.01

PROBE_MESSAGES = [{"role": "user", "content": "ping"}]
PROBE_MAX_TOKENS = 1


class ChatError(RuntimeError):
    """Raised when a chat request cannot be completed."""


class ChatClient:
    """Posts to /v1/chat/completions and returns the first choice plus usage.

    oMLX serves a thinking model, so a reply may carry `reasoning_content` next to
    (or instead of) `content`. Callers must decide what an empty `content` means;
    this client keeps both fields.

    A 409 means the model is busy (usually an unload still draining), so it is retried
    with its own, longer backoff. `opener` defaults to `urlopen` and is the seam tests
    use to replay server replies.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        *,
        timeout_s: float = 900.0,
        retries: int = DEFAULT_RETRIES,
        backoff_s: float = DEFAULT_BACKOFF_S,
        busy_backoff_s: float = DEFAULT_BUSY_BACKOFF_S,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._api_key = api_key
        self.timeout_s = timeout_s
        self.retries = max(int(retries), 0)
        self.backoff_s = backoff_s
        self.busy_backoff_s = busy_backoff_s
        self._opener = opener

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
        with self._opener(req, timeout=self.timeout_s) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def retry_delay_s(self, status: int, attempt: int) -> float:
        """Seconds to wait before retrying; a busy model (409) waits longer."""
        base = self.busy_backoff_s if status in BUSY_STATUSES else self.backoff_s
        return base * (attempt + 1)

    def chat(
        self,
        model: str,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int = 512,
        temperature: float = 0.0,
        retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return {content, reasoning, finish_reason, usage, latency_s}.

        `retries` overrides the client default for this call (0 for a single attempt).
        """
        body = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": False,
        }
        attempts = self.retries if retries is None else max(int(retries), 0)
        last_error: Optional[BaseException] = None
        for attempt in range(attempts + 1):
            started = time.monotonic()
            try:
                payload = self._post(body)
            except HTTPError as exc:
                last_error = exc
                message = _http_error_message(exc)
                if exc.code in RETRY_STATUSES and attempt < attempts:
                    delay = self.retry_delay_s(exc.code, attempt)
                    logger.warning("%s; retry %d in %.1fs", message, attempt + 1, delay)
                    time.sleep(delay)
                    continue
                raise ChatError(message) from exc
            except (OSError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < attempts:
                    delay = self.retry_delay_s(0, attempt)
                    logger.warning("Chat request failed (%s); retry %d in %.1fs", exc, attempt + 1, delay)
                    time.sleep(delay)
                    continue
                raise ChatError(f"chat request failed: {exc}") from exc
            latency = time.monotonic() - started
            return _normalize(payload, latency)
        raise ChatError(f"chat request failed: {last_error}")

    def wait_until_ready(
        self,
        model: str,
        *,
        timeout_s: float = DEFAULT_READY_TIMEOUT_S,
        interval_s: float = READY_POLL_INTERVAL_S,
    ) -> Dict[str, Any]:
        """Send a 1-token probe until the model answers, or raise ChatError at the deadline.

        oMLX unloads the model when its settings change. Until that unload drains the
        server refuses every request with 409 "busy; cannot start work while unload is
        pending", so a settings change must be followed by this wait before a block.
        """
        interval_s = max(float(interval_s), MIN_READY_POLL_INTERVAL_S)
        deadline = time.monotonic() + max(float(timeout_s), 0.0)
        last_error = "no probe sent"
        while True:
            try:
                reply = self.chat(
                    model,
                    PROBE_MESSAGES,
                    max_tokens=PROBE_MAX_TOKENS,
                    retries=0,
                )
            except ChatError as exc:
                last_error = str(exc)
                logger.warning("Model %s is not ready yet: %s", model, last_error)
            else:
                logger.info("Model %s answered a readiness probe", model)
                return reply
            if time.monotonic() >= deadline:
                raise ChatError(
                    f"model '{model}' did not answer a probe within {timeout_s:.0f}s: {last_error}"
                )
            time.sleep(interval_s)


def _read_error_body(exc: HTTPError) -> str:
    """Read the response body of an HTTPError once, as text."""
    try:
        raw = exc.read()
    except (AttributeError, OSError):
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw or "")


def _http_error_message(exc: HTTPError) -> str:
    """Error text with the status and the head of the server's own message."""
    head = f"HTTP {exc.code} from chat endpoint"
    body = _read_error_body(exc).strip()
    if not body:
        return head
    return f"{head}: {body[:ERROR_BODY_CHARS]}"


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
