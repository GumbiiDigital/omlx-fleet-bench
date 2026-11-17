"""Tests for the helper state read and the helper wait policy."""

import argparse
import unittest
from typing import Any, Dict, List

from bench.helper import (
    DEFAULT_READY_TIMEOUT_S,
    HELPER_UNKNOWN_STATE,
    HelperStatus,
    HelperWaitPolicy,
    add_wait_arguments,
    prepare_helper,
    read_helper_state,
    wait_for_helper_ready,
)


class FakeClock:
    """A clock that moves only when the code sleeps, so waits cost no test time."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: List[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


class FakeAdmin:
    """Answers with a fixed list of helper payloads, then repeats the last one."""

    def __init__(self, states: List[Any]) -> None:
        self.states = list(states) or [{"state": "ready"}]
        self.reads = 0

    def get_prefill_helper_state(self, model: str) -> Any:
        self.reads += 1
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]


class TestReadState(unittest.TestCase):
    def test_ready_state_is_read_from_the_state_field(self) -> None:
        status = read_helper_state(lambda model: {"state": "ready"}, "m1")
        self.assertEqual(status.state, "ready")
        self.assertTrue(status.is_ready)

    def test_state_is_normalised(self) -> None:
        self.assertEqual(read_helper_state(lambda model: {"state": " Ready "}, "m1").state, "ready")

    def test_a_state_that_is_not_ready_is_kept_as_it_is(self) -> None:
        status = read_helper_state(lambda model: {"state": "connecting"}, "m1")
        self.assertEqual(status.state, "connecting")
        self.assertFalse(status.is_ready)

    def test_missing_field_is_unknown(self) -> None:
        self.assertEqual(read_helper_state(lambda model: {"held": 63}, "m1").state, HELPER_UNKNOWN_STATE)

    def test_empty_or_non_text_state_is_unknown(self) -> None:
        for payload in ({"state": ""}, {"state": None}, {"state": 3}, None, ["ready"]):
            self.assertEqual(read_helper_state(lambda model: payload, "m1").state, HELPER_UNKNOWN_STATE)

    def test_http_error_is_unknown_not_a_crash(self) -> None:
        def read(model: str) -> Any:
            raise OSError("HTTP Error 401: Unauthorized")

        self.assertEqual(read_helper_state(read, "m1").state, HELPER_UNKNOWN_STATE)

    def test_unreadable_body_is_unknown(self) -> None:
        def read(model: str) -> Any:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

        self.assertEqual(read_helper_state(read, "m1").state, HELPER_UNKNOWN_STATE)

    def test_off_status_has_no_state(self) -> None:
        status = HelperStatus.off()
        self.assertIsNone(status.state)
        self.assertFalse(status.is_ready)


class TestWait(unittest.TestCase):
    def test_waits_until_ready_and_counts_the_seconds(self) -> None:
        clock = FakeClock()
        states = [{"state": "starting"}, {"state": "starting"}, {"state": "ready"}]
        status = wait_for_helper_ready(
            lambda model: states.pop(0), "m1", timeout_s=30.0, interval_s=2.0, clock=clock, sleep=clock.sleep
        )
        self.assertEqual(status.state, "ready")
        self.assertEqual(status.waited_s, 4.0)
        self.assertEqual(clock.slept, [2.0, 2.0])

    def test_timeout_keeps_the_last_state_and_the_seconds_spent(self) -> None:
        clock = FakeClock()
        status = wait_for_helper_ready(
            lambda model: {"state": "starting"},
            "m1",
            timeout_s=5.0,
            interval_s=2.0,
            clock=clock,
            sleep=clock.sleep,
        )
        self.assertEqual(status.state, "starting")
        self.assertFalse(status.is_ready)
        self.assertEqual(status.waited_s, 5.0)
        self.assertEqual(clock.slept, [2.0, 2.0, 1.0])

    def test_zero_timeout_reads_once(self) -> None:
        clock = FakeClock()
        reads: List[str] = []

        def read(model: str) -> Dict[str, Any]:
            reads.append(model)
            return {"state": "starting"}

        status = wait_for_helper_ready(read, "m1", timeout_s=0.0, clock=clock, sleep=clock.sleep)
        self.assertEqual(reads, ["m1"])
        self.assertEqual(status.waited_s, 0.0)
        self.assertEqual(clock.slept, [])

    def test_a_ready_helper_is_not_waited_for(self) -> None:
        clock = FakeClock()
        status = wait_for_helper_ready(
            lambda model: {"state": "ready"}, "m1", timeout_s=30.0, clock=clock, sleep=clock.sleep
        )
        self.assertTrue(status.is_ready)
        self.assertEqual(status.waited_s, 0.0)
        self.assertEqual(clock.slept, [])


class TestPrepare(unittest.TestCase):
    def test_helper_off_does_not_ask_the_server(self) -> None:
        admin = FakeAdmin([{"state": "ready"}])
        status = prepare_helper(admin, "m1", HelperWaitPolicy(), helper_on=False)
        self.assertEqual(admin.reads, 0)
        self.assertIsNone(status.state)
        self.assertEqual(status.waited_s, 0.0)

    def test_wait_on_polls_through_a_fake_clock(self) -> None:
        admin = FakeAdmin([{"state": "starting"}, {"state": "ready"}])
        clock = FakeClock()
        status = prepare_helper(
            admin, "m1", HelperWaitPolicy(timeout_s=30.0), helper_on=True, clock=clock, sleep=clock.sleep
        )
        self.assertEqual(status.state, "ready")
        self.assertEqual(status.waited_s, 2.0)
        self.assertEqual(admin.reads, 2)

    def test_no_wait_reads_once_and_records_a_state_that_is_not_ready(self) -> None:
        admin = FakeAdmin([{"state": "starting"}])
        clock = FakeClock()
        status = prepare_helper(
            admin, "m1", HelperWaitPolicy(wait=False), helper_on=True, clock=clock, sleep=clock.sleep
        )
        self.assertEqual(admin.reads, 1)
        self.assertEqual(status.state, "starting")
        self.assertEqual(status.waited_s, 0.0)
        self.assertFalse(status.is_ready)


class TestOptions(unittest.TestCase):
    def _parse(self, *argv: str) -> argparse.Namespace:
        parser = argparse.ArgumentParser()
        add_wait_arguments(parser)
        return parser.parse_args(list(argv))

    def test_defaults(self) -> None:
        policy = HelperWaitPolicy.from_args(self._parse())
        self.assertEqual(policy.timeout_s, DEFAULT_READY_TIMEOUT_S)
        self.assertTrue(policy.wait)

    def test_timeout_and_no_wait(self) -> None:
        policy = HelperWaitPolicy.from_args(self._parse("--helper-ready-timeout", "7.5", "--no-helper-wait"))
        self.assertEqual(policy.timeout_s, 7.5)
        self.assertFalse(policy.wait)


if __name__ == "__main__":
    unittest.main()
