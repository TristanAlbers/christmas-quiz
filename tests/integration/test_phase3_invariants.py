"""Cross-cutting Phase 3 clock, effect, receipt, and race invariants."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from quiz.application import (
    adjust_points,
    admin_freeze,
    admin_unfreeze,
    freeze_opponent,
    get_admin_state,
    get_team_state,
    pause_game,
    purchase_uno_reverse,
    resume_game,
    start_game,
    submit_answer,
)
from quiz.contracts import (
    Actor,
    AdminPoints,
    AdminTeam,
    ApplicationError,
    RunCommand,
    StartGame,
    SubmitAnswer,
)
from quiz.models import AccountRole, AuditEvent, CommandReceipt, TeamRun
from quiz.persistence import immediate_transaction


class PhaseThreeSetup:
    def setUp(self):
        super().setUp()
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)
        users = get_user_model()
        admin = users.objects.create_user("phase3-admin", password="pin")
        team_a = users.objects.create_user("phase3-a", password="pin")
        team_b = users.objects.create_user("phase3-b", password="pin")
        AccountRole.objects.create(user=admin, role="admin")
        AccountRole.objects.create(user=team_a, role="team", team_id="a")
        AccountRole.objects.create(user=team_b, role="team", team_id="b")
        self.admin = Actor(admin.pk, "admin")
        self.a = Actor(team_a.pk, "team", "a")
        self.b = Actor(team_b.pk, "team", "b")
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

    def add_points(self, team_id, amount, *, now=None):
        return adjust_points(
            self.admin,
            AdminPoints(str(uuid4()), self.run_id, team_id, amount),
            now=now or self.started,
        )

    def assert_error(self, code, call, *args, **kwargs):
        with self.assertRaises(ApplicationError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def restart_database_connection(self):
        """Use a new connection when the suite has a durable SQLite database."""
        if os.environ.get("TEST_DATABASE_PATH") not in (None, "", ":memory:"):
            connections["default"].close()


class PhaseThreeClockAndEffectTests(PhaseThreeSetup, TransactionTestCase):
    def test_pause_and_paused_restart_preserve_exact_freeze_remaining_time(self):
        freeze_at = self.started + timedelta(seconds=10)
        pause_at = freeze_at + timedelta(seconds=75)
        admin_freeze(self.admin, self.team_command("a"), now=freeze_at)
        self.assertEqual(
            get_team_state(self.a, now=pause_at).freeze_remaining_ms,
            225_000,
        )

        pause_game(self.admin, self.command(), now=pause_at)
        self.restart_database_connection()
        a_day_later = pause_at + timedelta(days=1)
        paused = get_team_state(self.a, now=a_day_later)
        self.assertEqual(paused.global_state, "PAUSED")
        self.assertEqual(paused.team_state, "FREEZE")
        self.assertEqual(paused.freeze_remaining_ms, 225_000)

        resume_game(self.admin, self.command(), now=a_day_later)
        self.assertEqual(
            get_team_state(
                self.a, now=a_day_later + timedelta(milliseconds=224_999)
            ).freeze_remaining_ms,
            1,
        )
        boundary = get_team_state(
            self.a, now=a_day_later + timedelta(milliseconds=225_000)
        )
        self.assertEqual(boundary.team_state, "PUZZLE")
        self.assertIsNone(boundary.freeze_remaining_ms)
        self.assertIsNotNone(boundary.question)

    def test_active_advent_downtime_counts_and_boundary_reconciles_on_command(self):
        freeze_at = self.started + timedelta(seconds=5)
        admin_freeze(self.admin, self.team_command("a"), now=freeze_at)
        self.restart_database_connection()
        before_boundary = freeze_at + timedelta(milliseconds=299_999)
        self.assertEqual(
            get_team_state(self.a, now=before_boundary).freeze_remaining_ms,
            1,
        )
        self.assert_error(
            "disallowed_state",
            submit_answer,
            self.a,
            SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red"),
            now=before_boundary,
        )

        boundary = freeze_at + timedelta(milliseconds=300_000)
        result = submit_answer(
            self.a,
            SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red"),
            now=boundary,
        )
        self.assertEqual(result.outcome, "completed")
        stored = TeamRun.objects.get(run_id=self.run_id, team_id="a")
        self.assertEqual(stored.activity_state, "PUZZLE")
        self.assertIsNone(stored.freeze_started_gameplay_ms)

    def test_admin_freeze_while_paused_starts_stopped_and_unfreeze_is_immediate(self):
        pause_at = self.started + timedelta(seconds=20)
        pause_game(self.admin, self.command(), now=pause_at)
        frozen = admin_freeze(
            self.admin,
            self.team_command("b"),
            now=pause_at + timedelta(hours=2),
        )
        self.assertEqual(frozen.outcome, "frozen")
        self.assertEqual(
            get_team_state(
                self.b, now=pause_at + timedelta(days=2)
            ).freeze_remaining_ms,
            300_000,
        )
        unfrozen = admin_unfreeze(
            self.admin,
            self.team_command("b"),
            now=pause_at + timedelta(days=2),
        )
        self.assertEqual(unfrozen.outcome, "unfrozen")
        state = get_team_state(self.b, now=pause_at + timedelta(days=2))
        self.assertEqual(state.team_state, "PUZZLE")
        self.assertIsNone(state.freeze_remaining_ms)

    def test_reverse_and_freeze_receipts_are_idempotent_and_conflicts_reject(self):
        self.add_points("b", 10)
        purchase = self.command()
        first_purchase = purchase_uno_reverse(self.b, purchase, now=self.started)
        self.assertEqual(
            purchase_uno_reverse(self.b, purchase, now=self.started), first_purchase
        )
        after_purchase = get_team_state(self.b, now=self.started)
        self.assertTrue(after_purchase.uno_reverse_active)
        self.assertEqual(after_purchase.points, 11)
        self.assert_error(
            "already_active",
            purchase_uno_reverse,
            self.b,
            self.command(),
            now=self.started,
        )

        attack = self.command()
        first_attack = freeze_opponent(self.a, attack, now=self.started)
        self.assertEqual(
            freeze_opponent(self.a, attack, now=self.started), first_attack
        )
        self.assertEqual(get_team_state(self.a, now=self.started).points, 0)
        self.assertEqual(get_team_state(self.a, now=self.started).team_state, "FREEZE")
        target = get_team_state(self.b, now=self.started)
        self.assertEqual(target.team_state, "PUZZLE")
        self.assertFalse(target.uno_reverse_active)
        self.assertEqual(AuditEvent.objects.filter(action="freeze_attack").count(), 1)
        self.assertEqual(
            CommandReceipt.objects.filter(action="freeze_attack").count(), 1
        )

    def test_team_projection_exposes_freeze_eligibility_and_latest_attack_event(self):
        self.add_points("a", 10)
        before = get_team_state(self.a, now=self.started)
        self.assertFalse(before.opponent_freeze_active)
        self.assertIsNone(before.presentation_event)

        result = freeze_opponent(self.a, self.command(), now=self.started)
        self.assertEqual(result.outcome, "frozen")

        attacker = get_team_state(self.a, now=self.started)
        target = get_team_state(self.b, now=self.started)
        self.assertTrue(attacker.opponent_freeze_active)
        self.assertFalse(target.opponent_freeze_active)
        for state in (attacker, target):
            event = state.presentation_event
            self.assertIsNotNone(event)
            self.assertEqual(event.kind, "freeze_attack")
            self.assertEqual(event.attacker_team_id, "a")
            self.assertEqual(event.target_team_id, "b")
            self.assertEqual(event.frozen_team_id, "b")
            self.assertFalse(event.reversed)

    def test_duplicate_freeze_rejection_keeps_points_and_event_revision_unchanged(self):
        self.add_points("a", 10)
        first = freeze_opponent(self.a, self.command(), now=self.started)
        self.assertEqual(first.outcome, "frozen")
        state = get_team_state(self.a, now=self.started)
        points_after_first = state.points
        event_id = state.presentation_event.id
        audit_count = AuditEvent.objects.filter(action="freeze_attack").count()

        self.assert_error(
            "already_active",
            freeze_opponent,
            self.a,
            self.command(),
            now=self.started,
        )
        after = get_team_state(self.a, now=self.started)
        self.assertEqual(after.points, points_after_first)
        self.assertEqual(after.presentation_event.id, event_id)
        self.assertEqual(
            AuditEvent.objects.filter(action="freeze_attack").count(), audit_count
        )

    def test_projection_admin_read_and_command_use_same_clock_boundary(self):
        freeze_at = self.started + timedelta(seconds=8)
        admin_freeze(self.admin, self.team_command("a"), now=freeze_at)
        boundary = freeze_at + timedelta(minutes=5)
        team = get_team_state(self.a, now=boundary)
        admin = get_admin_state(self.admin, now=boundary)
        admin_team = next(item for item in admin.teams if item.team_id == "a")
        self.assertEqual(team.team_state, admin_team.activity_state)
        self.assertEqual(team.freeze_remaining_ms, admin_team.freeze_remaining_ms)
        self.assertEqual(team.team_state, "PUZZLE")

        # A mutating command at the same instant persists the same reconciliation.
        purchase_uno_reverse(self.a, self.command(), now=boundary)
        stored = TeamRun.objects.get(run_id=self.run_id, team_id="a")
        self.assertEqual(stored.activity_state, "PUZZLE")
        self.assertIsNone(stored.freeze_started_gameplay_ms)

    def test_poll_projection_never_acquires_the_sqlite_writer_slot(self):
        connection = connections["default"]
        statements = []
        with connection.execute_wrapper(
            lambda execute, sql, params, many, context: (
                statements.append(sql) or execute(sql, params, many, context)
            )
        ):
            get_team_state(self.a, now=self.started + timedelta(seconds=1))
        normalized = {sql.strip().upper() for sql in statements}
        self.assertNotIn("BEGIN IMMEDIATE", normalized)

    def test_frozen_attacker_is_ineligible_without_charge(self):
        admin_freeze(self.admin, self.team_command("a"), now=self.started)
        before = TeamRun.objects.get(run_id=self.run_id, team_id="a").points
        self.assert_error(
            "disallowed_state",
            freeze_opponent,
            self.a,
            self.command(),
            now=self.started,
        )
        self.assertEqual(
            TeamRun.objects.get(run_id=self.run_id, team_id="a").points, before
        )
        self.assertFalse(AuditEvent.objects.filter(action="freeze_attack").exists())

    def test_finished_target_is_ineligible_without_charge(self):
        # The compact demo package is intentionally not the 25-puzzle finish
        # package, so establish the target precondition directly.
        TeamRun.objects.filter(run_id=self.run_id, team_id="b").update(
            activity_state="FINISHED"
        )
        self.assertEqual(
            get_team_state(self.b, now=self.started).team_state, "FINISHED"
        )
        before = get_team_state(self.a, now=self.started).points
        self.assert_error(
            "disallowed_state",
            freeze_opponent,
            self.a,
            self.command(),
            now=self.started,
        )
        self.assertEqual(get_team_state(self.a, now=self.started).points, before)


class PhaseThreeRaceTests(PhaseThreeSetup, TransactionTestCase):
    def setUp(self):
        if (
            not os.environ.get("TEST_DATABASE_PATH")
            or os.environ["TEST_DATABASE_PATH"] == ":memory:"
        ):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        super().setUp()

    def _compete(self, first, second):
        attempted = Event()

        def contender():
            connections.close_all()
            connection = connections["default"]
            connection.ensure_connection()
            connection.connection.set_trace_callback(
                lambda sql: attempted.set()
                if sql.strip().upper() == "BEGIN IMMEDIATE"
                else None
            )
            try:
                return second()
            except ApplicationError as error:
                return error
            finally:
                connection.connection.set_trace_callback(None)
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with immediate_transaction():
                first_result = first()
                future = pool.submit(contender)
                self.assertTrue(attempted.wait(2))
                self.assertFalse(future.done())
            second_result = future.result(timeout=8)
        return first_result, second_result

    def test_two_paid_attacks_consume_one_reverse_and_charge_only_first(self):
        self.add_points("a", 10)
        self.add_points("b", 10)
        purchase_uno_reverse(self.b, self.command(), now=self.started)
        before = get_team_state(self.a, now=self.started).points
        first, second = self._compete(
            lambda: freeze_opponent(self.a, self.command(), now=self.started),
            lambda: freeze_opponent(self.a, self.command(), now=self.started),
        )
        self.assertEqual(first.outcome, "reversed")
        self.assertIsInstance(second, ApplicationError)
        self.assertEqual(second.code, "disallowed_state")
        attacker = get_team_state(self.a, now=self.started)
        target = get_team_state(self.b, now=self.started)
        self.assertEqual(attacker.points, before - attacker.freeze_cost)
        self.assertEqual(attacker.team_state, "FREEZE")
        self.assertEqual(target.team_state, "PUZZLE")
        self.assertFalse(target.uno_reverse_active)
        self.assertEqual(AuditEvent.objects.filter(action="freeze_attack").count(), 1)
        self.assertEqual(
            CommandReceipt.objects.filter(action="freeze_attack").count(), 1
        )

    def test_concurrent_reverse_purchases_charge_once(self):
        self.add_points("a", 10)
        before = get_team_state(self.a, now=self.started).points
        first, second = self._compete(
            lambda: purchase_uno_reverse(self.a, self.command(), now=self.started),
            lambda: purchase_uno_reverse(self.a, self.command(), now=self.started),
        )
        self.assertEqual(first.outcome, "purchased")
        self.assertIsInstance(second, ApplicationError)
        self.assertEqual(second.code, "already_active")
        state = get_team_state(self.a, now=self.started)
        self.assertTrue(state.uno_reverse_active)
        self.assertEqual(state.points, before - state.uno_reverse_cost)
        self.assertEqual(
            AuditEvent.objects.filter(action="purchase_uno_reverse").count(), 1
        )
