"""Declared answer validator behavior for a pinned puzzle snapshot."""

from django.test import SimpleTestCase

from quiz.domain import DomainError, evaluate_answer


class AnswerValidatorTests(SimpleTestCase):
    def test_text_exact_ignores_outer_space_and_case_only(self):
        self.assertTrue(evaluate_answer("text_exact", "North Star", "  NORTH STAR  "))
        self.assertFalse(evaluate_answer("text_exact", "North Star", "North  Star"))
        self.assertFalse(evaluate_answer("text_exact", "North Star", "Star North"))

    def test_text_exact_unicode_casefold(self):
        self.assertTrue(evaluate_answer("text_exact", "Straße", "STRASSE"))

    def test_number_exact_compares_decimal_values(self):
        for value in ("7", " 7.0 ", "+07", "7e0"):
            with self.subTest(value=value):
                self.assertTrue(evaluate_answer("number_exact", "7", value))
        for value in ("8", "seven", "", "NaN", "Infinity"):
            with self.subTest(value=value):
                self.assertFalse(evaluate_answer("number_exact", "7", value))

    def test_unknown_or_invalid_validator_is_configuration_error(self):
        invalid_validators = (
            ("regex", "x"),
            ("text_exact", " "),
            ("number_exact", "NaN"),
        )
        for kind, expected in invalid_validators:
            with self.subTest(kind=kind, expected=expected):
                with self.assertRaises(DomainError) as caught:
                    evaluate_answer(kind, expected, "x")
                self.assertEqual(caught.exception.code, "invalid_input")
