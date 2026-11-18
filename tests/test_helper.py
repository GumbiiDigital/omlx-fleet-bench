"""Tests for the helper state read, the wait rule, the row fields and the served proof."""

import argparse
import unittest
from typing import Any, Dict, List

from bench.helper import (
    DEFAULT_READY_TIMEOUT_S,
    DEFAULT_STABLE_S,
    HELPER_UNKNOWN_STATE,
    HelperStatus,
    HelperWaitPolicy,
    add_wait_arguments,
    helper_fields,
    helper_served,
    prepare_helper,
    read_helper_state,
    wait_for_helper_ready,
)

FULL_ANSWER = {
    "state": "ready",
    "since": 1763400000.5,
    "layers": 49,
    "held": 63,
    "name": "a machine name",
    "node_id": "a node id",
    "link": "ethernet",
    "device": "NVIDIA GB10",
    "memory": 130660982784,
    "on_battery": False,
    "out_of_memory": False,
    "last_prompt": {"tokens": 32768, "seconds": 26.04, "at": 1763400123.25},
}


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
        self.states = list(states) or [FULL_ANSWER]
        self.reads = 0

    def get_prefill_helper_state(self, model: str) -> Any:
        self.reads += 1
        if len(self.states) > 1:
            return self.states.pop(0)
        return self.states[0]


class TestReadState(unittest.TestCase):
    def test_the_whole_answer_is_read(self) -> None:
        status = read_helper_state(lambda model: FULL_ANSWER, "m1")
        self.assertTrue(status.is_ready)
        self.assertEqual(status.since, 1763400000.5)
        self.assertEqual(status.layers, 49)
        self.assertEqual(status.held, 63)
        self.assertEqual(status.last_prompt_at, 1763400123.25)
        self.assertEqual(status.last_prompt_tokens, 32768)
        self.assertEqual(status.last_prompt_seconds, 26.04)

    def test_name_and_node_id_are_never_kept(self) -> None:
        fields = HelperStatus.__dataclass_fields__
        self.assertNotIn("name", fields)
        self.assertNotIn("node_id", fields)

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

    def test_a_missing_last_prompt_leaves_the_proof_fields_empty(self) -> None:
        status = read_helper_state(lambda model: {"state": "ready", "last_prompt": None}, "m1")
        self.assertIsNone(status.last_prompt_at)
        self.assertIsNone(status.last_prompt_tokens)
        self.assertIsNone(status.last_prompt_seconds)

    def test_http_error_is_unknown_not_a_crash(self) -> None:
        def read(model: str) -> Any:
            raise OSError("HTTP Error 401: Unauthorized")

        status = read_helper_state(read, "m1")
        self.assertEqual(status.state, HELPER_UNKNOWN_STATE)
        self.assertIsNone(status.last_prompt_at)

    def test_unreadable_body_is_unknown(self) -> None:
        def read(model: str) -> Any:
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

        self.assertEqual(read_helper_state(read, "m1").state, HELPER_UNKNOWN_STATE)

    def test_off_status_has_no_state(self) -> None:
        status = HelperStatus.off()
        self.assertIsNone(status.state)
        self.assertFalse(status.is_ready)


class TestWait(unittest.TestCase):
    def test_waits_until_ready_then_accepts_a_zero_span(self) -> None:
        clock = FakeClock()
        states = [{"state": "starting"}, {"state": "starting"}, {"state": "ready", "since": 5}]
        status = wait_for_helper_ready(
            lambda model: states.pop(0),
            "m1",
            timeout_s=30.0,
            stable_s=0.0,
            interval_s=2.0,
            clock=clock,
            sleep=clock.sleep,
        )
        self.assertEqual(status.state, "ready")
        self.assertEqual(status.waited_s, 4.0)
        self.assertEqual(clock.slept, [2.0, 2.0])

    def test_ready_must_hold_for_the_stable_span(self) -> None:
        clock = FakeClock()
        status = wait_for_helper_ready(
            lambda model: {"state": "ready", "since": 7},
            "m1",
            timeout_s=30.0,
            stable_s=5.0,
            interval_s=2.0,
            clock=clock,
            sleep=clock.sleep,
        )
        self.assertTrue(status.is_ready)
        self.assertEqual(status.since, 7)
        self.assertEqual(status.waited_s, 6.0)
        self.assertTrue(status.stable)

    def test_a_short_false_ready_does_not_pass(self) -> None:
        # The old session reads ready for the first second and ends; the new one starts at 10 s.
        clock = FakeClock()

        def read(model: str) -> Dict[str, Any]:
            if clock.now < 1.0:
                return {"state": "ready", "since": 1}
            if clock.now < 10.0:
                return {"state": "starting", "since": None}
            return {"state": "ready", "since": 2}

        status = wait_for_helper_ready(
            read, "m1", timeout_s=60.0, stable_s=5.0, interval_s=2.0, clock=clock, sleep=clock.sleep
        )
        self.assertEqual(status.since, 2)
        self.assertEqual(status.waited_s, 16.0)

    def test_a_change_of_since_restarts_the_span(self) -> None:
        clock = FakeClock()

        def read(model: str) -> Dict[str, Any]:
            return {"state": "ready", "since": 1 if clock.now < 4.0 else 2}

        status = wait_for_helper_ready(
            read, "m1", timeout_s=60.0, stable_s=5.0, interval_s=2.0, clock=clock, sleep=clock.sleep
        )
        self.assertEqual(status.since, 2)
        self.assertEqual(status.waited_s, 10.0)

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
        self.assertFalse(status.stable)
        self.assertEqual(clock.slept, [2.0, 2.0, 1.0])

    def test_a_ready_state_the_wait_did_not_trust_does_not_count(self) -> None:
        clock = FakeClock()
        status = wait_for_helper_ready(
            lambda model: {"state": "ready", "since": 1},
            "m1",
            timeout_s=0.0,
            stable_s=10.0,
            clock=clock,
            sleep=clock.sleep,
        )
        self.assertEqual(status.state, "ready")
        self.assertTrue(status.is_ready)
        self.assertFalse(status.stable)
        self.assertFalse(status.ready_for_request)

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

    def test_a_stable_ready_helper_is_not_waited_for(self) -> None:
        clock = FakeClock()
        status = wait_for_helper_ready(
            lambda model: {"state": "ready", "since": 3},
            "m1",
            timeout_s=30.0,
            stable_s=0.0,
            clock=clock,
            sleep=clock.sleep,
        )
        self.assertTrue(status.is_ready)
        self.assertEqual(status.waited_s, 0.0)
        self.assertEqual(clock.slept, [])


