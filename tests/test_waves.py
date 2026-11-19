"""Tests for reading a many-users row into its wave and its cell."""

import unittest

from bench import waves
from bench.labels import ARM_ALONE, ARM_HELPER


def _row(
    *,
    size=4096,
    users=2,
    wave=0,
    index=0,
    helper=False,
    ttft=10.0,
    wall=19.2,
    prompt_tokens=4142,
    cached=0,
    correct=True,
    valid=True,
    failed=None,
) -> dict:
    """One many-users row, shaped as bench/concurrency.py writes it."""
    validity = {"valid": valid, "wave_answered": valid, "status_completed": True, "cached_tokens_zero": True}
    validity.update(failed or {})
    if failed:
        validity["valid"] = False
    return {
        "machine": "m1",
        "helper_on": helper,
        "helper_state": "ready" if helper else None,
        "users": users,
        "wave": wave,
        "wave_id": f"{'spark' if helper else 'gpu'}-{size}-u{users}-w{wave}",
        "user_index": index,
        "target_tokens": size,
        "task": "many_users",
        "status": "completed",
        "correct": correct,
        "usage": {"cached_tokens": cached, "prompt_tokens": prompt_tokens},
        "server_timing": {"time_to_first_token": ttft},
        "wave_wall_s": wall,
        "validity": validity,
    }


class MemberTest(unittest.TestCase):
    def test_the_arm_comes_from_the_helper_field_of_the_row(self):
        self.assertEqual(waves.from_row(_row(helper=False)).arm, ARM_ALONE)
        self.assertEqual(waves.from_row(_row(helper=True)).arm, ARM_HELPER)

    def test_the_prompt_size_and_user_count_come_from_the_row(self):
        member = waves.from_row(_row(size=32768, users=8, wave=2, index=5))
        self.assertEqual(member.size, 32768)
        self.assertEqual(member.users, 8)
        self.assertEqual(member.wave, 2)

    def test_the_wave_carries_its_own_wall_time_and_prompt_tokens(self):
        member = waves.from_row(_row(wall=33.5, prompt_tokens=4100))
        self.assertEqual(member.wall_s, 33.5)
        self.assertEqual(member.prompt_tokens, 4100)

    def test_a_row_without_a_user_count_wave_or_wall_time_is_an_error(self):
        for field in ("users", "wave", "wave_wall_s"):
            row = _row()
            del row[field]
            with self.assertRaises(ValueError):
                waves.from_row(row)

    def test_a_row_without_prompt_tokens_is_an_error(self):
        row = _row()
        row["usage"] = {"cached_tokens": 0}
        with self.assertRaises(ValueError):
            waves.from_row(row)


