"""Regression coverage for issues found during the Phase 6 Codex review."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from quiz.application import get_admin_state, get_team_state
from quiz.auth import actor_for_user
from quiz.configuration import InvalidPackage, _validate, stage_snapshot
from quiz.models import (
    AccountRole,
    Challenge,
    ChallengeAttempt,
    PuzzleProgress,
    Run,
    TeamRun,
)
from quiz.persistence import immediate_transaction


def _puzzle(team_id, number):
    return {
        "id": f"{team_id}-{number}",
        "number": number,
        "title": f"Puzzle {number}",
        "body": "Clue",
        "validator": {"type": "text_exact", "answer": "secret"},
        "reward_points": 1,
        "hint": None,
        "fragment": None,
        "media": [],
    }


def _music_question(number):
    return {
        "id": f"music-{number}",
        "number": number,
        "title": f"Song {number}",
        "body": "Name it",
        "validator": {"type": "text_exact", "answer": f"answer-{number}"},
    }


def _phase6_config(answer):
    return {
        "schema_version": 6,
        "package_id": "phase6-review",
        "initial_points": 10,
        "hint_cost": 1,
        "skip_cost": 2,
        "freeze_cost": 3,
        "uno_reverse_cost": 4,
        "challenge_cost": 7,
        "music_question_reward": 5,
        "music_score_display_duration_ms": 10_000,
        "teams": {
            team_id: {
                "puzzles": [_puzzle(team_id, number) for number in range(1, 26)]
            }
            for team_id in ("a", "b")
        },
        "music_questions": [_music_question(number) for number in range(1, 12)],
        "challenge_puzzle": {
            "id": "shared-challenge",
            "title": "Christmas Challenge",
            "body": "Solve it",
            "validator": {"type": "number_exact", "answer": answer},
            "media": [],
        },
    }


class PhaseSixConfigurationReviewTests(TestCase):
    def test_number_challenge_expected_answer_must_be_finite_decimal(self):
        for answer in ("not-a-number", "NaN", "Infinity", "-Infinity"):
            with self.subTest(answer=answer), self.assertRaises(InvalidPackage):
                _validate(_phase6_config(answer), "phase6-review")

        self.assertEqual(_validate(_phase6_config("12.50"), "phase6-review"), set())


class LegacyChallengeProjectionTests(TestCase):
    def test_legacy_run_never_reports_challenge_opportunity_available(self):
        users = get_user_model()
        admin = users.objects.create_user("review-admin")
        team_user = users.objects.create_user("review-team-a")
        AccountRole.objects.create(user=admin, role="admin", team_id=None)
        AccountRole.objects.create(user=team_user, role="team", team_id="a")

        with TemporaryDirectory() as directory:
            root = Path(directory)
            games = root / "games"
            package = games / "legacy-review"
            package.mkdir(parents=True)
            config = {
                "schema_version": 1,
                "package_id": "legacy-review",
                "initial_points": 10,
                "teams": {
                    team_id: {
                        "puzzles": [
                            _puzzle(team_id, number) for number in range(1, 3)
                        ]
                    }
                    for team_id in ("a", "b")
                },
            }

            (package / "game.json").write_text(json.dumps(config))
            with override_settings(
                QUIZ_GAMES_ROOT=games,
                QUIZ_SNAPSHOT_ROOT=root / "snapshots",
            ):
                staged = stage_snapshot("legacy-review")
                run = Run.objects.create(
                    global_state="ADVENT_QUIZ",
                    package_id="legacy-review",
                    snapshot_path=staged.path,
                    snapshot_digest=staged.digest,
                    advent_clock_anchor=timezone.now(),
                )
                for team_id in ("a", "b"):
                    TeamRun.objects.create(
                        run=run,
                        team_id=team_id,
                        activity_state="PUZZLE",
                        points=10,
                    )
                    for puzzle in config["teams"][team_id]["puzzles"]:
                        PuzzleProgress.objects.create(
                            run=run,
                            team_id=team_id,
                            puzzle_id=puzzle["id"],
                            number=puzzle["number"],
                        )

                team_state = get_team_state(actor_for_user(team_user))
                admin_state = get_admin_state(actor_for_user(admin))

        self.assertFalse(team_state.challenge_available)
        self.assertIsNone(team_state.challenge_cost)
        team_a = next(team for team in admin_state.teams if team.team_id == "a")
        team_b = next(team for team in admin_state.teams if team.team_id == "b")
        self.assertFalse(team_a.challenge_available)
        self.assertFalse(team_b.challenge_available)


class ChallengeWinnerInvariantTests(TransactionTestCase):
    def setUp(self):
        users = get_user_model()
        self.user_a = users.objects.create_user("review-a")
        self.user_b = users.objects.create_user("review-b")
        AccountRole.objects.create(user=self.user_a, role="team", team_id="a")
        AccountRole.objects.create(user=self.user_b, role="team", team_id="b")

    def _run(self, suffix):
        return Run.objects.create(
            active=False,
            global_state="ADVENT_QUIZ",
            package_id=f"review-{suffix}",
            snapshot_path=f"/tmp/review-{suffix}",
            snapshot_digest=suffix * 64,
        )

    def _challenge(self, run):
        return Challenge.objects.create(
            run=run,
            initiator_team_id="a",
            challenged_team_id="b",
            question_id="shared-challenge",
            paid_cost=7,
        )

    def _attempt(self, challenge, *, actor, team_id, correct):
        return ChallengeAttempt.objects.create(
            challenge=challenge,
            actor=actor,
            team_id=team_id,
            request_id=uuid4(),
            question_id="shared-challenge",
            is_correct=correct,
        )

    def _resolve_with(self, challenge, attempt):
        return Challenge.objects.filter(pk=challenge.pk).update(
            status="resolved",
            winner_team_id="a",
            freeze_applied=True,
            winning_attempt=attempt,
            resolved_at=timezone.now(),
        )

    def test_winning_attempt_must_belong_to_challenge_team_and_be_correct(self):
        challenge = self._challenge(self._run("a"))
        other_challenge = self._challenge(self._run("b"))
        foreign_attempt = self._attempt(
            other_challenge, actor=self.user_a, team_id="a", correct=True
        )
        with self.assertRaises(IntegrityError), immediate_transaction():
            self._resolve_with(challenge, foreign_attempt)

        incorrect_attempt = self._attempt(
            challenge, actor=self.user_a, team_id="a", correct=False
        )
        with self.assertRaises(IntegrityError), immediate_transaction():
            self._resolve_with(challenge, incorrect_attempt)

        wrong_team_challenge = self._challenge(self._run("c"))
        wrong_team_attempt = self._attempt(
            wrong_team_challenge, actor=self.user_b, team_id="b", correct=True
        )
        with self.assertRaises(IntegrityError), immediate_transaction():
            self._resolve_with(wrong_team_challenge, wrong_team_attempt)

    def test_winning_attempt_cannot_be_invalidated_after_resolution(self):
        challenge = self._challenge(self._run("d"))
        attempt = self._attempt(
            challenge, actor=self.user_a, team_id="a", correct=True
        )
        with immediate_transaction():
            self.assertEqual(self._resolve_with(challenge, attempt), 1)

        with self.assertRaises(IntegrityError), immediate_transaction():
            ChallengeAttempt.objects.filter(pk=attempt.pk).update(is_correct=False)
