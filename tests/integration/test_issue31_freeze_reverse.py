from datetime import UTC, datetime
from tempfile import TemporaryDirectory
from pathlib import Path
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from quiz.application import (
    freeze_opponent,
    get_team_state,
    purchase_uno_reverse,
    start_game,
)
from quiz.contracts import Actor, ApplicationError, RunCommand, StartGame
from quiz.models import AccountRole, AuditEvent, TeamRun
from quiz.web.team_presentation import get_team_presentation_state


class Issue31FreezeReverseTests(TestCase):
    def setUp(self):
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("issue31-admin")
        a_user = users.objects.create_user("issue31-a")
        b_user = users.objects.create_user("issue31-b")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=a_user, role="team", team_id="a")
        AccountRole.objects.create(user=b_user, role="team", team_id="b")
        self.admin = Actor(admin_user.pk, "admin")
        self.a = Actor(a_user.pk, "team", "a")
        self.b = Actor(b_user.pk, "team", "b")
        self.now = datetime(2026, 12, 25, 12, tzinfo=UTC)
        self.run_id = start_game(
            self.admin,
            StartGame(str(uuid4()), "christmas-2026-demo"),
            now=self.now,
        ).run_id
        TeamRun.objects.filter(run_id=self.run_id).update(points=20)

    def command(self):
        return RunCommand(str(uuid4()), self.run_id)

    def test_normal_freeze_projects_eligibility_and_one_authoritative_event(self):
        result = freeze_opponent(self.a, self.command(), now=self.now)
        self.assertEqual(result.outcome, "frozen")

        state_a = get_team_state(self.a, now=self.now)
        state_b = get_team_state(self.b, now=self.now)
        ui_a = get_team_presentation_state(
            self.run_id, "a", state_a.gameplay_elapsed_ms
        )
        ui_b = get_team_presentation_state(
            self.run_id, "b", state_b.gameplay_elapsed_ms
        )
        self.assertTrue(ui_a.opponent_freeze_active)
        self.assertFalse(ui_b.opponent_freeze_active)
        self.assertEqual(ui_a.event, ui_b.event)
        self.assertEqual(ui_a.event.attacker_team_id, "a")
        self.assertEqual(ui_a.event.target_team_id, "b")
        self.assertEqual(ui_a.event.frozen_team_id, "b")
        self.assertFalse(ui_a.event.reversed)

        points = get_team_state(self.a, now=self.now).points
        revision = ui_a.event.id
        audit_count = AuditEvent.objects.filter(action="freeze_attack").count()
        with self.assertRaises(ApplicationError) as raised:
            freeze_opponent(self.a, self.command(), now=self.now)
        self.assertEqual(raised.exception.code, "already_active")
        self.assertEqual(get_team_state(self.a, now=self.now).points, points)
        current = get_team_presentation_state(
            self.run_id, "a", state_a.gameplay_elapsed_ms
        )
        self.assertEqual(current.event.id, revision)
        self.assertEqual(
            AuditEvent.objects.filter(action="freeze_attack").count(), audit_count
        )

    def test_reverse_consumes_once_and_projects_reflected_attack(self):
        purchase_uno_reverse(self.a, self.command(), now=self.now)
        result = freeze_opponent(self.b, self.command(), now=self.now)
        self.assertEqual(result.outcome, "reversed")

        state_a = get_team_state(self.a, now=self.now)
        state_b = get_team_state(self.b, now=self.now)
        self.assertEqual(state_a.team_state, "PUZZLE")
        self.assertFalse(state_a.uno_reverse_active)
        self.assertEqual(state_b.team_state, "FREEZE")

        ui_a = get_team_presentation_state(
            self.run_id, "a", state_a.gameplay_elapsed_ms
        )
        ui_b = get_team_presentation_state(
            self.run_id, "b", state_b.gameplay_elapsed_ms
        )
        self.assertEqual(ui_a.event, ui_b.event)
        self.assertTrue(ui_a.event.reversed)
        self.assertEqual(ui_a.event.attacker_team_id, "b")
        self.assertEqual(ui_a.event.target_team_id, "a")
        self.assertEqual(ui_a.event.frozen_team_id, "b")