class CellTest(unittest.TestCase):
    def _cell(self, rows):
        return next(iter(waves.cells(rows).values()))

    def test_every_request_of_the_cell_is_counted(self):
        rows = [_row(users=2, index=index, ttft=10.0 + index) for index in range(2)]
        cell = self._cell(rows)
        self.assertEqual(cell.requests, 2)
        self.assertEqual(cell.n_valid, 2)

    def test_the_mean_wait_is_over_the_requests(self):
        rows = [_row(users=2, index=index, ttft=wait) for index, wait in enumerate((9.8, 10.6))]
        self.assertAlmostEqual(self._cell(rows).mean_ttft_s, 10.2)
        self.assertEqual(self._cell(rows).low_ttft_s, 9.8)
        self.assertEqual(self._cell(rows).high_ttft_s, 10.6)

    def test_a_flagged_row_stays_in_the_count_and_out_of_the_means(self):
        rows = [
            _row(wave=0, users=2, index=0, ttft=9.8, wall=19.0),
            _row(wave=0, users=2, index=1, ttft=9.9, wall=19.0),
            _row(wave=1, users=2, index=0, ttft=99.0, wall=99.0, failed={"helper_served_proven": False}),
            _row(wave=1, users=2, index=1, ttft=98.0, wall=99.0),
        ]
        cell = self._cell(rows)
        self.assertEqual(cell.requests, 4)
        self.assertEqual(cell.n_valid, 3)
        # The wait of the flagged row is out of the range; the wave it broke has no whole-wave figure.
        self.assertAlmostEqual(cell.mean_ttft_s, (9.8 + 9.9 + 98.0) / 3)
        self.assertEqual(cell.high_ttft_s, 98.0)
        self.assertAlmostEqual(cell.mean_wall_s, 19.0)

    def test_a_cell_whose_every_wave_broke_has_no_wave_mean(self):
        rows = [_row(wave=wave, index=0, failed={"wave_answered": False}) for wave in range(2)]
        cell = self._cell(rows)
        self.assertEqual(cell.requests, 2)
        with self.assertRaises(ValueError):
            cell.mean_wall_s
        with self.assertRaises(ValueError):
            cell.mean_ttft_s

    def test_the_wave_time_is_the_mean_of_the_waves_not_of_the_requests(self):
        rows = [
            _row(wave=0, index=0, ttft=9.0, wall=18.0),
            _row(wave=0, index=1, ttft=9.0, wall=18.0),
            _row(wave=1, index=0, ttft=11.0, wall=22.0),
            _row(wave=1, index=1, ttft=11.0, wall=22.0),
        ]
        cell = self._cell(rows)
        self.assertEqual(sorted(cell.waves), [0, 1])
        self.assertAlmostEqual(cell.mean_wall_s, 20.0)

    def test_the_wave_speed_counts_every_user_prompt_over_the_wave_time(self):
        rows = [_row(users=2, index=index, wall=20.0, prompt_tokens=4000) for index in range(2)]
        self.assertAlmostEqual(self._cell(rows).mean_prompt_tps, 400.0)

    def test_cells_keep_the_two_arms_and_the_two_sizes_apart(self):
        rows = [
            _row(size=4096, helper=False),
            _row(size=4096, helper=True),
            _row(size=32768, helper=False),
        ]
        self.assertEqual(
            set(waves.cells(rows)),
            {(4096, ARM_ALONE, 2), (4096, ARM_HELPER, 2), (32768, ARM_ALONE, 2)},
        )


class SortTest(unittest.TestCase):
    def test_cells_run_by_size_then_user_count_then_the_mac_alone(self):
        rows = [
            _row(size=32768, users=1, helper=False),
            _row(size=4096, users=8, helper=True),
            _row(size=4096, users=8, helper=False),
            _row(size=4096, users=2, helper=True),
        ]
        ordered = waves.sort_cells(list(waves.cells(rows).values()))
        self.assertEqual(
            [(cell.size, cell.users, cell.arm) for cell in ordered],
            [(4096, 2, ARM_HELPER), (4096, 8, ARM_ALONE), (4096, 8, ARM_HELPER), (32768, 1, ARM_ALONE)],
        )


class ComparisonTest(unittest.TestCase):
    def test_the_speed_up_is_the_mac_alone_wave_over_the_helper_wave(self):
        alone = next(iter(waves.cells([_row(helper=False, wall=40.0)]).values()))
        helper = next(iter(waves.cells([_row(helper=True, wall=20.0)]).values()))
        self.assertAlmostEqual(waves.comparison(helper, alone), 2.0)


class ReadingLineTest(unittest.TestCase):
    def test_all_cold_and_right_says_so_with_the_count(self):
        members = [waves.from_row(_row(users=2, index=index)) for index in range(2)]
        self.assertEqual(
            waves.reading_line(members), "All 2 requests read their prompt cold and got a correct answer."
        )

    def test_a_warm_request_and_a_wrong_answer_are_both_counted(self):
        members = [
            waves.from_row(_row(index=0, cached=0)),
            waves.from_row(_row(index=1, cached=12, correct=False)),
        ]
        self.assertIn("1 of 2 requests read their prompt cold", waves.reading_line(members))
        self.assertIn("1 of 2 answers were correct", waves.reading_line(members))


class FailedMarksTest(unittest.TestCase):
    def test_each_failed_check_is_counted(self):
        members = [
            waves.from_row(_row(index=0, failed={"helper_served_proven": False})),
            waves.from_row(_row(index=1, failed={"helper_served_proven": False})),
            waves.from_row(_row(index=1, failed={"cached_tokens_zero": False})),
        ]
        self.assertEqual(waves.failed_marks(members), {"helper_served_proven": 2, "cached_tokens_zero": 1})


if __name__ == "__main__":
    unittest.main()
