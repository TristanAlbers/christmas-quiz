"""Focused phase-3.1 package discovery and compatibility migration checks."""

import importlib
import json
import tempfile
from pathlib import Path
from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings

from quiz.configuration import InvalidPackage, discover_packages, stage_snapshot


def _puzzle(team_id, number, media=None):
    return {
        "id": f"{team_id}-{number}",
        "number": number,
        "title": f"Puzzle {number}",
        "body": "Clue",
        "validator": {"type": "text_exact", "answer": "secret"},
        "reward_points": 1,
        "hint": None,
        "fragment": None,
        "media": media or [],
    }


def _write_package(root, package_id, *, media=None):
    package = root / package_id
    package.mkdir(parents=True)
    config = {
        "schema_version": 3,
        "package_id": package_id,
        "initial_points": 3,
        "hint_cost": 1,
        "skip_cost": 2,
        "freeze_cost": 3,
        "uno_reverse_cost": 4,
        "teams": {
            team_id: {
                "puzzles": [
                    _puzzle(team_id, 1, media if team_id == "a" else None),
                    _puzzle(team_id, 2),
                ]
            }
            for team_id in ("a", "b")
        },
    }
    (package / "game.json").write_text(json.dumps(config))
    return package


class Phase31PackageDiscoveryTests(TestCase):
    def test_discovery_lists_only_direct_directories_without_staging(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            games = root / "games"
            snapshots = root / "snapshots"
            games.mkdir()
            _write_package(games, "valid-package")
            invalid = games / "invalid-package"
            invalid.mkdir()
            (invalid / "game.json").write_text("not JSON")
            (games / "not-a-package.txt").write_text("ignored")
            nested = games / "container" / "nested-package"
            _write_package(nested.parent, nested.name)

            with override_settings(
                QUIZ_GAMES_ROOT=games,
                QUIZ_SNAPSHOT_ROOT=snapshots,
            ):
                packages = discover_packages()

            self.assertEqual(
                [(item.package_id, item.startable) for item in packages],
                [
                    ("container", False),
                    ("invalid-package", False),
                    ("valid-package", True),
                ],
            )
            self.assertIn("game.json", packages[0].diagnostic)
            self.assertIn("game.json", packages[1].diagnostic)
            self.assertIsNone(packages[2].diagnostic)
            self.assertFalse(snapshots.exists())

    def test_missing_media_is_actionable_and_start_staging_leaves_no_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            games = root / "games"
            snapshots = root / "snapshots"
            games.mkdir()
            _write_package(games, "missing-media", media=["media/clue.txt"])

            with override_settings(
                QUIZ_GAMES_ROOT=games,
                QUIZ_SNAPSHOT_ROOT=snapshots,
            ):
                packages = discover_packages()
                self.assertEqual(len(packages), 1)
                self.assertFalse(packages[0].startable)
                self.assertIn("media file is missing", packages[0].diagnostic)
                self.assertFalse(snapshots.exists())

                with self.assertRaisesRegex(InvalidPackage, "media file is missing"):
                    stage_snapshot("missing-media")

            self.assertFalse(snapshots.exists())

    def test_staging_revalidates_media_after_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            games = root / "games"
            snapshots = root / "snapshots"
            games.mkdir()
            package = _write_package(
                games, "mutable-package", media=["media/clue.txt"]
            )
            media = package / "media" / "clue.txt"
            media.parent.mkdir()
            media.write_text("clue")

            with override_settings(
                QUIZ_GAMES_ROOT=games,
                QUIZ_SNAPSHOT_ROOT=snapshots,
            ):
                self.assertTrue(discover_packages()[0].startable)
                media.unlink()
                with self.assertRaises(InvalidPackage):
                    stage_snapshot("mutable-package")

            self.assertFalse(snapshots.exists())


class Phase31CompatibilityMigrationTests(TransactionTestCase):
    migrate_from = ("quiz", "0003_phase3")
    migrate_to = ("quiz", "0004_retire_legacy_ready_runs")
    latest_migration = ("quiz", "0007_phase6_challenge")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        self.old_apps = executor.loader.project_state([self.migrate_from]).apps

    def tearDown(self):
        # This historical migration test deliberately exercises only the 0004
        # transition. Restore the current schema afterward so later test classes
        # run against the models they imported rather than a stale 0004 database.
        MigrationExecutor(connection).migrate([self.latest_migration])
        super().tearDown()

    def _migrate(self):
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        return executor.loader.project_state([self.migrate_to]).apps

    def test_migration_retires_only_active_ready_shell_and_preserves_history(self):
        User = self.old_apps.get_model("auth", "User")
        Run = self.old_apps.get_model("quiz", "Run")
        TeamRun = self.old_apps.get_model("quiz", "TeamRun")
        PuzzleProgress = self.old_apps.get_model("quiz", "PuzzleProgress")
        CommandReceipt = self.old_apps.get_model("quiz", "CommandReceipt")
        AuditEvent = self.old_apps.get_model("quiz", "AuditEvent")
        actor = User.objects.create(username="migration-admin")
        ready = Run.objects.create(
            active=True,
            global_state="READY",
            package_id="legacy",
            snapshot_path="/persistent/snapshots/legacy",
            snapshot_digest="a" * 64,
        )
        archived = Run.objects.create(
            active=False,
            global_state="ADVENT_QUIZ",
            package_id="older",
            snapshot_path="/persistent/snapshots/older",
            snapshot_digest="b" * 64,
        )
        TeamRun.objects.create(
            run=ready,
            team_id="a",
            activity_state="READY",
            points=7,
            hint_tokens=2,
        )
        PuzzleProgress.objects.create(
            run=ready,
            team_id="a",
            puzzle_id="a-1",
            number=1,
        )
        CommandReceipt.objects.create(
            run=archived,
            actor=actor,
            request_id=uuid4(),
            action="reset",
            payload_digest="c" * 64,
            result={"outcome": "reset"},
        )
        AuditEvent.objects.create(
            run=archived,
            actor=actor,
            request_id=uuid4(),
            actor_role="admin",
            action="reset",
            result="reset",
            changes={"new_run_id": str(ready.pk)},
        )

        apps = self._migrate()
        MigratedRun = apps.get_model("quiz", "Run")
        migrated_ready = MigratedRun.objects.get(pk=ready.pk)
        migrated_archived = MigratedRun.objects.get(pk=archived.pk)
        self.assertFalse(migrated_ready.active)
        self.assertFalse(migrated_archived.active)
        self.assertEqual(migrated_ready.snapshot_path, ready.snapshot_path)
        self.assertEqual(
            apps.get_model("quiz", "TeamRun").objects.filter(run_id=ready.pk).count(),
            1,
        )
        self.assertEqual(
            apps.get_model("quiz", "PuzzleProgress")
            .objects.filter(run_id=ready.pk)
            .count(),
            1,
        )
        self.assertEqual(
            apps.get_model("quiz", "CommandReceipt")
            .objects.filter(run_id=archived.pk, action="reset")
            .count(),
            1,
        )
        self.assertEqual(
            apps.get_model("quiz", "AuditEvent")
            .objects.filter(run_id=archived.pk, action="reset")
            .count(),
            1,
        )

        migration = importlib.import_module(
            "quiz.migrations.0004_retire_legacy_ready_runs"
        )
        migration.retire_legacy_ready_runs(apps, None)
        self.assertFalse(MigratedRun.objects.get(pk=ready.pk).active)

    def test_migration_does_not_deactivate_active_gameplay_run(self):
        Run = self.old_apps.get_model("quiz", "Run")
        active = Run.objects.create(
            active=True,
            global_state="ADVENT_QUIZ",
            package_id="live",
            snapshot_path="/persistent/snapshots/live",
            snapshot_digest="d" * 64,
        )
        inactive_ready = Run.objects.create(
            active=False,
            global_state="READY",
            package_id="historical",
            snapshot_path="/persistent/snapshots/historical",
            snapshot_digest="e" * 64,
        )

        apps = self._migrate()
        MigratedRun = apps.get_model("quiz", "Run")
        self.assertTrue(MigratedRun.objects.get(pk=active.pk).active)
        self.assertFalse(MigratedRun.objects.get(pk=inactive_ready.pk).active)
