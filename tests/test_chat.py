"""Tests for the chat client: retries, error text, and the readiness probe.

The HTTP layer is a scripted fake, so a 409 "busy; unload pending" reply can be
replayed without a server.
"""

import io
import json
import unittest
from email.message import Message
from typing import Any, Dict, Sequence, Union
from urllib.error import HTTPError

from bench.chat import ChatClient, ChatError

MODEL = "test-model"
PROBE_MESSAGES = [{"role": "user", "content": "hi"}]


class _FakeResponse:
    def __init__(self, payload: Dict[str, Any]) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _Fail:
    """One scripted HTTP error outcome."""

    def __init__(self, code: int, body: str = "") -> None:
        self.code = code
        self.body = body


def _reply(text: str = "pong") -> Dict[str, Any]:
    return {
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 1},
    }


class _ScriptedOpener:
    """Fake urlopen: plays queued outcomes, repeats the last one, counts calls."""

    def __init__(self, outcomes: Sequence[Union[Dict[str, Any], _Fail]]) -> None:
        self._outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, req: Any, timeout: Any = None) -> _FakeResponse:
        index = min(self.calls, len(self._outcomes) - 1)
        self.calls += 1
        outcome = self._outcomes[index]
        if isinstance(outcome, _Fail):
            raise HTTPError(
                req.full_url,
                outcome.code,
                "scripted",
                Message(),
                io.BytesIO(outcome.body.encode("utf-8")),
            )
        return _FakeResponse(outcome)


def _client(opener: Any, **kwargs: Any) -> ChatClient:
    kwargs.setdefault("retries", 2)
    kwargs.setdefault("backoff_s", 0.0)
    kwargs.setdefault("busy_backoff_s", 0.0)
    kwargs.setdefault("timeout_s", 5.0)
    return ChatClient("http://example:8004", "test-key", opener=opener, **kwargs)


class ChatRetryTest(unittest.TestCase):
    def test_409_then_200_returns_reply(self) -> None:
        opener = _ScriptedOpener([_Fail(409, '{"detail":"busy; unload pending"}'), _reply("#### 18")])
        out = _client(opener).chat(MODEL, PROBE_MESSAGES)
        self.assertEqual(out["content"], "#### 18")
        self.assertEqual(opener.calls, 2)

    def test_client_error_is_not_retried(self) -> None:
        opener = _ScriptedOpener([_Fail(400, '{"detail":"bad prompt"}')])
        with self.assertRaises(ChatError):
            _client(opener).chat(MODEL, PROBE_MESSAGES)
        self.assertEqual(opener.calls, 1)

    def test_busy_backoff_is_longer_than_plain_backoff(self) -> None:
        client = ChatClient(
            "http://example:8004", "test-key", backoff_s=1.0, busy_backoff_s=7.0
        )
        self.assertEqual(client.retry_delay_s(409, 0), 7.0)
        self.assertEqual(client.retry_delay_s(500, 0), 1.0)


class ChatErrorMessageTest(unittest.TestCase):
    def test_error_text_has_status_and_body_head(self) -> None:
        body = '{"detail":"' + "x" * 400 + '"}'
        opener = _ScriptedOpener([_Fail(400, body)])
        with self.assertRaises(ChatError) as caught:
            _client(opener).chat(MODEL, PROBE_MESSAGES)
        text = str(caught.exception)
        self.assertIn("400", text)
        self.assertIn(body[:300], text)
        self.assertNotIn(body[:340], text)


class WaitUntilReadyTest(unittest.TestCase):
    def test_waits_through_busy_until_probe_answers(self) -> None:
        opener = _ScriptedOpener([_Fail(409, "busy"), _Fail(409, "busy"), _reply("pong")])
        out = _client(opener).wait_until_ready(MODEL, timeout_s=5.0, interval_s=0.001)
        self.assertEqual(out["content"], "pong")
        self.assertEqual(opener.calls, 3)

    def test_gives_up_after_timeout_with_clear_error(self) -> None:
        opener = _ScriptedOpener([_Fail(409, "busy; unload pending")])
        with self.assertRaises(ChatError) as caught:
            _client(opener).wait_until_ready(MODEL, timeout_s=0.05, interval_s=0.01)
        text = str(caught.exception)
        self.assertIn("did not answer", text)
        self.assertIn("409", text)
        self.assertGreater(opener.calls, 1)


if __name__ == "__main__":
    unittest.main()
