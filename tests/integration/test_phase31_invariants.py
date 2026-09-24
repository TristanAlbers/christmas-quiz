"""Adversarial lifecycle coverage for the phase 3.1 no-active-run model."""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from quiz.application import (
    adjust_points,
    admin_freeze,
    get_admin_state,
    get_team_state,
    pause_game,
    purchase_uno_reverse,
    reset_game,
    resume_game,
    start_game,
    submit_answer,
)
from quiz.configuration import load_snapshot
from quiz.contracts import (
    Actor,
    AdminPoints,
    AdminTeam,
    ApplicationError,
    RunCommand,
    StartGame,
    SubmitAnswer,
)
from quiz.models import (
    AccountRole,
    AuditEvent,
    CommandReceipt,
    PuzzleProgress,
    Run,
    StartReceipt,
    TeamRun,
)


class Phase31LifecycleTests(TransactionTestCase):
    """Use transaction tests so competing writers use independent connections."""

    def setUp(self):
        super().setUp()
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)
        users = get_user_model()
        self.admin_user = users.objects.create_user("phase31-admin")
        self.admin2_user = users.objects.create_user("phase31-admin-2")
        self.a_user = users.objects.create_user("phase31-a")
        self.b_user = users.objects.create_user("phase31-b")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.admin2_user, role="admin")
        AccountRole.objects.create(user=self.a_user, role="team", team_id="a")
        AccountRole.objects.create(user=self.b_user, role="team", team_id="b")
        self.admin = Actor(self.admin_user.pk, "admin")
        self.admin2 = Actor(self.admin2_user.pk, "admin")
        self.a = Actor(self.a_user.pk, "team", "a")
        self.b = Actor(self.b_user.pk, "team", "b")
        self.now = timezone.now().replace(microsecond=0)

    def start(self, actor=None, request_id=None):
        return start_game(
            actor or self.admin,
            StartGame(request_id or str(uuid4()), "christmas-2026-demo"),
            now=self.now,
        )

    def command(self, run_id):
        return RunCommand(str(uuid4()), run_id)

    def assert_error(self, code, call, *args, **kwargs):
        with self.assertRaises(ApplicationError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_reset_archives_the_run_without_replacement_and_old_commands_are_stale(
        self,
    ):
        run_id = self.start().run_id
        adjust_points(
            self.admin, AdminPoints(str(uuid4()), run_id, "a", 8), now=self.now
        )
        purchase_uno_reverse(self.a, self.command(run_id), now=self.now)
        admin_freeze(self.admin, AdminTeam(str(uuid4()), run_id, "b"), now=self.now)
        old = Run.objects.get(pk=run_id)
        old_snapshot = old.snapshot_path
        old_progress = PuzzleProgress.objects.filter(run=old).count()
        old_teams = TeamRun.objects.filter(run=old).count()

        reset = reset_game(self.admin, self.command(run_id), now=self.now)
        self.assertEqual(reset.outcome, "reset")
        self.assertFalse(Run.objects.get(pk=run_id).active)
        self.assertFalse(Run.objects.filter(active=True).exists())
        self.assertEqual(TeamRun.objects.filter(run_id=run_id).count(), old_teams)
        self.assertEqual(
            PuzzleProgress.objects.filter(run_id=run_id).count(), old_progress
        )
        self.assertTrue(Path(old_snapshot).is_dir())
        self.assertTrue(
            AuditEvent.objects.filter(run_id=run_id, action="reset").exists()
        )
        self.assertTrue(
            CommandReceipt.objects.filter(run_id=run_id, action="reset").exists()
        )

        self.assert_error(
            "stale_run",
            submit_answer,
            self.a,
            SubmitAnswer(str(uuid4()), run_id, "a-1", "red"),
            now=self.now,
        )

    def test_waiting_projections_are_history_free_after_reset(self):
        run_id = self.start().run_id
        adjust_points(
            self.admin, AdminPoints(str(uuid4()), run_id, "a", 8), now=self.now
        )
        purchase_uno_reverse(self.a, self.command(run_id), now=self.now)
        reset_game(self.admin, self.command(run_id), now=self.now)

        waiting = get_team_state(self.a, now=self.now)
        self.assertEqual(
            (waiting.run_id, waiting.global_state, waiting.team_state),
            (None, "READY", "READY"),
        )
        self.assertEqual(waiting.points, 0)
        self.assertIsNone(waiting.current_number)
        self.assertEqual(waiting.completed_numbers, ())
        self.assertEqual(waiting.fragments, ())
        self.assertIsNone(waiting.question)
        self.assertEqual(waiting.hint_tokens, 0)
        self.assertIsNone(waiting.freeze_remaining_ms)
        self.assertFalse(waiting.uno_reverse_active)

        admin = get_admin_state(self.admin, now=self.now)
        self.assertEqual(
            (admin.run_id, admin.global_state, admin.package_id, admin.teams),
            (None, "READY", None, ()),
        )

    def test_recovery_keeps_pinned_snapshot_and_phase_three_state_after_source_loss(
        self,
    ):
        games = TemporaryDirectory()
        self.addCleanup(games.cleanup)
        source = Path(games.name) / "christmas-2026-demo"
        shutil.copytree(Path("games/christmas-2026-demo"), source)
        scope = override_settings(QUIZ_GAMES_ROOT=Path(games.name))
        scope.enable()
        self.addCleanup(scope.disable)
        run_id = self.start().run_id
        adjust_points(
            self.admin, AdminPoints(str(uuid4()), run_id, "a", 8), now=self.now
        )
        purchase_uno_reverse(self.a, self.command(run_id), now=self.now)
        frozen_at = self.now + timedelta(seconds=10)
        admin_freeze(self.admin, AdminTeam(str(uuid4()), run_id, "b"), now=frozen_at)
        pause_at = frozen_at + timedelta(seconds=15)
        pause_game(self.admin, self.command(run_id), now=pause_at)
        before = get_team_state(self.b, now=pause_at)
        snapshot = Path(Run.objects.get(pk=run_id).snapshot_path)

        # A source package may change or vanish after Start.  A new process
        # connection must continue exclusively from the run snapshot.
        source_config = source / "game.json"
        changed = json.loads(source_config.read_text())
        changed["teams"]["a"]["puzzles"][0]["title"] = "Source must not leak"
        source_config.write_text(json.dumps(changed))
        shutil.rmtree(source)
        connections["default"].close()
        recovered_a = get_team_state(self.a, now=pause_at + timedelta(days=1))
        recovered_b = get_team_state(self.b, now=pause_at + timedelta(days=1))
        self.assertEqual(recovered_a.run_id, run_id)
        self.assertTrue(recovered_a.uno_reverse_active)
        self.assertEqual(recovered_b.global_state, "PAUSED")
        self.assertEqual(recovered_b.freeze_remaining_ms, before.freeze_remaining_ms)
        self.assertTrue(snapshot.is_dir())
        resume_game(self.admin, self.command(run_id), now=pause_at + timedelta(days=1))
        self.assertEqual(
            get_team_state(self.a, now=pause_at + timedelta(days=1)).question.title,
            "Demo A1: North star",
        )

    def test_simultaneous_starts_create_at_most_one_active_run_and_one_initialization(
        self,
    ):
        request_a, request_b = str(uuid4()), str(uuid4())

        def attempt(actor, request_id):
            connections["default"].close()
            try:
                return ("ok", self.start(actor, request_id).run_id)
            except ApplicationError as exc:
                return ("error", exc.code)
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(
                pool.map(
                    lambda args: attempt(*args),
                    ((self.admin, request_a), (self.admin2, request_b)),
                )
            )
        accepted = [value for kind, value in results if kind == "ok"]
        self.assertEqual(len(accepted), 1, results)
        self.assertEqual(Run.objects.filter(active=True).count(), 1)
        run = Run.objects.get(active=True)
        self.assertEqual(TeamRun.objects.filter(run=run).count(), 2)
        config = load_snapshot(run)
        expected_progress = sum(
            len(config["teams"][team_id]["puzzles"]) for team_id in ("a", "b")
        )
        self.assertEqual(
            PuzzleProgress.objects.filter(run=run).count(), expected_progress
        )
        self.assertEqual(StartReceipt.objects.filter(run=run).count(), 1)

    def test_start_request_retry_survives_reset_and_source_unavailability(self):
        request_id = str(uuid4())
        first = self.start(request_id=request_id)
        reset_game(self.admin, self.command(first.run_id), now=self.now)
        retry = self.start(request_id=request_id)
        self.assertEqual(retry, first)
        self.assertFalse(Run.objects.filter(active=True).exists())

    def test_simultaneous_resets_leave_one_archived_run_and_no_replacement(self):
        run_id = self.start().run_id

        def attempt(actor):
            connections["default"].close()
            try:
                return (
                    "ok",
                    reset_game(actor, self.command(run_id), now=self.now).outcome,
                )
            except ApplicationError as exc:
                return ("error", exc.code)
            finally:
                connections["default"].close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(attempt, (self.admin, self.admin2)))

        self.assertEqual(sum(kind == "ok" for kind, _ in results), 1, results)
        self.assertFalse(Run.objects.filter(active=True).exists())
        self.assertEqual(Run.objects.count(), 1)
        self.assertTrue(
            AuditEvent.objects.filter(run_id=run_id, action="reset").exists()
        )

    def test_reset_then_source_edit_starts_a_new_snapshot_from_current_source(self):
        games = TemporaryDirectory()
        self.addCleanup(games.cleanup)
        source = Path(games.name) / "christmas-2026-demo"
        shutil.copytree(Path("games/christmas-2026-demo"), source)
        scope = override_settings(QUIZ_GAMES_ROOT=Path(games.name))
        scope.enable()
        self.addCleanup(scope.disable)

        first = self.start()
        first_run = Run.objects.get(pk=first.run_id)
        reset_game(self.admin, self.command(first.run_id), now=self.now)
        config_path = source / "game.json"
        config = json.loads(config_path.read_text())
        config["teams"]["a"]["puzzles"][0]["title"] = "Changed only for run two"
        config_path.write_text(json.dumps(config))

        second = self.start(request_id=str(uuid4()))
        second_run = Run.objects.get(pk=second.run_id)
        self.assertNotEqual(first.run_id, second.run_id)
        self.assertNotEqual(first_run.snapshot_digest, second_run.snapshot_digest)
        self.assertEqual(
            get_team_state(self.a, now=self.now).question.title,
            "Changed only for run two",
        )
