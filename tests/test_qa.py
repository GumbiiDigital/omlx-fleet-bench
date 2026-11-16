import unittest

from bench import qa


class FinalNumberTest(unittest.TestCase):
    def test_reference_uses_marker(self):
        self.assertEqual(qa.reference_final_number("work ... #### 18"), 18.0)
        self.assertEqual(qa.reference_final_number("#### 1,234"), 1234.0)

    def test_model_marker_wins(self):
        text = "12 + 6 = 18\n#### 18"
        self.assertEqual(qa.model_final_number(text), 18.0)

    def test_model_falls_back_to_last_number(self):
        self.assertEqual(qa.model_final_number("It costs $18."), 18.0)
        self.assertEqual(qa.model_final_number("so 3 * 4 = 12, total 12"), 12.0)

    def test_no_number(self):
        self.assertIsNone(qa.model_final_number("no idea"))


class ScoreGsm8kTest(unittest.TestCase):
    def test_correct(self):
        result = qa.score_gsm8k("#### 18", "steps #### 18")
        self.assertTrue(result["correct"])

    def test_comma_and_currency(self):
        self.assertTrue(qa.score_gsm8k("#### $1,234", "steps #### 1234")["correct"])

    def test_wrong(self):
        self.assertFalse(qa.score_gsm8k("#### 17", "steps #### 18")["correct"])

    def test_unparsed_answer_is_wrong(self):
        result = qa.score_gsm8k("I cannot solve this", "steps #### 18")
        self.assertFalse(result["correct"])
        self.assertIsNone(result["got"])


class LetterTest(unittest.TestCase):
    def test_bare_letter(self):
        self.assertEqual(qa.extract_letter("B"), "B")
        self.assertEqual(qa.extract_letter("(C)"), "C")
        self.assertEqual(qa.extract_letter("D."), "D")

    def test_labelled_answer(self):
        self.assertEqual(qa.extract_letter("The correct answer is (C)."), "C")
        self.assertEqual(qa.extract_letter("Answer: D"), "D")
        self.assertEqual(qa.extract_letter("choice b"), "B")

    def test_thinking_then_answer(self):
        self.assertEqual(qa.extract_letter("We compare options.\n\nAnswer: A"), "A")

    def test_nothing(self):
        self.assertIsNone(qa.extract_letter(""))

    def test_score_mmlu(self):
        self.assertTrue(qa.score_mmlu("Answer: B", 1)["correct"])
        self.assertFalse(qa.score_mmlu("Answer: B", 2)["correct"])


class PasskeyTest(unittest.TestCase):
    def test_prompt_contains_needle(self):
        prompt = qa.build_passkey_prompt(1024, "4829157")
        self.assertIn("4829157", prompt)
        self.assertIn("passkey", prompt.lower())

    def test_prompt_size_close_to_target(self):
        prompt = qa.build_passkey_prompt(4096, "4829157")
        approx = qa.approximate_tokens(prompt)
        self.assertGreater(approx, 4096 * 0.8)
        self.assertLess(approx, 4096 * 1.25)

    def test_depth_moves_needle(self):
        early = qa.build_passkey_prompt(4096, "1111111", depth=0.1)
        late = qa.build_passkey_prompt(4096, "1111111", depth=0.9)
        self.assertLess(early.index("1111111"), late.index("1111111"))

    def test_depth_range(self):
        with self.assertRaises(ValueError):
            qa.build_passkey_prompt(1024, "1", depth=1.5)

    def test_score_passkey(self):
        self.assertTrue(qa.score_passkey("The passkey is 4829157.", "4829157")["correct"])
        self.assertTrue(qa.score_passkey("4,829,157", "4829157")["correct"])
        self.assertFalse(qa.score_passkey("7304826", "4829157")["correct"])


class MmluPromptTest(unittest.TestCase):
    def test_four_choices(self):
        prompt = qa.format_mmlu_prompt("Q?", ["a", "b", "c", "d"], "anatomy")
        for letter in "ABCD":
            self.assertIn(f"{letter}. ", prompt)
        self.assertIn("anatomy", prompt)

    def test_choice_count_checked(self):
        with self.assertRaises(ValueError):
            qa.format_mmlu_prompt("Q?", ["a", "b", "c"])


if __name__ == "__main__":
    unittest.main()
