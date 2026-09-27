"""Deterministic phase 2 rules, independent of database and actor plumbing."""

from dataclasses import replace

from django.test import SimpleTestCase

from quiz.domain import CompletionState, DomainError, PuzzleCompletion
from quiz.domain.phase2 import (
    adjust_points,
    pause_game,
    pay_skip,
    purchase_hint,
    resume_game,
    reveal_hint,
)


def completion_state(**changes):
    original = CompletionState(
        global_state="ADVENT_QUIZ",
        team_state="PUZZLE",
        current_number=1,
        points=8,
        completed_numbers=frozenset(),
        rewarded_numbers=frozenset(),
        fragment_awarded_numbers=frozenset(),
    )
    return replace(original, **changes)


def error_code(call, *args):
    try:
        call(*args)
    except DomainError as error:
        return error.code
    raise AssertionError("expected a domain rejection")


class AdministrationRulesTests(SimpleTestCase):
    def test_pause_and_resume_only_normal_advent(self):
        self.assertEqual(pause_game("ADVENT_QUIZ"), "PAUSED")
        self.assertEqual(resume_game("PAUSED"), "ADVENT_QUIZ")
        for state in ("READY", "PAUSED", "MUSIC_QUIZ", "FINISHED"):
            with self.subTest(state=state):
                self.assertEqual(error_code(pause_game, state), "disallowed_state")
        for state in ("READY", "ADVENT_QUIZ", "MUSIC_QUIZ", "FINISHED"):
            with self.subTest(state=state):
                self.assertEqual(error_code(resume_game, state), "disallowed_state")

    def test_adjustment_boundaries(self):
        self.assertEqual(adjust_points(4, 3), 7)
        self.assertEqual(adjust_points(4, -4), 0)
        self.assertEqual(error_code(adjust_points, 4, -5), "insufficient_points")
        for balance, delta in ((-1, 1), (1.0, 1), (True, 1), (1, False)):
            with self.subTest(balance=balance, delta=delta):
                self.assertEqual(
                    error_code(adjust_points, balance, delta), "invalid_input"
                )


class HintRulesTests(SimpleTestCase):
    def test_purchase_spends_configured_cost_and_increments_generic_inventory(self):
        self.assertEqual(purchase_hint("ADVENT_QUIZ", "PUZZLE", 3, 2, 3), (0, 3))
        self.assertEqual(purchase_hint("ADVENT_QUIZ", "PUZZLE", 0, 0, 0), (0, 1))
        self.assertEqual(
            error_code(purchase_hint, "ADVENT_QUIZ", "PUZZLE", 2, 0, 3),
            "insufficient_points",
        )

    def test_purchase_rejects_interruption_team_block_and_bad_values(self):
        for global_state, team_state in (
            ("PAUSED", "PUZZLE"),
            ("MUSIC_QUIZ", "PUZZLE"),
            ("ADVENT_QUIZ", "FREEZE"),
            ("READY", "READY"),
        ):
            with self.subTest(global_state=global_state, team_state=team_state):
                self.assertEqual(
                    error_code(purchase_hint, global_state, team_state, 4, 0, 3),
                    "disallowed_state",
                )
        for points, tokens, cost in ((-1, 0, 1), (3, -1, 1), (3, 0, -1), (True, 0, 1)):
            with self.subTest(points=points, tokens=tokens, cost=cost):
                self.assertEqual(
                    error_code(
                        purchase_hint, "ADVENT_QUIZ", "PUZZLE", points, tokens, cost
                    ),
                    "invalid_input",
                )

    def test_first_player_use_consumes_one_token_and_repeat_is_free(self):
        self.assertEqual(
            reveal_hint("ADVENT_QUIZ", "PUZZLE", 2, 2, 3, False), (2, True)
        )
        self.assertEqual(
            reveal_hint("ADVENT_QUIZ", "PUZZLE", 2, 2, 0, True), (0, False)
        )
        self.assertEqual(
            error_code(reveal_hint, "ADVENT_QUIZ", "PUZZLE", 2, 2, 0, False),
            "no_hint_tokens",
        )

    def test_admin_first_reveal_is_free_and_subsequent_player_use_is_free(self):
        self.assertEqual(
            reveal_hint("ADVENT_QUIZ", "PUZZLE", 2, 2, 1, False, True), (1, True)
        )
        self.assertEqual(
            reveal_hint("ADVENT_QUIZ", "PUZZLE", 2, 2, 1, True), (1, False)
        )
        self.assertEqual(
            reveal_hint("ADVENT_QUIZ", "PUZZLE", 2, 2, 0, True, True), (0, False)
        )

    def test_reveal_requires_current_puzzle_and_usable_state_even_on_repeat(self):
        self.assertEqual(
            error_code(reveal_hint, "ADVENT_QUIZ", "PUZZLE", 2, 1, 1, True),
            "stale_question",
        )
        for global_state, team_state in (
            ("PAUSED", "PUZZLE"),
            ("MUSIC_QUIZ", "PUZZLE"),
            ("ADVENT_QUIZ", "FREEZE"),
        ):
            with self.subTest(global_state=global_state, team_state=team_state):
                self.assertEqual(
                    error_code(reveal_hint, global_state, team_state, 2, 2, 1, True),
                    "disallowed_state",
                )
        self.assertEqual(
            error_code(reveal_hint, "ADVENT_QUIZ", "PUZZLE", 2, 2, -1, False),
            "invalid_input",
        )