class TestPrepare(unittest.TestCase):
    def test_helper_off_does_not_ask_the_server(self) -> None:
        admin = FakeAdmin([FULL_ANSWER])
        status = prepare_helper(admin, "m1", HelperWaitPolicy(), helper_on=False)
        self.assertEqual(admin.reads, 0)
        self.assertIsNone(status.state)
        self.assertEqual(status.waited_s, 0.0)

    def test_wait_on_polls_through_a_fake_clock(self) -> None:
        admin = FakeAdmin([{"state": "starting"}, {"state": "ready", "since": 4}])
        clock = FakeClock()
        status = prepare_helper(
            admin,
            "m1",
            HelperWaitPolicy(timeout_s=30.0, stable_s=0.0),
            helper_on=True,
            clock=clock,
            sleep=clock.sleep,
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


class TestFields(unittest.TestCase):
    def test_start_fields_only(self) -> None:
        fields = helper_fields(HelperStatus(state="ready", waited_s=12.5))
        self.assertEqual(fields, {"helper_state": "ready", "helper_wait_s": 12.5})

    def test_proof_fields_are_added_after_a_request(self) -> None:
        start = HelperStatus(state="ready", waited_s=12.5)
        fields = helper_fields(start, HelperStatus.from_response(FULL_ANSWER))
        self.assertEqual(fields["helper_state"], "ready")
        self.assertEqual(fields["helper_wait_s"], 12.5)
        self.assertEqual(fields["helper_layers"], 49)
        self.assertEqual(fields["helper_held"], 63)
        self.assertEqual(fields["helper_session_since"], 1763400000.5)
        self.assertEqual(fields["helper_last_prompt_at"], 1763400123.25)
        self.assertEqual(fields["helper_last_prompt_tokens"], 32768)
        self.assertEqual(fields["helper_last_prompt_seconds"], 26.04)

    def test_helper_off_fields(self) -> None:
        fields = helper_fields(HelperStatus.off(), HelperStatus.off())
        self.assertIsNone(fields["helper_state"])
        self.assertEqual(fields["helper_wait_s"], 0.0)
        self.assertIsNone(fields["helper_layers"])
        self.assertIsNone(fields["helper_last_prompt_at"])


class TestServed(unittest.TestCase):
    def test_served_when_the_last_prompt_is_at_or_after_the_request(self) -> None:
        proof = HelperStatus(state="ready", last_prompt_at=100.0)
        self.assertTrue(helper_served(proof, 100.0))
        self.assertTrue(helper_served(proof, 99.0))

    def test_not_served_when_the_last_prompt_is_older(self) -> None:
        proof = HelperStatus(state="ready", last_prompt_at=100.0)
        self.assertFalse(helper_served(proof, 101.0))

    def test_helper_off_is_served(self) -> None:
        self.assertTrue(helper_served(HelperStatus.off(), None))

    def test_no_last_prompt_or_no_request_time_is_not_recorded(self) -> None:
        self.assertIsNone(helper_served(HelperStatus(state="ready"), 100.0))
        self.assertIsNone(helper_served(HelperStatus(state="ready", last_prompt_at=100.0), None))
        self.assertIsNone(helper_served(HelperStatus.unknown(), 100.0))


class TestOptions(unittest.TestCase):
    def _parse(self, *argv: str) -> argparse.Namespace:
        parser = argparse.ArgumentParser()
        add_wait_arguments(parser)
        return parser.parse_args(list(argv))

    def test_defaults(self) -> None:
        policy = HelperWaitPolicy.from_args(self._parse())
        self.assertEqual(policy.timeout_s, DEFAULT_READY_TIMEOUT_S)
        self.assertEqual(policy.stable_s, DEFAULT_STABLE_S)
        self.assertTrue(policy.wait)

    def test_timeout_stable_and_no_wait(self) -> None:
        policy = HelperWaitPolicy.from_args(
            self._parse("--helper-ready-timeout", "7.5", "--helper-stable-s", "2", "--no-helper-wait")
        )
        self.assertEqual(policy.timeout_s, 7.5)
        self.assertEqual(policy.stable_s, 2.0)
        self.assertFalse(policy.wait)


if __name__ == "__main__":
    unittest.main()
