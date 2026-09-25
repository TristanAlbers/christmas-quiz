"""Focused deterministic tests for Phase 6 Challenge policies."""

from dataclasses import fields, replace

from django.test import SimpleTestCase

from quiz.domain.phase6 import (
    ChallengeTeamState,
    challenge_eligibility,
    initiate_challenge,
    resolve_challenge_answer,
)
from quiz.domain.types import DomainError


def error_code(call, *args, **kwargs):
    try:
        call(*args, **kwargs)
    except DomainError as error:
        return error.code
    raise AssertionError("expected a domain rejection")


def team(team_id, **changes):
    original = ChallengeTeamState(
        team_id=team_id,
        activity_state="PUZZLE",
        points=10,
        opportunity_available=True,
    )
    return replace(original, **changes)


def eligibility_args(**changes):
    original = {
        "global_state": "ADVENT_QUIZ",
        "challenge_active": False,
        "initiator": team("a"),
        "challenged": team("b"),
        "current_gameplay_ms": 100_000,
        "cost": 7,
    }
    original.update(changes)
    return original


def answer_args(**changes):
    original = {
        "global_state": "ADVENT_QUIZ",
        "challenge_status": "active",
        "current_challenge_id": "challenge-1",
        "submitted_challenge_id": "challenge-1",
        "current_question_id": "shared-challenge",
        "submitted_question_id": "shared-challenge",
        "validator_type": "text_exact",
        "expected_answer": "mistletoe",
        "submitted_answer": "Mistletoe",
        "answering_team_id": "a",
        "initiator": team(
            "a",
            activity_state="CHALLENGE",
            points=3,
            opportunity_available=False,
        ),
        "challenged": team("b", activity_state="CHALLENGE", points=4),
        "current_gameplay_ms": 123_000,
    }
    original.update(changes)
    return original


class ChallengeEligibilityTests(SimpleTestCase):
    def test_eligible_requires_two_effective_puzzle_teams_and_affordability(self):
        decision = challenge_eligibility(**eligibility_args())
        self.assertTrue(decision.can_initiate)
        self.assertIsNone(decision.reason)

        expired = team("b", activity_state="FREEZE", freeze_started_ms=0)
        self.assertTrue(
            challenge_eligibility(
                **eligibility_args(
                    challenged=expired,
                    current_gameplay_ms=300_000,
                )
            ).can_initiate
        )

    def test_disabled_reasons_are_coarse_and_stably_prioritized(self):
        cases = (
            ({"global_state": "PAUSED"}, "game_unavailable"),
            ({"challenge_active": True}, "game_unavailable"),
            (
                {"initiator": team("a", activity_state="FINISHED")},
                "game_unavailable",
            ),
            (
                {"initiator": team("a", opportunity_available=False)},
                "opportunity_spent",
            ),
            ({"initiator": team("a", points=6)}, "insufficient_points"),
            (
                {
                    "challenged": team(
                        "b", activity_state="FREEZE", freeze_started_ms=1
                    )
                },
                "opponent_unavailable",
            ),
            (
                {"challenged": team("b", activity_state="FINISHED")},
                "opponent_unavailable",
            ),
        )
        for changes, reason in cases:
            with self.subTest(changes=changes):
                decision = challenge_eligibility(**eligibility_args(**changes))
                self.assertFalse(decision.can_initiate)
                self.assertEqual(decision.reason, reason)


class ChallengeInitiationTests(SimpleTestCase):
    def test_start_atomically_describes_cost_opportunity_and_both_states(self):
        original_target = team("b", points=2, opportunity_available=True)
        decision = initiate_challenge(
            **eligibility_args(challenged=original_target)
        )
        self.assertEqual(decision.points_delta, -7)
        self.assertTrue(decision.opportunity_consumed)
        self.assertEqual(decision.initiator.points, 3)
        self.assertFalse(decision.initiator.opportunity_available)
        self.assertEqual(decision.initiator.activity_state, "CHALLENGE")
        self.assertEqual(decision.challenged.activity_state, "CHALLENGE")
        self.assertEqual(decision.challenged.points, 2)
        self.assertTrue(decision.challenged.opportunity_available)

    def test_either_team_can_initiate_and_only_that_team_spends(self):
        decision = initiate_challenge(
            **eligibility_args(
                initiator=team("b", points=7),
                challenged=team("a", points=11, opportunity_available=False),
            )
        )
        self.assertEqual(decision.initiator.team_id, "b")
        self.assertEqual(decision.initiator.points, 0)
        self.assertFalse(decision.initiator.opportunity_available)
        self.assertEqual(decision.challenged.team_id, "a")
        self.assertEqual(decision.challenged.points, 11)
        self.assertFalse(decision.challenged.opportunity_available)

    def test_illegal_start_rejects_without_partial_decision(self):
        cases = (
            ({"global_state": "PAUSED"}, "disallowed_state"),
            (
                {"initiator": team("a", activity_state="FINISHED")},
                "disallowed_state",
            ),
            ({"challenge_active": True}, "challenge_unavailable"),
            (
                {
                    "challenged": team(
                        "b", activity_state="FREEZE", freeze_started_ms=1
                    )
                },
                "challenge_unavailable",
            ),
            (
                {"challenged": team("b", activity_state="FINISHED")},
                "challenge_unavailable",
            ),
            (
                {"initiator": team("a", opportunity_available=False)},
                "challenge_spent",
            ),
            ({"initiator": team("a", points=6)}, "insufficient_points"),
        )
        for changes, code in cases:
            with self.subTest(changes=changes):
                self.assertEqual(
                    error_code(initiate_challenge, **eligibility_args(**changes)),
                    code,
                )


