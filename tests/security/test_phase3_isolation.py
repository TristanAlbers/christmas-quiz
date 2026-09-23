"""Phase 3 authorization and frozen-content isolation at public boundaries."""

from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from quiz.application import (
    admin_freeze,
    admin_unfreeze,
    freeze_opponent,
    get_admin_state,
    get_team_state,
    purchase_hint,
    purchase_uno_reverse,
    start_game,
    submit_answer,
    use_hint,
)
from quiz.contracts import (
    Actor,
    AdminTeam,
    ApplicationError,
    RunCommand,
    StartGame,
    SubmitAnswer,
    TeamPuzzle,
)
from quiz.models import AccountRole, AuditEvent, CommandReceipt, TeamRun


class PhaseThreeIsolationTests(TestCase):
    def setUp(self):
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)
        users = get_user_model()
        self.admin_user = users.objects.create_user("phase3-security-admin")
        self.a_user = users.objects.create_user("phase3-security-a")
        self.b_user = users.objects.create_user("phase3-security-b")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.a_user, role="team", team_id="a")
        AccountRole.objects.create(user=self.b_user, role="team", team_id="b")
        self.admin = Actor(self.admin_user.pk, "admin")
        self.a = Actor(self.a_user.pk, "team", "a")
        self.b = Actor(self.b_user.pk, "team", "b")
        self.started = timezone.now().replace(microsecond=0)
        self.run_id = start_game(
            self.admin,
            StartGame(str(uuid4()), "christmas-2026-demo"),
            now=self.started,
        ).run_id

    def command(self):
        return RunCommand(str(uuid4()), self.run_id)

    def team_command(self, team_id):
        return AdminTeam(str(uuid4()), self.run_id, team_id)

    def assert_error(self, code, call, *args, **kwargs):
        with self.assertRaises(ApplicationError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_frozen_team_loses_question_revealed_hint_media_and_all_interaction(self):
        purchase_hint(self.a, self.command(), now=self.started)
        use_hint(
            self.a,
            TeamPuzzle(str(uuid4()), self.run_id, "a-1"),
            now=self.started,
        )
        before = get_team_state(self.a, now=self.started)
        self.assertEqual(before.question.hint, "The colour starts with R.")
        media_url = before.question.media_urls[0]

        frozen_at = timezone.now()
        admin_freeze(
            self.admin,
            self.team_command("a"),
            now=frozen_at,
        )
        frozen = get_team_state(self.a, now=frozen_at)
        self.assertEqual(frozen.team_state, "FREEZE")
        self.assertIsNone(frozen.question)

        self.client.force_login(self.a_user)
        with patch(
            "quiz.web.media_views.server_now",
            return_value=frozen_at,
        ):
            self.assertEqual(self.client.get(media_url).status_code, 404)
        page = self.client.get(reverse("team"))
        poll = self.client.get(reverse("team_state"))
        for response in (page, poll):
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "Demo A1: North star")
            self.assertNotContains(response, "colour of the star")
            self.assertNotContains(response, "The colour starts with R.")
            self.assertNotContains(response, media_url)

        before_counts = (AuditEvent.objects.count(), CommandReceipt.objects.count())
        for call, command in (
            (
                submit_answer,
                SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red"),
            ),
            (purchase_hint, self.command()),
            (purchase_uno_reverse, self.command()),
            (
                freeze_opponent,
                RunCommand(str(uuid4()), self.run_id),
            ),
        ):
            self.assert_error(
                "disallowed_state",
                call,
                self.a,
                command,
                now=frozen_at,
            )
        self.assertEqual(
            (AuditEvent.objects.count(), CommandReceipt.objects.count()), before_counts
        )

    def test_client_expiry_fields_and_clock_values_cannot_unfreeze_or_answer(self):
        frozen_at = timezone.now()
        admin_freeze(self.admin, self.team_command("a"), now=frozen_at)
        self.client.force_login(self.a_user)
        response = self.client.post(
            reverse("team_answer"),
            {
                "request_id": str(uuid4()),
                "run_id": self.run_id,
                "question_id": "a-1",
                "answer": "red",
                "freeze_remaining_ms": "0",
                "freeze_started_gameplay_ms": "-999999999",
                "now": (frozen_at + timedelta(days=30)).isoformat(),
                "team_id": "b",
            },
        )
        self.assertEqual(response.status_code, 409)
        state = get_team_state(self.a, now=frozen_at + timedelta(seconds=1))
        self.assertEqual(state.team_state, "FREEZE")
        self.assertGreater(state.freeze_remaining_ms, 0)
        self.assertEqual(state.current_number, 1)

    def test_team_cannot_admin_freeze_unfreeze_or_choose_an_attack_target(self):
        before = (
            TeamRun.objects.get(run_id=self.run_id, team_id="a").points,
            TeamRun.objects.get(run_id=self.run_id, team_id="b").points,
        )
        for function in (admin_freeze, admin_unfreeze):
            self.assert_error(
                "forbidden",
                function,
                self.a,
                self.team_command("b"),
                now=self.started,
            )

        self.client.force_login(self.a_user)
        for action in ("freeze", "unfreeze"):
            response = self.client.post(
                reverse("admin_action", kwargs={"action": action}),
                {
                    "request_id": str(uuid4()),
                    "run_id": self.run_id,
                    "team_id": "b",
                },
            )
            self.assertEqual(response.status_code, 403)

        # The forged body target is ignored: a valid team attack always targets
        # the authenticated actor's opponent, never a client-selected team.
        response = self.client.post(
            reverse("team_action", kwargs={"action": "freeze"}),
            {
                "request_id": str(uuid4()),
                "run_id": self.run_id,
                "team_id": "a",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            TeamRun.objects.get(run_id=self.run_id, team_id="a").activity_state,
            "PUZZLE",
        )
        self.assertEqual(
            TeamRun.objects.get(run_id=self.run_id, team_id="b").activity_state,
            "FREEZE",
        )
        after = (
            TeamRun.objects.get(run_id=self.run_id, team_id="a").points,
            TeamRun.objects.get(run_id=self.run_id, team_id="b").points,
        )
        self.assertEqual(after, (before[0] - 3, before[1]))

    def test_reverse_is_private_to_owner_and_admin(self):
        purchase_uno_reverse(self.b, self.command(), now=self.started)
        self.assertFalse(get_team_state(self.a, now=self.started).uno_reverse_active)
        self.assertTrue(get_team_state(self.b, now=self.started).uno_reverse_active)
        admin = get_admin_state(self.admin, now=self.started)
        states = {team.team_id: team.uno_reverse_active for team in admin.teams}
        self.assertEqual(states, {"a": False, "b": True})

        self.client.force_login(self.a_user)
        response = self.client.get(reverse("team_state"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Team B")
        self.assertNotContains(response, "B Reverse")
