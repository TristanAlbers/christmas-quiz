"""Phase 2 authorization and team-private Hint checks at public boundaries."""

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from quiz.application import (
    adjust_points,
    force_complete_current,
    get_admin_state,
    get_team_state,
    pause_game,
    provide_hint,
    purchase_hint,
    reset_game,
    resume_game,
    skip_current,
    start_game,
    use_hint,
)
from quiz.contracts import (
    Actor,
    AdminPoints,
    AdminPuzzle,
    ApplicationError,
    RunCommand,
    StartGame,
    TeamPuzzle,
)
from quiz.models import AccountRole, AuditEvent, CommandReceipt, HintReveal, TeamRun


class PhaseTwoIsolationTests(TestCase):
    def setUp(self):
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)
        users = get_user_model()
        admin = users.objects.create_user("security-phase2-admin", password="pin")
        a = users.objects.create_user("security-phase2-a", password="pin")
        b = users.objects.create_user("security-phase2-b", password="pin")
        AccountRole.objects.create(user=admin, role="admin")
        AccountRole.objects.create(user=a, role="team", team_id="a")
        AccountRole.objects.create(user=b, role="team", team_id="b")
        self.admin = Actor(admin.pk, "admin")
        self.a = Actor(a.pk, "team", "a")
        self.b = Actor(b.pk, "team", "b")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id

    def assert_forbidden(self, func, actor, command):
        with self.assertRaises(ApplicationError) as caught:
            func(actor, command)
        self.assertEqual(caught.exception.code, "forbidden")

    def test_team_actor_cannot_use_any_admin_command_even_with_forged_target(self):
        calls = [
            (pause_game, RunCommand(str(uuid4()), self.run_id)),
            (resume_game, RunCommand(str(uuid4()), self.run_id)),
            (adjust_points, AdminPoints(str(uuid4()), self.run_id, "b", 100)),
            (
                force_complete_current,
                AdminPuzzle(str(uuid4()), self.run_id, "b", "b-1"),
            ),
            (provide_hint, AdminPuzzle(str(uuid4()), self.run_id, "b", "b-1")),
            (reset_game, RunCommand(str(uuid4()), self.run_id)),
        ]
        before = (AuditEvent.objects.count(), CommandReceipt.objects.count())
        for func, command in calls:
            self.assert_forbidden(func, self.a, command)
        self.assertEqual(
            (AuditEvent.objects.count(), CommandReceipt.objects.count()), before
        )
        self.assertEqual(TeamRun.objects.get(run_id=self.run_id, team_id="b").points, 3)
        self.assertFalse(HintReveal.objects.exists())

    def test_forged_team_identity_cannot_buy_skip_or_reveal_for_opponent(self):
        forged = Actor(self.a.user_id, "team", "b")
        commands = [
            (purchase_hint, RunCommand(str(uuid4()), self.run_id)),
            (use_hint, TeamPuzzle(str(uuid4()), self.run_id, "b-1")),
            (skip_current, TeamPuzzle(str(uuid4()), self.run_id, "b-1")),
        ]
        for func, command in commands:
            self.assert_forbidden(func, forged, command)
        with self.assertRaises(ApplicationError) as caught:
            get_team_state(forged)
        self.assertEqual(caught.exception.code, "forbidden")
        self.assertEqual(TeamRun.objects.get(run_id=self.run_id, team_id="b").points, 3)
        self.assertFalse(HintReveal.objects.exists())

    def test_question_id_cannot_select_other_team_and_hint_text_stays_private(self):
        purchase_hint(self.a, RunCommand(str(uuid4()), self.run_id))
        before = (AuditEvent.objects.count(), CommandReceipt.objects.count())
        for func in (use_hint, skip_current):
            with self.assertRaises(ApplicationError) as caught:
                func(self.a, TeamPuzzle(str(uuid4()), self.run_id, "b-1"))
            self.assertEqual(caught.exception.code, "stale_question")
        self.assertEqual(
            (AuditEvent.objects.count(), CommandReceipt.objects.count()), before
        )
        self.assertEqual(
            use_hint(self.a, TeamPuzzle(str(uuid4()), self.run_id, "a-1")).outcome,
            "revealed",
        )
        self.assertEqual(
            get_team_state(self.a).question.hint,
            "De Engelse kleur begint met een R.",
        )
        self.assertIsNone(get_team_state(self.b).question.hint)
        self.assertEqual(get_team_state(self.b).hint_tokens, 0)
        self.assertEqual(HintReveal.objects.filter(team_id="b").count(), 0)
        with self.assertRaises(ApplicationError) as caught:
            get_admin_state(self.a)
        self.assertEqual(caught.exception.code, "forbidden")

    def test_admin_actor_cannot_spend_a_team_inventory_as_player(self):
        for func, command in (
            (purchase_hint, RunCommand(str(uuid4()), self.run_id)),
            (use_hint, TeamPuzzle(str(uuid4()), self.run_id, "a-1")),
            (skip_current, TeamPuzzle(str(uuid4()), self.run_id, "a-1")),
        ):
            self.assert_forbidden(func, self.admin, command)
        self.assertFalse(HintReveal.objects.exists())
        self.assertEqual(TeamRun.objects.get(run_id=self.run_id, team_id="a").points, 3)

    def test_http_actions_use_session_identity_and_admin_role(self):
        self.client.force_login(get_user_model().objects.get(pk=self.a.user_id))
        admin_url = reverse("admin_action", kwargs={"action": "pause"})
        denied = self.client.post(
            admin_url,
            {"request_id": str(uuid4()), "run_id": self.run_id},
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(get_team_state(self.a).global_state, "ADVENT_QUIZ")

        def post_team(action, **fields):
            return self.client.post(
                reverse("team_action", kwargs={"action": action}),
                {
                    "request_id": str(uuid4()),
                    "run_id": self.run_id,
                    "question_id": "a-1",
                    "team_id": "b",  # forged body value must be ignored
                    **fields,
                },
            )

        self.assertEqual(post_team("purchase-hint").status_code, 302)
        self.assertEqual(post_team("use-hint").status_code, 302)
        self.assertEqual(
            get_team_state(self.a).question.hint,
            "De Engelse kleur begint met een R.",
        )
        self.assertIsNone(get_team_state(self.b).question.hint)
        self.assertEqual(post_team("skip").status_code, 302)
        self.assertEqual(get_team_state(self.a).current_number, 2)
        self.assertEqual(get_team_state(self.b).current_number, 1)

        self.client.force_login(get_user_model().objects.get(pk=self.admin.user_id))
        for action in ("pause", "resume", "reset"):
            response = self.client.post(
                reverse("admin_action", kwargs={"action": action}),
                {"request_id": str(uuid4()), "run_id": self.run_id},
            )
            self.assertEqual(response.status_code, 302)
        self.assertIsNone(get_team_state(self.a).run_id)
        self.assertEqual(get_team_state(self.a).global_state, "READY")