class ChallengeAnswerTests(SimpleTestCase):
    def test_wrong_attempt_is_penalty_free_and_keeps_challenge_active(self):
        initiator = answer_args()["initiator"]
        challenged = answer_args()["challenged"]
        decision = resolve_challenge_answer(
            **answer_args(
                submitted_answer="holly",
                initiator=initiator,
                challenged=challenged,
            )
        )
        self.assertEqual(decision.outcome, "incorrect")
        self.assertEqual(decision.initiator, initiator)
        self.assertEqual(decision.challenged, challenged)
        self.assertIsNone(decision.winner_team_id)
        self.assertFalse(decision.freeze_applied)
        self.assertEqual(decision.points_delta, 0)

    def test_initiator_win_directly_freezes_loser_and_preserves_reverse(self):
        decision = resolve_challenge_answer(
            **answer_args(
                challenged=team(
                    "b",
                    activity_state="CHALLENGE",
                    points=4,
                    uno_reverse_active=True,
                )
            )
        )
        self.assertEqual(decision.outcome, "won")
        self.assertEqual(decision.winner_team_id, "a")
        self.assertEqual(decision.initiator.activity_state, "PUZZLE")
        self.assertEqual(decision.challenged.activity_state, "FREEZE")
        self.assertEqual(decision.challenged.freeze_started_ms, 123_000)
        self.assertTrue(decision.challenged.uno_reverse_active)
        self.assertTrue(decision.freeze_applied)

    def test_challenged_team_win_returns_both_without_freeze(self):
        decision = resolve_challenge_answer(
            **answer_args(answering_team_id="b")
        )
        self.assertEqual(decision.winner_team_id, "b")
        self.assertEqual(decision.initiator.activity_state, "PUZZLE")
        self.assertEqual(decision.challenged.activity_state, "PUZZLE")
        self.assertIsNone(decision.challenged.freeze_started_ms)
        self.assertFalse(decision.freeze_applied)

    def test_answers_never_reward_progress_fragment_or_trigger_music(self):
        decision = resolve_challenge_answer(**answer_args())
        self.assertEqual(decision.points_delta, 0)
        self.assertFalse(decision.advent_progressed)
        self.assertIsNone(decision.fragment_award)
        self.assertFalse(decision.music_triggered)
        self.assertEqual(decision.initiator.points, 3)
        self.assertEqual(decision.challenged.points, 4)
        names = {field.name for field in fields(type(decision))}
        self.assertNotIn("reward_points", names)

    def test_pause_stale_context_and_nonparticipant_answers_are_rejected(self):
        cases = (
            ({"global_state": "PAUSED"}, "disallowed_state"),
            ({"challenge_status": "resolved"}, "stale_challenge"),
            ({"submitted_challenge_id": "old"}, "stale_challenge"),
            ({"submitted_question_id": "old"}, "stale_question"),
            ({"answering_team_id": "intruder"}, "disallowed_state"),
            (
                {"challenged": team("b", activity_state="PUZZLE")},
                "stale_challenge",
            ),
        )
        for changes, code in cases:
            with self.subTest(changes=changes):
                self.assertEqual(
                    error_code(
                        resolve_challenge_answer, **answer_args(**changes)
                    ),
                    code,
                )

    def test_answer_validator_supports_unlimited_repeated_attempts(self):
        first = resolve_challenge_answer(
            **answer_args(submitted_answer="wrong once")
        )
        second = resolve_challenge_answer(
            **answer_args(
                submitted_answer="wrong twice",
                initiator=first.initiator,
                challenged=first.challenged,
            )
        )
        self.assertEqual(first.outcome, "incorrect")
        self.assertEqual(second.outcome, "incorrect")
        self.assertEqual(second.initiator.activity_state, "CHALLENGE")


class ChallengeInputValidationTests(SimpleTestCase):
    def test_invalid_cost_team_or_clock_values_are_rejected(self):
        for changes in (
            {"cost": -1},
            {"cost": True},
            {"current_gameplay_ms": -1},
            {"initiator": team("a", points=-1)},
            {"challenged": team("a")},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(
                    error_code(initiate_challenge, **eligibility_args(**changes)),
                    "invalid_input",
                )
