"""Tests for oMLX admin client (mocked HTTP)."""

import io
import json
import logging
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from urllib.request import HTTPCookieProcessor

from bench.client import OMLXClient, cookie_opener, load_api_key


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class TestClient(unittest.TestCase):
    def test_load_api_key(self) -> None:
        with patch("builtins.open", unittest.mock.mock_open(read_data='{"auth":{"api_key":"sekret"}}')):
            self.assertEqual(load_api_key("/fake/settings.json"), "sekret")

    def test_start_benchmark_forces_align_true(self) -> None:
        seen: List[Dict[str, Any]] = []

        def fake_json_request(opener: Any, method: str, url: str, body: Dict[str, Any] = None) -> Any:
            if body is not None:
                seen.append(body)
            if url.endswith("/login"):
                return {}
            if url.endswith("/start"):
                return {"bench_id": "bench-test123"}
            return {}

        opener = MagicMock()
        with patch("bench.client._json_request", side_effect=fake_json_request):
            client = OMLXClient("http://example:8004", "sekret", opener_factory=lambda: opener)
            with self.assertRaises(ValueError):
                client.start_benchmark("model", 8192, align_prompt_to_ane=False)
            bid = client.start_benchmark("model", 32768)
            self.assertEqual(bid, "bench-test123")
        self.assertTrue(seen[-1]["align_prompt_to_ane"])

    def test_preserved_settings_restores_only_touched_fields(self) -> None:
        calls: List[Dict[str, Any]] = []

        def fake_json_request(opener: Any, method: str, url: str, body: Dict[str, Any] = None) -> Any:
            if url.endswith("/models"):
                return {"models": [{"id": "m1", "settings": {
                    "prefill_helper_node_id": "orig", "display_name": "x", "is_default": True}}]}
            if method == "PUT":
                calls.append(dict(body))
            return {}

        opener = MagicMock()
        with patch("bench.client._json_request", side_effect=fake_json_request):
            client = OMLXClient("http://example:8004", "sekret", opener_factory=lambda: opener)
            with self.assertRaises(RuntimeError):
                with client.preserved_settings("m1", ["prefill_helper_node_id"]):
                    client.apply_settings("m1", {"prefill_helper_node_id": "temp"}, ["prefill_helper_node_id"])
                    raise RuntimeError("boom")
        self.assertEqual(calls, [{"prefill_helper_node_id": "temp"}, {"prefill_helper_node_id": "orig"}])

    def test_helper_state_read_uses_the_model_endpoint(self) -> None:
        seen: List[Any] = []

        def fake_json_request(opener: Any, method: str, url: str, body: Dict[str, Any] = None) -> Any:
            seen.append((method, url))
            return {"state": "ready", "held": 63}

        opener = MagicMock()
        with patch("bench.client._json_request", side_effect=fake_json_request):
            client = OMLXClient("http://example:8004", "sekret", opener_factory=lambda: opener)
            state = client.get_prefill_helper_state("m1")
        self.assertEqual(state, {"state": "ready", "held": 63})
        self.assertEqual(seen[-1], ("GET", "http://example:8004/admin/api/prefill-helper/models/m1"))

    def test_helper_state_read_is_none_for_an_odd_answer(self) -> None:
        opener = MagicMock()
        with patch("bench.client._json_request", side_effect=lambda *a, **kw: ["ready"]):
            client = OMLXClient("http://example:8004", "sekret", opener_factory=lambda: opener)
            self.assertIsNone(client.get_prefill_helper_state("m1"))

    def test_default_opener_keeps_cookies(self) -> None:
        opener = cookie_opener()
        self.assertTrue(any(isinstance(h, HTTPCookieProcessor) for h in opener.handlers))

    def test_api_key_not_logged(self) -> None:
        log_stream = io.StringIO()
        handler = logging.StreamHandler(log_stream)
        root = logging.getLogger("bench.client")
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            def fake_json_request(opener: Any, method: str, url: str, body: Dict[str, Any] = None) -> Any:
                return {}

            opener = MagicMock()
            with patch("bench.client._json_request", side_effect=fake_json_request):
                client = OMLXClient("http://example:8004", "SUPER_SECRET_KEY", opener_factory=lambda: opener)
                client.login()
        finally:
            root.removeHandler(handler)
        output = log_stream.getvalue()
        self.assertNotIn("SUPER_SECRET_KEY", output)


if __name__ == "__main__":
    unittest.main()