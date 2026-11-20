"""Tests for the request-level reading of a row: its wait, its setting, its helper state."""

import unittest

from bench import latency


def _chat_row(
    *,
    ttft: float,
    size=32768,
    helper=True,
    layers=None,
    state="ready",
    wait=0.0,
    status="completed",
    correct=True,
    cached=0,
    machine="box",
):
    return {
        "machine": machine,
        "helper_on": helper,
        "ane_on": False,
        "helper_state": state if helper else None,
        "helper_wait_s": wait,
        "helper_layers": layers,
        "desired_settings": {"prefill_helper_layers": layers},
        "target_tokens": size,
        "status": status,
        "correct": correct,
        "usage": {"cached_tokens": cached, "prompt_tokens": 100},
        "server_timing": {"time_to_first_token": ttft},
    }


def _speed_row(*, ttft_ms, size=32768, helper=True, valid=True, checks=None, machine="box"):
    row = {
        "machine": machine,
        "helper_on": helper,
        "helper_state": "ready" if helper else None,
        "helper_wait_s": 0.0,
        "helper_layers": None,
        "desired_settings": {"prefill_helper_layers": None},
        "prompt_size": size,
        "metrics": {"ttft_ms": ttft_ms},
        "validity": {"valid": valid, **(checks or {})},
    }
    return row


class PromptSizeTest(unittest.TestCase):
    def test_a_speed_row_gives_its_prompt_size(self):
        self.assertEqual(latency.prompt_size(_speed_row(ttft_ms=1000.0, size=8192)), 8192)

    def test_a_chat_row_gives_the_size_it_asked_for(self):
        self.assertEqual(latency.prompt_size(_chat_row(ttft=1.0, size=131072)), 131072)

    def test_a_short_chat_request_gives_the_size_it_read(self):
        row = _chat_row(ttft=1.0, size=None)
        self.assertEqual(latency.prompt_size(row), 100)

    def test_a_row_with_no_size_is_an_error(self):
        row = _chat_row(ttft=1.0)
        row.pop("target_tokens")
        row.pop("usage")
        with self.assertRaises(ValueError):
            latency.prompt_size(row)


class SettingTest(unittest.TestCase):
    def test_a_row_with_the_helper_off_is_the_mac_alone(self):
        self.assertEqual(latency.setting_of(_chat_row(ttft=1.0, helper=False)), "mac-alone")

    def test_no_layer_count_asked_for_is_the_automatic_setting(self):
        self.assertEqual(latency.setting_of(_chat_row(ttft=1.0, layers=None)), "automatic")

    def test_a_pinned_layer_count_names_its_setting(self):
        self.assertEqual(latency.setting_of(_chat_row(ttft=1.0, layers=32)), "layers-32")

    def test_a_layer_count_read_from_a_string_is_read_as_a_number(self):
        row = _chat_row(ttft=1.0, layers="49")
        self.assertEqual(latency.setting_of(row), "layers-49")


class TtftTest(unittest.TestCase):
    def test_a_speed_row_gives_milliseconds_as_seconds(self):
        self.assertAlmostEqual(latency.ttft_s(_speed_row(ttft_ms=29500.0)), 29.5)

    def test_a_chat_row_gives_the_servers_own_seconds(self):
        self.assertAlmostEqual(latency.ttft_s(_chat_row(ttft=109.7)), 109.7)

    def test_a_row_with_no_wait_is_an_error(self):
        with self.assertRaises(ValueError):
            latency.ttft_s({"machine": "box", "prompt_size": 8192})


