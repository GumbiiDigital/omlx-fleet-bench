"""Tests for bench/helper_id.py, with a stubbed admin client (no server, no network)."""

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import patch

from bench import helper_id
from bench.client import OMLXClient

BASE_URL = "http://127.0.0.1:8004"
SETTINGS = "/fake/settings.json"
FULL_ID = "9f2c7a1b2c3d4e5f"


class _FakeClient:
    """The two calls the command makes, answered from a list held in memory."""

    def __init__(self, models: List[Dict[str, Any]]) -> None:
        self.models = models
        self.logins = 0
        self.asked: List[str] = []

    def login(self) -> None:
        self.logins += 1

    def list_models(self) -> List[Dict[str, Any]]:
        return self.models

    def get_model_settings(self, model: str) -> Dict[str, Any]:
        self.asked.append(model)
        # Read the list through `list_models`, as the real client does, so a stub that breaks the
        # list breaks both calls.
        for entry in self.list_models():
            if entry.get("id") == model:
                settings = entry.get("settings")
                return dict(settings) if isinstance(settings, dict) else {}
        return {}


def _entry(model: str, value: Any = None) -> Dict[str, Any]:
    """One model as the server lists it, with its settings."""
    return {"id": model, "settings": {helper_id.HELPER_ID_FIELD: value}}


def _paired(model: str, value: str) -> Dict[str, Any]:
    return _entry(model, value)


class HelperIdOfTest(unittest.TestCase):
    def test_it_reads_the_setting_the_server_keeps(self) -> None:
        self.assertEqual(helper_id.helper_id_of(_entry("m1", FULL_ID)["settings"]), FULL_ID)

    def test_a_missing_or_odd_value_reads_as_none(self) -> None:
        self.assertEqual(helper_id.helper_id_of({}), "")
        self.assertEqual(helper_id.helper_id_of(_entry("m1")["settings"]), "")
        self.assertEqual(helper_id.helper_id_of(_entry("m1", "   ")["settings"]), "")


class OneModelTest(unittest.TestCase):
    def test_it_prints_the_id_and_says_it_worked(self) -> None:
        client = _FakeClient([_paired("m1", FULL_ID)])
        out = io.StringIO()
        self.assertEqual(helper_id.print_helper_id(client, "m1", out), 0)
        self.assertEqual(out.getvalue().strip(), FULL_ID)

    def test_a_model_with_no_id_gets_the_plain_message_and_a_failure(self) -> None:
        client = _FakeClient([_entry("m1")])
        out = io.StringIO()
        self.assertEqual(helper_id.print_helper_id(client, "m1", out), 1)
        self.assertEqual(
            out.getvalue().strip(),
            "no helper id set for m1: pair the Spark in oMLX first",
        )

    def test_a_model_the_server_does_not_list_reads_the_same_way(self) -> None:
        client = _FakeClient([_paired("m1", FULL_ID)])
        out = io.StringIO()
        self.assertEqual(helper_id.print_helper_id(client, "absent", out), 1)
        self.assertIn("no helper id set for absent", out.getvalue())


class ModelListTest(unittest.TestCase):
    def test_every_model_gets_a_line_and_the_id_is_cut_short(self) -> None:
        client = _FakeClient([_paired("m1", FULL_ID), _entry("m2")])
        out = io.StringIO()
        self.assertEqual(helper_id.print_model_list(client, out), 0)
        lines = out.getvalue().splitlines()
        self.assertEqual(lines[0], "m1: helper id set, starts 9f2c")
        self.assertEqual(lines[1], "m2: no helper id set")
        self.assertNotIn(FULL_ID, out.getvalue())

    def test_it_says_when_no_model_has_an_id(self) -> None:
        client = _FakeClient([_entry("m1")])
        out = io.StringIO()
        self.assertEqual(helper_id.print_model_list(client, out), 0)
        self.assertIn("no model here has a helper id", out.getvalue())

    def test_a_server_with_no_models_says_so(self) -> None:
        out = io.StringIO()
        self.assertEqual(helper_id.print_model_list(_FakeClient([]), out), 0)
        self.assertIn("the server lists no models", out.getvalue())


class _Response:
    """One HTTP answer: a JSON body, read once."""

    def __init__(self, payload: Any) -> None:
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self._raw

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *args: object) -> None:
        return None


class _ScriptedOpener:
    """Answers each request by the end of its URL, the way the server's own routes would."""

    def __init__(self, routes: Dict[str, Any]) -> None:
        self.routes = routes
        self.calls: List[Tuple[str, str]] = []

    def open(self, request: Any, timeout: int = 0) -> _Response:
        self.calls.append((request.get_method(), request.full_url))
        for suffix, payload in self.routes.items():
            if request.full_url.endswith(suffix):
                return _Response(payload)
        raise OSError(f"no route for {request.full_url}")


