"""Focused Phase 6 application, projection, route, and HTMX-boundary checks."""

import tempfile
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from quiz.application import (
    get_admin_state,
    get_public_state,
    get_team_state,
    initiate_challenge,
    pause_game,
    resume_game,
    start_game,
    submit_challenge_answer,
)
from quiz.contracts import (
    Actor,
    ApplicationError,
    RunCommand,
    StartGame,
    SubmitChallengeAnswer,
)
from quiz.models import (
    AccountRole,
    AuditEvent,
    Challenge,
    ChallengeAttempt,
    CommandReceipt,
    PuzzleProgress,
    TeamRun,
)
from quiz.web.views import _question_context, _team_actions_context

NOW = datetime(2026, 12, 24, 18, 0, tzinfo=timezone.utc)


class PhaseSixApplicationTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        settings = override_settings(
            QUIZ_SNAPSHOT_ROOT=Path(self.temp.name) / "snapshots"
        )
        settings.enable()
        self.addCleanup(settings.disable)
        users = get_user_model()
        self.admin_user = users.objects.create_user("phase6-app-admin")
        self.a_user = users.objects.create_user("phase6-app-a")
        self.b_user = users.objects.create_user("phase6-app-b")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.a_user, role="team", team_id="a")
        AccountRole.objects.create(user=self.b_user, role="team", team_id="b")
        self.admin = Actor(self.admin_user.pk, "admin")
        self.a = Actor(self.a_user.pk, "team", "a")
        self.b = Actor(self.b_user.pk, "team", "b")
        self.run_id = start_game(
            self.admin,
            StartGame(str(uuid4()), "christmas-2026-demo"),
            now=NOW,
        ).run_id

    def initiate(self, actor, *, request_id=None, now=NOW):
        return initiate_challenge(
            actor,
            RunCommand(request_id or str(uuid4()), self.run_id),
            now=now,
        )

    def answer(self, actor, challenge, answer, *, request_id=None, now=NOW):
        return submit_challenge_answer(
            actor,
            SubmitChallengeAnswer(
                request_id or str(uuid4()),
                self.run_id,
                str(challenge.id),
                "shared-challenge",
                answer,
            ),
            now=now,
        )

    def test_projection_start_retry_wrong_attempt_and_challenged_win(self):
        initial = get_team_state(self.a, now=NOW)
        self.assertTrue(initial.challenge_available)
        self.assertEqual(initial.challenge_cost, 2)
        self.assertTrue(initial.can_initiate_challenge)
        self.assertIsNone(initial.challenge_ineligible_reason)

        request_id = str(uuid4())
        started = self.initiate(self.a, request_id=request_id)
        retry = self.initiate(self.a, request_id=request_id)
        self.assertEqual(started, retry)
        challenge = Challenge.objects.get(run_id=self.run_id)
        a_row = TeamRun.objects.get(run_id=self.run_id, team_id="a")
        self.assertEqual(a_row.points, 1)
        self.assertFalse(a_row.challenge_available)
        self.assertEqual(
            CommandReceipt.objects.filter(action="initiate_challenge").count(), 1
        )

        a_state = get_team_state(self.a, now=NOW)
        b_state = get_team_state(self.b, now=NOW)
        self.assertEqual(a_state.challenge.role, "initiator")
        self.assertEqual(b_state.challenge.role, "challenged")
        self.assertEqual(a_state.challenge.question.id, "shared-challenge")
        self.assertFalse(a_state.can_initiate_challenge)
        self.assertEqual(a_state.challenge_ineligible_reason, "game_unavailable")

        wrong_id = str(uuid4())
        before_context = _question_context(b_state)
        wrong = self.answer(self.b, challenge, "wrong", request_id=wrong_id)
        wrong_retry = self.answer(self.b, challenge, "wrong", request_id=wrong_id)
        self.assertEqual(wrong.outcome, "incorrect")
        self.assertEqual(wrong_retry.outcome, "incorrect")
        self.assertEqual(_question_context(wrong.state), before_context)
        self.assertEqual(
            ChallengeAttempt.objects.filter(challenge=challenge).count(), 1
        )

        won = self.answer(self.b, challenge, "santa", now=NOW + timedelta(seconds=5))
        self.assertEqual(won.outcome, "won")
        challenge.refresh_from_db()
        self.assertEqual(challenge.winner_team_id, "b")
        self.assertFalse(challenge.freeze_applied)
        self.assertEqual(won.state.challenge.status, "resolved")
        self.assertIsNone(won.state.challenge.question)
        self.assertEqual(
            set(
                TeamRun.objects.filter(run_id=self.run_id).values_list(
                    "activity_state", flat=True
                )
            ),
            {"PUZZLE"},
        )
        self.assertFalse(
            PuzzleProgress.objects.filter(
                run_id=self.run_id, completed=True
            ).exists()
        )

    def test_initiator_win_applies_direct_freeze_and_preserves_reverse(self):
        TeamRun.objects.filter(run_id=self.run_id, team_id="b").update(
            reverse_active=True
        )
        self.initiate(self.a)
        challenge = Challenge.objects.get(run_id=self.run_id)
        result = self.answer(
            self.a,
            challenge,
            "santa",
            now=NOW + timedelta(seconds=12),
        )
        self.assertEqual(result.outcome, "won")
        b_row = TeamRun.objects.get(run_id=self.run_id, team_id="b")
        self.assertEqual(b_row.activity_state, "FREEZE")
        self.assertEqual(b_row.freeze_started_gameplay_ms, 12_000)
        self.assertTrue(b_row.reverse_active)
        self.assertEqual(result.state.challenge.winner_team_id, "a")
        self.assertTrue(result.state.challenge.freeze_applied)

    def test_pause_resume_preserves_active_challenge_and_rejects_answer(self):
        self.initiate(self.a)
        challenge = Challenge.objects.get(run_id=self.run_id)
        pause_game(
            self.admin,
            RunCommand(str(uuid4()), self.run_id),
            now=NOW + timedelta(seconds=3),
        )
        paused = get_team_state(self.a, now=NOW + timedelta(minutes=2))
        self.assertEqual(paused.global_state, "PAUSED")
        self.assertEqual(paused.challenge.status, "active")
        with self.assertRaises(ApplicationError) as rejected:
            self.answer(self.a, challenge, "santa", now=NOW + timedelta(minutes=2))
        self.assertEqual(rejected.exception.code, "disallowed_state")
        self.assertFalse(ChallengeAttempt.objects.exists())
        resume_game(
            self.admin,
            RunCommand(str(uuid4()), self.run_id),
            now=NOW + timedelta(minutes=2),
        )
        self.assertEqual(get_team_state(self.a).team_state, "CHALLENGE")

    def test_admin_monitoring_fields_and_no_public_challenge_data(self):
        self.initiate(self.a)
        admin = get_admin_state(self.admin, now=NOW)
        self.assertEqual(admin.challenge.status, "active")
        self.assertEqual(admin.challenge.initiator_team_id, "a")
        self.assertEqual(admin.challenge.paid_cost, 2)
        team_a = next(team for team in admin.teams if team.team_id == "a")
        self.assertFalse(team_a.challenge_available)
        public = asdict(get_public_state(now=NOW))
        self.assertNotIn("challenge", public)
        self.assertNotIn("shared-challenge", str(public))

    def test_routes_keep_wrong_answer_context_and_guard_media(self):
        client = Client()
        client.force_login(self.a_user)
        response = client.post(
            reverse("team_action", args=["challenge"]),
            {"request_id": str(uuid4()), "run_id": self.run_id},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        challenge = Challenge.objects.get(run_id=self.run_id)
        state = get_team_state(self.a)
        response = client.post(
            reverse("team_challenge_answer"),
            {
                "request_id": str(uuid4()),
                "run_id": self.run_id,
                "challenge_id": challenge.id,
                "question_id": "shared-challenge",
                "answer": "wrong",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="question-pane"')
        current = get_team_state(self.a)
        self.assertEqual(_question_context(current), _question_context(state))
        self.assertEqual(
            _team_actions_context(current), _team_actions_context(state)
        )

        client.force_login(self.admin_user)
        missing = client.get(
            reverse(
                "challenge_media",
                kwargs={
                    "run_id": self.run_id,
                    "challenge_id": challenge.id,
                    "asset_path": "not-declared.png",
                },
            )
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(
            AuditEvent.objects.filter(action="submit_challenge_answer").count(), 1
        )