class SkipRulesTests(SimpleTestCase):
    def test_skip_charges_pre_reward_balance_and_uses_canonical_awards(self):
        puzzle = PuzzleCompletion(1, 7, "bell", 2)
        result = pay_skip(completion_state(points=3), puzzle, 3)
        self.assertEqual(result.route, "skip")
        self.assertEqual(result.state.points, 7)
        self.assertEqual(result.points_delta, 4)
        self.assertEqual(result.state.current_number, 2)
        self.assertEqual(result.state.completed_numbers, {1})
        self.assertEqual(result.fragment_award, "bell")

    def test_future_reward_cannot_fund_skip(self):
        self.assertEqual(
            error_code(
                pay_skip, completion_state(points=2), PuzzleCompletion(1, 7, None, 2), 3
            ),
            "insufficient_points",
        )

    def test_skip_cannot_recomplete_or_ignore_state_and_prerequisites(self):
        puzzle = PuzzleCompletion(1, 2, None, 2)
        self.assertEqual(
            error_code(
                pay_skip, completion_state(completed_numbers=frozenset({1})), puzzle, 1
            ),
            "stale_question",
        )
        self.assertEqual(
            error_code(pay_skip, completion_state(global_state="PAUSED"), puzzle, 1),
            "disallowed_state",
        )
        self.assertEqual(
            error_code(
                pay_skip,
                completion_state(current_number=2),
                PuzzleCompletion(2, 2, None, 3),
                1,
            ),
            "prerequisite_violation",
        )
        self.assertEqual(
            error_code(pay_skip, completion_state(), puzzle, -1), "invalid_input"
        )

    def test_skip_recompletion_history_never_duplicates_reward_or_fragment(self):
        reopened = completion_state(
            points=8,
            rewarded_numbers=frozenset({1}),
            fragment_awarded_numbers=frozenset({1}),
        )
        result = pay_skip(reopened, PuzzleCompletion(1, 7, "bell", 2), 3)
        self.assertEqual(result.points_delta, -3)
        self.assertEqual(result.state.points, 5)
        self.assertIsNone(result.fragment_award)

    def test_skip_rejects_puzzle_25_before_canonical_completion(self):
        before = completion_state(
            current_number=25,
            points=10,
            completed_numbers=frozenset(range(1, 25)),
        )

        self.assertEqual(
            error_code(
                pay_skip,
                before,
                PuzzleCompletion(25, 2, "last", None),
                3,
                True,
            ),
            "disallowed_state",
        )
        self.assertEqual(before.current_number, 25)
        self.assertEqual(before.points, 10)
        self.assertNotIn(25, before.completed_numbers)