class RealClientTest(unittest.TestCase):
    """The command against the real admin client, with the network replaced by a scripted opener.

    The payload is the shape the server answers `GET /admin/api/models` with, so a change to the
    client's reading of it (the `models` key, the per-model `settings` object) breaks this test.
    """

    MODELS = {
        "models": [
            {"id": "Qwen3.8-27B-oQ4e-mtp", "settings": {"prefill_helper_node_id": FULL_ID}},
            {"id": "Qwen3.8-Flash-Next-oQ4e-mtp", "settings": {}},
        ]
    }

    def _client(self) -> Tuple[OMLXClient, _ScriptedOpener]:
        opener = _ScriptedOpener({"/admin/api/login": {}, "/admin/api/models": self.MODELS})
        return OMLXClient(BASE_URL, "key", opener_factory=lambda: opener), opener

    def test_the_real_client_prints_the_id_from_a_models_answer(self) -> None:
        client, opener = self._client()
        client.login()
        out = io.StringIO()
        self.assertEqual(helper_id.print_helper_id(client, "Qwen3.8-27B-oQ4e-mtp", out), 0)
        self.assertEqual(out.getvalue().strip(), FULL_ID)
        self.assertEqual(opener.calls[0], ("POST", f"{BASE_URL}/admin/api/login"))
        self.assertIn(("GET", f"{BASE_URL}/admin/api/models"), opener.calls)

    def test_the_real_client_lists_both_models(self) -> None:
        client, _ = self._client()
        out = io.StringIO()
        self.assertEqual(helper_id.print_model_list(client, out), 0)
        self.assertIn("Qwen3.8-Flash-Next-oQ4e-mtp: no helper id set", out.getvalue())


class MainTest(unittest.TestCase):
    def _run(
        self,
        argv: List[str],
        client: Any = None,
        key_error: Optional[Exception] = None,
        key: str = "key",
    ) -> Any:
        """Run main with the client and the key stubbed, returning its code and both streams."""
        out, err = io.StringIO(), io.StringIO()
        with patch("bench.helper_id.load_api_key", return_value=key) as load:
            load.side_effect = key_error
            with patch("bench.helper_id.OMLXClient", return_value=client) as built:
                with redirect_stdout(out), redirect_stderr(err):
                    code = helper_id.main(argv)
        return code, out.getvalue(), err.getvalue(), built, load

    def test_it_reads_the_key_from_the_settings_file_and_logs_in(self) -> None:
        client = _FakeClient([_paired("m1", FULL_ID)])
        code, out, _, built, load = self._run(
            ["--base-url", BASE_URL, "--settings", SETTINGS, "--model", "m1"], client
        )
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), FULL_ID)
        self.assertEqual(client.logins, 1)
        built.assert_called_once_with(BASE_URL, "key")
        load.assert_called_once_with(SETTINGS)

    def test_with_no_model_it_lists_every_model(self) -> None:
        client = _FakeClient([_paired("m1", FULL_ID), _entry("m2")])
        code, out, _, _, _ = self._run(["--base-url", BASE_URL, "--settings", SETTINGS], client)
        self.assertEqual(code, 0)
        self.assertEqual(sorted(client.asked), ["m1", "m2"])
        self.assertIn("m2: no helper id set", out)

    def test_an_unreachable_server_is_a_clear_message_and_a_failure(self) -> None:
        class _Down(_FakeClient):
            def login(self) -> None:
                raise OSError("connection refused")

        code, _, err, _, _ = self._run(
            ["--base-url", BASE_URL, "--settings", SETTINGS, "--model", "m1"], _Down([])
        )
        self.assertEqual(code, 2)
        self.assertIn("could not read the server: connection refused", err)

    def test_a_model_list_that_fails_after_login_is_a_message_and_a_failure(self) -> None:
        # Login worked; the answer to the model list did not arrive. Exit 1 would read as "no helper
        # id set", so it must be 2 with a plain reason and no traceback.
        class _ListFails(_FakeClient):
            def list_models(self) -> List[Dict[str, Any]]:
                raise OSError("connection reset by peer")

        code, out, err, _, _ = self._run(
            ["--base-url", BASE_URL, "--settings", SETTINGS, "--model", "m1"], _ListFails([])
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("could not read the server: connection reset by peer", err)

    def test_a_model_settings_read_that_fails_is_a_message_and_a_failure(self) -> None:
        class _SettingsFail(_FakeClient):
            def get_model_settings(self, model: str) -> Dict[str, Any]:
                raise ValueError("Expecting value: line 1 column 1 (char 0)")

        code, out, err, _, _ = self._run(
            ["--base-url", BASE_URL, "--settings", SETTINGS, "--model", "m1"], _SettingsFail([])
        )
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("could not read the server:", err)
        self.assertNotIn("Traceback", err)

    def test_a_failed_read_never_prints_the_key(self) -> None:
        class _ListFails(_FakeClient):
            def list_models(self) -> List[Dict[str, Any]]:
                raise OSError("connection reset by peer")

        code, _, err, _, _ = self._run(
            ["--base-url", BASE_URL, "--settings", SETTINGS], _ListFails([]), key="SUPER_SECRET_KEY"
        )
        self.assertEqual(code, 2)
        self.assertNotIn("SUPER_SECRET_KEY", err)

    def test_a_settings_file_with_no_key_is_a_message_not_a_traceback(self) -> None:
        code, _, err, _, _ = self._run(
            ["--base-url", BASE_URL, "--settings", SETTINGS], key_error=ValueError("Missing auth.api_key")
        )
        self.assertEqual(code, 2)
        self.assertIn("could not read the server: Missing auth.api_key", err)


if __name__ == "__main__":
    unittest.main()
