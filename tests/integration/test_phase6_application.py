"""Focused Phase 6 application, projection, route, and HTMX-boundary checks."""

import tempfile
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
    Run,
    TeamRun,
)
from quiz.web.views import _question_context, _team_actions_context

NOW = datetime(2026, 12, 24, 18, 0, tzinfo=timezone.utc)
GRACE_END = NOW + timedelta(seconds=30)


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

    def answer(self, actor, challenge, answer, *, request_id=None, now=GRACE_END):
        return submit_challenge_answer(
            actor,
            SubmitChallengeAnswer(
                request_id or str(uuid4()),
                self.run_id,
                str(challenge.id),
                challenge.question_id,
                answer,
            ),
            now=now,
        )

    def test_free_start_grace_retry_wrong_attempt_and_challenged_win(self):
        TeamRun.objects.filter(run_id=self.run_id, team_id="a").update(points=0)
        initial = get_team_state(self.a, now=NOW)
        self.assertTrue(initial.challenge_available)
        self.assertEqual(initial.challenge_cost, 0)
        self.assertTrue(initial.can_initiate_challenge)
        self.assertIsNone(initial.challenge_ineligible_reason)

        request_id = str(uuid4())
        started = self.initiate(self.a, request_id=request_id)
        retry = self.initiate(self.a, request_id=request_id)
        self.assertEqual(started, retry)
        challenge = Challenge.objects.get(run_id=self.run_id)
        self.assertEqual(challenge.question_id, "challenge-a-reindeer")
        self.assertEqual(challenge.paid_cost, 0)
        a_row = TeamRun.objects.get(run_id=self.run_id, team_id="a")
        self.assertEqual(a_row.points, 0)
        self.assertFalse(a_row.challenge_available)
        self.assertEqual(
            CommandReceipt.objects.filter(action="initiate_challenge").count(), 1
        )

        a_starting = get_team_state(self.a, now=NOW)
        b_starting = get_team_state(self.b, now=NOW)
        self.assertEqual(a_starting.challenge.role, "initiator")
        self.assertEqual(b_starting.challenge.role, "challenged")
        self.assertEqual(a_starting.challenge.phase, "starting")
        self.assertIsNone(a_starting.challenge.question)
        self.assertEqual(a_starting.challenge.grace_remaining_ms, 30_000)
        public_starting = get_public_state(now=NOW)
        self.assertEqual(public_starting.challenge.phase, "starting")
        self.assertIsNone(public_starting.challenge.title)
        self.assertIsNone(public_starting.challenge.body)

        with self.assertRaises(ApplicationError) as early:
            self.answer(self.b, challenge, "rudolph", now=NOW + timedelta(seconds=29))
        self.assertEqual(early.exception.code, "challenge_starting")
        self.assertFalse(ChallengeAttempt.objects.exists())

        b_active = get_team_state(self.b, now=GRACE_END)
        self.assertEqual(b_active.challenge.phase, "active")
        self.assertEqual(b_active.challenge.question.id, "challenge-a-reindeer")
        public_active = get_public_state(now=GRACE_END)
        self.assertEqual(public_active.challenge.phase, "active")
        self.assertEqual(public_active.challenge.title, "Rendierenappel")
        self.assertIn("gloeiende rode neus", public_active.challenge.body)

        wrong_id = str(uuid4())
        before_context = _question_context(b_active)
        wrong = self.answer(self.b, challenge, "wrong", request_id=wrong_id)
        wrong_retry = self.answer(self.b, challenge, "wrong", request_id=wrong_id)
        self.assertEqual(wrong.outcome, "incorrect")
        self.assertEqual(wrong_retry.outcome, "incorrect")
        self.assertEqual(_question_context(wrong.state), before_context)
        self.assertEqual(
            ChallengeAttempt.objects.filter(challenge=challenge).count(), 1
        )

        won = self.answer(
            self.b,
            challenge,
            "rudolph",
            now=GRACE_END + timedelta(seconds=1),
        )
        self.assertEqual(won.outcome, "won")
        challenge.refresh_from_db()
        self.assertEqual(challenge.winner_team_id, "b")
        self.assertFalse(challenge.freeze_applied)
        self.assertEqual(won.state.challenge.status, "resolved")
        self.assertIsNone(won.state.challenge.question)
        public_after = get_public_state(now=GRACE_END + timedelta(seconds=1))
        self.assertIsNone(public_after.challenge)
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

    def test_each_team_can_initiate_once_with_a_different_question(self):
        self.initiate(self.a)
        first = Challenge.objects.get(run_id=self.run_id)
        self.answer(self.b, first, "rudolph")
        second_start = GRACE_END + timedelta(seconds=1)
        self.initiate(self.b, now=second_start)
        second = Challenge.objects.get(run_id=self.run_id, initiator_team_id="b")
        self.assertEqual(second.question_id, "challenge-b-five-gifts")
        self.assertNotEqual(first.question_id, second.question_id)
        self.assertEqual(Challenge.objects.filter(run_id=self.run_id).count(), 2)

        second_active = second_start + timedelta(seconds=30)
        b_state = get_team_state(self.b, now=second_active)
        self.assertEqual(b_state.challenge.question.id, "challenge-b-five-gifts")
        public_second = get_public_state(now=second_active)
        self.assertEqual(public_second.challenge.challenge_number, 2)

        with self.assertRaises(ApplicationError) as spent:
            self.initiate(self.a, now=second_active)
        self.assertEqual(spent.exception.code, "challenge_spent")

    def test_initiator_win_applies_direct_freeze_and_preserves_reverse(self):
        TeamRun.objects.filter(run_id=self.run_id, team_id="b").update(
            reverse_active=True
        )
        self.initiate(self.a)
        challenge = Challenge.objects.get(run_id=self.run_id)
        result = self.answer(self.a, challenge, "rudolph", now=GRACE_END)
        self.assertEqual(result.outcome, "won")
        b_row = TeamRun.objects.get(run_id=self.run_id, team_id="b")
        self.assertEqual(b_row.activity_state, "FREEZE")
        self.assertEqual(b_row.freeze_started_gameplay_ms, 30_000)
        self.assertTrue(b_row.reverse_active)
        self.assertEqual(result.state.challenge.winner_team_id, "a")
        self.assertTrue(result.state.challenge.freeze_applied)

    def test_pause_resume_freezes_grace_clock_and_rejects_answer(self):
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
        self.assertEqual(paused.challenge.phase, "starting")
        self.assertEqual(paused.challenge.grace_remaining_ms, 27_000)
        with self.assertRaises(ApplicationError) as rejected:
            self.answer(self.a, challenge, "rudolph", now=NOW + timedelta(minutes=2))
        self.assertEqual(rejected.exception.code, "disallowed_state")
        self.assertFalse(ChallengeAttempt.objects.exists())
        resume_time = NOW + timedelta(minutes=2)
        resume_game(
            self.admin,
            RunCommand(str(uuid4()), self.run_id),
            now=resume_time,
        )
        resumed = get_team_state(self.a, now=resume_time)
        self.assertEqual(resumed.team_state, "CHALLENGE")
        self.assertEqual(resumed.challenge.grace_remaining_ms, 27_000)
        active = get_team_state(self.a, now=resume_time + timedelta(seconds=27))
        self.assertEqual(active.challenge.phase, "active")

    def test_admin_and_public_monitoring_fields(self):
        self.initiate(self.a)
        admin = get_admin_state(self.admin, now=NOW)
        self.assertEqual(admin.challenge.status, "active")
        self.assertEqual(admin.challenge.phase, "starting")
        self.assertEqual(admin.challenge.initiator_team_id, "a")
        self.assertEqual(admin.challenge.paid_cost, 0)
        self.assertEqual(admin.challenge.challenge_number, 1)
        team_a = next(team for team in admin.teams if team.team_id == "a")
        self.assertFalse(team_a.challenge_available)
        public = get_public_state(now=NOW)
        self.assertIsNotNone(public.challenge)
        self.assertEqual(public.challenge.initiator_team_id, "a")
        self.assertEqual(public.challenge.challenged_team_id, "b")
        self.assertEqual(public.challenge.grace_remaining_ms, 30_000)

    def test_routes_reject_grace_answers_then_keep_wrong_answer_context(self):
        client = Client()
        client.force_login(self.a_user)
        response = client.post(
            reverse("team_action", args=["challenge"]),
            {"request_id": str(uuid4()), "run_id": self.run_id},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        challenge = Challenge.objects.get(run_id=self.run_id)

        response = client.post(
            reverse("team_challenge_answer"),
            {
                "request_id": str(uuid4()),
                "run_id": self.run_id,
                "challenge_id": challenge.id,
                "question_id": challenge.question_id,
                "answer": "wrong",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, "challenge starting", status_code=409)

        Run.objects.filter(pk=self.run_id).update(
            gameplay_elapsed_ms=30_000,
            advent_clock_anchor=None,
        )
        state = get_team_state(self.a, now=NOW)
        response = client.post(
            reverse("team_challenge_answer"),
            {
                "request_id": str(uuid4()),
                "run_id": self.run_id,
                "challenge_id": challenge.id,
                "question_id": challenge.question_id,
                "answer": "wrong",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'id="question-pane"')
        current = get_team_state(self.a, now=NOW)
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