class FailedChecksTest(unittest.TestCase):
    def test_a_speed_row_names_the_checks_its_validity_block_failed(self):
        row = _speed_row(ttft_ms=29500.0, valid=False, checks={"helper_ready_at_start": False})
        self.assertEqual(latency.failed_checks(row), ("helper_ready_at_start",))

    def test_a_valid_speed_row_fails_nothing(self):
        self.assertEqual(latency.failed_checks(_speed_row(ttft_ms=29500.0)), ())

    def test_a_chat_row_is_checked_on_what_it_records(self):
        self.assertEqual(latency.failed_checks(_chat_row(ttft=1.0, cached=140)), ("cached_tokens_zero",))
        self.assertEqual(latency.failed_checks(_chat_row(ttft=1.0, correct=False)), ("answer_correct",))
        self.assertEqual(latency.failed_checks(_chat_row(ttft=1.0, status="error")), ("status_completed",))

    def test_a_chat_row_that_records_nothing_wrong_fails_nothing(self):
        self.assertEqual(latency.failed_checks(_chat_row(ttft=1.0)), ())


class RequestTest(unittest.TestCase):
    def test_a_request_carries_the_path_and_arm_it_was_run_in(self):
        request = latency.from_row(_chat_row(ttft=29.31), path="chat", arm="wait")
        self.assertEqual((request.path, request.arm, request.size), ("chat", "wait", 32768))
        self.assertEqual((request.setting, request.helper_state), ("automatic", "ready"))
        self.assertTrue(request.valid)
        self.assertTrue(request.correct)
        self.assertEqual(request.cached_tokens, 0)

    def test_a_speed_row_records_its_checks(self):
        request = latency.from_row(_speed_row(ttft_ms=29500.0), path="speed test", arm="no wait")
        self.assertTrue(request.checks_recorded)

    def test_a_chat_row_records_no_checks(self):
        request = latency.from_row(_chat_row(ttft=29.31), path="chat", arm="wait")
        self.assertFalse(request.checks_recorded)

    def test_a_not_valid_request_keeps_its_failed_checks(self):
        row = _speed_row(ttft_ms=29500.0, valid=False, checks={"helper_ready_at_start": False})
        request = latency.from_row(row, path="speed test", arm="no wait")
        self.assertFalse(request.valid)
        self.assertEqual(request.failed, ("helper_ready_at_start",))


