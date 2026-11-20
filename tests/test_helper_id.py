"""Tests for bench/helper_id.py, with a stubbed admin client (no server, no network)."""

import io
import unittest
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from bench import helper_id

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
        for entry in self.models:
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


class MainTest(unittest.TestCase):
    def _run(self, argv: List[str], client: Any = None, key_error: Optional[Exception] = None) -> Any:
        """Run main with the client and the key stubbed, returning its code and both streams."""
        out, err = io.StringIO(), io.StringIO()
        with patch("bench.helper_id.load_api_key", return_value="key") as load:
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
        self.assertIn("could not reach", err)

    def test_a_settings_file_with_no_key_is_a_message_not_a_traceback(self) -> None:
        code, _, err, _, _ = self._run(
            ["--base-url", BASE_URL, "--settings", SETTINGS], key_error=ValueError("Missing auth.api_key")
        )
        self.assertEqual(code, 2)
        self.assertIn("could not read the API key", err)


if __name__ == "__main__":
    unittest.main()
