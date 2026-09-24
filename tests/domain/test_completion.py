"""Canonical puzzle completion proposals; no database is needed here."""

from dataclasses import replace

from django.test import SimpleTestCase

from quiz.domain import (
    CompletionState,
    DomainError,
    PuzzleCompletion,
    can_submit_answer,
    complete_puzzle,
)


def state(**changes):
    base = CompletionState(
        global_state="ADVENT_QUIZ",
        team_state="PUZZLE",
        current_number=1,
        points=4,
        completed_numbers=frozenset(),
        rewarded_numbers=frozenset(),
        fragment_awarded_numbers=frozenset(),
    )
    return replace(base, **changes)


PUZZLE_1 = PuzzleCompletion(1, 3, "red bell", 2)


class CompletionTests(SimpleTestCase):
    def test_answer_permissions_require_advent_and_puzzle(self):
        self.assertTrue(can_submit_answer("ADVENT_QUIZ", "PUZZLE"))
        for global_state in ("READY", "PAUSED", "MUSIC_QUIZ", "FINISHED"):
            self.assertFalse(can_submit_answer(global_state, "PUZZLE"))
        for team_state in ("READY", "FREEZE", "CHALLENGE", "FINISHED"):
            self.assertFalse(can_submit_answer("ADVENT_QUIZ", team_state))

    def test_all_routes_use_same_completion_effects(self):
        for route in ("correct_answer", "skip", "admin_force"):
            with self.subTest(route=route):
                before = state()
                decision = complete_puzzle(before, PUZZLE_1, route)
                self.assertEqual(decision.route, route)
                self.assertEqual(decision.points_delta, 3)
                self.assertEqual(decision.fragment_award, "red bell")
                self.assertTrue(decision.progressed)
                self.assertFalse(decision.team_finished)
                self.assertFalse(decision.claim_first_finisher)
                self.assertFalse(decision.game_finished)
                self.assertEqual(decision.state.points, 7)
                self.assertEqual(decision.state.current_number, 2)
                self.assertEqual(decision.state.completed_numbers, {1})
                self.assertEqual(decision.state.rewarded_numbers, {1})
                self.assertEqual(decision.state.fragment_awarded_numbers, {1})
                self.assertEqual(before.points, 4)
                self.assertEqual(before.completed_numbers, frozenset())

    def test_wrong_puzzle_or_missing_prerequisite_cannot_advance(self):
        puzzle_2 = PuzzleCompletion(2, 5, None, None)
        for before, code in (
            (state(), "stale_question"),
            (state(current_number=2), "prerequisite_violation"),
        ):
            with self.subTest(code=code):
                with self.assertRaises(DomainError) as caught:
                    complete_puzzle(before, puzzle_2, "correct_answer")
                self.assertEqual(caught.exception.code, code)
        with self.assertRaises(DomainError) as caught:
            complete_puzzle(
                state(current_number=2, completed_numbers=frozenset({1})),
                PUZZLE_1,
                "correct_answer",
            )
        self.assertEqual(caught.exception.code, "stale_question")

    def test_reopened_puzzle_recompletes_without_duplicate_awards(self):
        reopened = state(
            current_number=2,
            points=7,
            rewarded_numbers=frozenset({1}),
            fragment_awarded_numbers=frozenset({1}),
        )
        result = complete_puzzle(reopened, PUZZLE_1, "admin_force")
        self.assertEqual(result.points_delta, 0)
        self.assertIsNone(result.fragment_award)
        self.assertFalse(result.progressed)
        self.assertEqual(result.state.current_number, 2)
        self.assertEqual(result.state.points, 7)
        self.assertEqual(result.state.completed_numbers, {1})

    def test_reward_and_fragment_history_are_independent(self):
        reopened = state(
            rewarded_numbers=frozenset({1}),
            fragment_awarded_numbers=frozenset(),
        )
        result = complete_puzzle(reopened, PUZZLE_1, "correct_answer")
        self.assertEqual(result.points_delta, 0)
        self.assertEqual(result.fragment_award, "red bell")

    def test_repeated_completion_is_stale(self):
        before = state(completed_numbers=frozenset({1}))
        with self.assertRaises(DomainError) as caught:
            complete_puzzle(before, PUZZLE_1, "correct_answer")
        self.assertEqual(caught.exception.code, "stale_question")

    def test_interruptions_and_team_activity_block_completion(self):
        for before in (
            state(global_state="PAUSED"),
            state(global_state="MUSIC_QUIZ"),
            state(team_state="FREEZE"),
            state(team_state="FINISHED"),
        ):
            with self.subTest(before=before):
                with self.assertRaises(DomainError) as caught:
                    complete_puzzle(before, PUZZLE_1, "correct_answer")
                self.assertEqual(caught.exception.code, "disallowed_state")

    def test_demo_last_puzzle_does_not_finish_the_game(self):
        before = state(current_number=2, completed_numbers=frozenset({1}))
        result = complete_puzzle(
            before, PuzzleCompletion(2, 1, None, None), "correct_answer"
        )
        self.assertFalse(result.progressed)
        self.assertEqual(result.state.current_number, 2)
        self.assertEqual(result.state.team_state, "PUZZLE")
        self.assertEqual(result.state.global_state, "ADVENT_QUIZ")
        self.assertEqual(result.state.completed_numbers, {1, 2})

    def test_puzzle_25_finishes_first_team_but_not_global_game(self):
        before = state(
            current_number=25,
            completed_numbers=frozenset(range(1, 25)),
            rewarded_numbers=frozenset(range(1, 25)),
        )

        for route in ("correct_answer", "skip", "admin_force"):
            with self.subTest(route=route):
                result = complete_puzzle(
                    before,
                    PuzzleCompletion(25, 7, "final star", None),
                    route,
                )
                self.assertTrue(result.team_finished)
                self.assertTrue(result.claim_first_finisher)
                self.assertFalse(result.game_finished)
                self.assertEqual(result.state.team_state, "FINISHED")
                self.assertEqual(result.state.global_state, "ADVENT_QUIZ")
                self.assertEqual(result.state.current_number, 25)
                self.assertEqual(result.state.completed_numbers, set(range(1, 26)))
                self.assertEqual(result.points_delta, 7)
                self.assertEqual(result.fragment_award, "final star")
                self.assertFalse(result.progressed)

    def test_puzzle_25_finishes_global_game_when_other_team_finished(self):
        before = state(
            current_number=25,
            completed_numbers=frozenset(range(1, 25)),
        )

        result = complete_puzzle(
            before,
            PuzzleCompletion(25, 0, None, None),
            "correct_answer",
            other_team_finished=True,
        )

        self.assertTrue(result.team_finished)
        self.assertFalse(result.claim_first_finisher)
        self.assertTrue(result.game_finished)
        self.assertEqual(result.state.team_state, "FINISHED")
        self.assertEqual(result.state.global_state, "FINISHED")

    def test_puzzle_24_advances_without_finishing(self):
        before = state(
            current_number=24,
            completed_numbers=frozenset(range(1, 24)),
        )
        result = complete_puzzle(
            before, PuzzleCompletion(24, 0, None, 25), "correct_answer"
        )

        self.assertTrue(result.progressed)
        self.assertFalse(result.team_finished)
        self.assertEqual(result.state.current_number, 25)
        self.assertEqual(result.state.team_state, "PUZZLE")

    def test_finished_team_cannot_recomplete_final_puzzle(self):
        before = state(
            team_state="FINISHED",
            current_number=25,
            completed_numbers=frozenset(range(1, 26)),
        )
        with self.assertRaises(DomainError) as caught:
            complete_puzzle(
                before,
                PuzzleCompletion(25, 0, None, None),
                "admin_force",
            )
        self.assertEqual(caught.exception.code, "disallowed_state")

    def test_invalid_costs_or_next_number_are_rejected(self):
        for puzzle in (
            PuzzleCompletion(1, -1, None, 2),
            PuzzleCompletion(1, 1, None, 3),
            PuzzleCompletion(25, 1, None, 26),
            PuzzleCompletion(26, 1, None, None),
        ):
            with self.subTest(puzzle=puzzle):
                with self.assertRaises(DomainError) as caught:
                    complete_puzzle(
                        state(current_number=puzzle.number),
                        puzzle,
                        "correct_answer",
                    )
                self.assertEqual(caught.exception.code, "invalid_input")

        with self.assertRaises(DomainError) as caught:
            complete_puzzle(state(), PUZZLE_1, "correct_answer", other_team_finished=1)
        self.assertEqual(caught.exception.code, "invalid_input")