class GroupTest(unittest.TestCase):
    def _requests(self):
        rows = [
            (_chat_row(ttft=109.70, state="connecting"), "chat", "no wait"),
            (_chat_row(ttft=109.76, state="connecting"), "chat", "no wait"),
            (_chat_row(ttft=29.31, state="ready", wait=20.0), "chat", "wait"),
            (_chat_row(ttft=29.93, state="ready", wait=20.2), "chat", "wait"),
        ]
        return [latency.from_row(row, path=path, arm=arm) for row, path, arm in rows]

    def test_a_group_counts_its_requests_and_their_waits(self):
        groups = latency.group_requests(self._requests(), lambda r: r.arm)
        self.assertEqual(groups["no wait"].requests, 2)
        self.assertAlmostEqual(groups["no wait"].mean_ttft_s, 109.73)
        self.assertEqual((groups["no wait"].low_ttft_s, groups["no wait"].high_ttft_s), (109.70, 109.76))
        self.assertAlmostEqual(groups["wait"].mean_wait_s, 20.1)

    def test_the_help_text_names_each_state_and_its_share(self):
        groups = latency.group_requests(self._requests(), lambda r: r.arm)
        self.assertEqual(groups["no wait"].state_text, "not ready yet, still connecting (2 of 2)")
        self.assertEqual(groups["wait"].state_text, "ready (2 of 2)")

    def test_a_group_of_mixed_states_names_both(self):
        rows = [_chat_row(ttft=1.0, state="ready"), _chat_row(ttft=1.0, state="starting")]
        groups = latency.group_requests([latency.from_row(r, path="chat", arm="a") for r in rows], lambda r: r.arm)
        self.assertEqual(groups["a"].state_text, "ready (1 of 2) · not ready yet, still starting (1 of 2)")

    def test_the_layers_taken_are_listed_one_by_one_when_they_differ(self):
        rows = [_chat_row(ttft=1.0, layers=50), _chat_row(ttft=1.0, layers=49), _chat_row(ttft=1.0, layers=49)]
        groups = latency.group_requests([latency.from_row(r, path="chat", arm="a") for r in rows], lambda r: r.arm)
        self.assertEqual(groups["a"].layers_text, "50, 49, 49")

    def test_one_layer_count_is_named_once(self):
        rows = [_chat_row(ttft=1.0, layers=32), _chat_row(ttft=1.0, layers=32)]
        groups = latency.group_requests([latency.from_row(r, path="chat", arm="a") for r in rows], lambda r: r.arm)
        self.assertEqual(groups["a"].layers_text, "32")

    def test_no_helper_means_no_layers(self):
        rows = [_chat_row(ttft=1.0, helper=False)]
        groups = latency.group_requests([latency.from_row(r, path="chat", arm="a") for r in rows], lambda r: r.arm)
        self.assertEqual(groups["a"].layers_text, "none")

    def test_failed_checks_are_counted_by_name(self):
        rows = [
            _speed_row(ttft_ms=1.0, valid=False, checks={"helper_ready_at_start": False}),
            _speed_row(ttft_ms=1.0, valid=False, checks={"helper_ready_at_start": False}),
            _speed_row(ttft_ms=1.0),
        ]
        groups = latency.group_requests([latency.from_row(r, path="s", arm="a") for r in rows], lambda r: r.arm)
        self.assertEqual(groups["a"].failed_text, "2 · helper_ready_at_start")

    def test_a_group_with_nothing_wrong_says_zero(self):
        groups = latency.group_requests([latency.from_row(_speed_row(ttft_ms=1.0), path="s", arm="a")], lambda r: r.arm)
        self.assertEqual(groups["a"].failed_text, "0")

    def test_a_group_whose_rows_record_no_checks_says_so(self):
        rows = [_chat_row(ttft=1.0, state="connecting") for _ in range(2)]
        groups = latency.group_requests([latency.from_row(r, path="c", arm="a") for r in rows], lambda r: r.arm)
        self.assertEqual(groups["a"].failed_text, "no validity marks")

    def test_a_group_that_mixes_both_says_how_many_rows_are_unmarked(self):
        rows = [_speed_row(ttft_ms=1.0), _chat_row(ttft=1.0)]
        groups = latency.group_requests([latency.from_row(r, path="m", arm="a") for r in rows], lambda r: r.arm)
        self.assertEqual(groups["a"].failed_text, "0 · 1 row unmarked")


class MacAloneTest(unittest.TestCase):
    def _requests(self):
        rows = [
            (_chat_row(ttft=109.70), "chat", "no wait"),
            (_chat_row(ttft=29.31), "chat", "wait"),
            (_chat_row(ttft=30.10), "speed test", "no wait"),
        ]
        return [latency.from_row(row, path=path, arm=arm) for row, path, arm in rows]

    def test_the_slowest_arm_at_a_size_is_the_mac_alone(self):
        self.assertAlmostEqual(latency.mac_alone_wait_s(self._requests())[32768], 109.70)

    def test_a_request_at_half_the_mac_alone_wait_is_not_helper_speed(self):
        alone = latency.mac_alone_wait_s(self._requests())
        at_half = latency.from_row(_chat_row(ttft=54.85), path="chat", arm="x")
        self.assertFalse(latency.at_helper_speed(at_half, alone))
        under = latency.from_row(_chat_row(ttft=54.84), path="chat", arm="x")
        self.assertTrue(latency.at_helper_speed(under, alone))

    def test_a_size_with_no_reference_is_not_judged(self):
        request = latency.from_row(_chat_row(ttft=29.0, size=8192), path="chat", arm="x")
        self.assertTrue(latency.at_helper_speed(request, {}))


if __name__ == "__main__":
    unittest.main()
