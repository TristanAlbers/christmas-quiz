"""Focused phase-3 persistence, configuration, and media checks."""

import json
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse

from quiz.configuration import InvalidPackage, load_snapshot, stage_snapshot
from quiz.models import AccountRole, Run, TeamRun
from quiz.persistence import immediate_transaction


def _puzzle(team_id, number, media=None):
    return {
        "id": f"{team_id}-{number}",
        "number": number,
        "title": f"Puzzle {number}",
        "body": "Clue",
        "validator": {"type": "text_exact", "answer": "secret"},
        "reward_points": 0,
        "hint": "private hint",
        "fragment": None,
        "media": media or [],
    }


def _package_config(package_id, version=3):
    config = {
        "schema_version": version,
        "package_id": package_id,
        "initial_points": 10,
        "teams": {
            "a": {
                "puzzles": [
                    _puzzle("a", 1, ["a/private.txt"]),
                    _puzzle("a", 2),
                ]
            },
            "b": {"puzzles": [_puzzle("b", 1), _puzzle("b", 2)]},
        },
    }
    if version >= 2:
        config.update(hint_cost=2, skip_cost=3)
    if version >= 3:
        config.update(freeze_cost=4, uno_reverse_cost=5)
    return config


def _write_package(root, package_id, version=3):
    package = root / package_id
    (package / "a").mkdir(parents=True)
    (package / "a" / "private.txt").write_bytes(b"private media")
    config = _package_config(package_id, version)
    (package / "game.json").write_text(json.dumps(config))
    return package, config


class PhaseThreeStorageTests(TestCase):
    def setUp(self):
        self.run = Run.objects.create(
            global_state="READY",
            package_id="demo",
            snapshot_path="/tmp/unused",
            snapshot_digest="a" * 64,
        )

    def test_gameplay_clock_accumulator_cannot_be_negative(self):
        with self.assertRaises(IntegrityError):
            with immediate_transaction():
                Run.objects.filter(pk=self.run.pk).update(gameplay_elapsed_ms=-1)

    def test_freeze_state_and_clock_start_are_paired_and_nonnegative(self):
        valid = TeamRun.objects.create(
            run=self.run,
            team_id="a",
            activity_state="FREEZE",
            freeze_started_gameplay_ms=0,
            reverse_active=True,
        )
        valid.refresh_from_db()
        self.assertEqual(valid.freeze_started_gameplay_ms, 0)
        self.assertTrue(valid.reverse_active)

        invalid_rows = (
            {"team_id": "b", "activity_state": "FREEZE"},
            {
                "team_id": "b",
                "activity_state": "PUZZLE",
                "freeze_started_gameplay_ms": 0,
            },
            {
                "team_id": "b",
                "activity_state": "FREEZE",
                "freeze_started_gameplay_ms": -1,
            },
        )
        for fields in invalid_rows:
            with self.subTest(fields=fields), self.assertRaises(IntegrityError):
                with immediate_transaction():
                    TeamRun.objects.create(run=self.run, **fields)


class PhaseThreeMigrationTests(TransactionTestCase):
    migrate_from = ("quiz", "0002_phase2")
    migrate_to = ("quiz", "0003_phase3")
    latest_migration = ("quiz", "0008_issue44_music_gathering")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        OldRun = old_apps.get_model("quiz", "Run")
        self.active_run_id = OldRun.objects.create(
            active=True,
            global_state="ADVENT_QUIZ",
            package_id="demo",
            snapshot_path="/tmp/unused",
            snapshot_digest="a" * 64,
        ).pk
        self.paused_run_id = OldRun.objects.create(
            active=False,
            global_state="PAUSED",
            package_id="demo",
            snapshot_path="/tmp/unused",
            snapshot_digest="b" * 64,
        ).pk
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        # This historical test intentionally stops at phase 3 while asserting
        # migration 0003. Restore today's schema afterward so later tests using
        # current ORM models do not inherit a stale database schema.
        MigrationExecutor(connection).migrate([self.latest_migration])
        super().tearDown()

    def test_migration_bootstraps_only_the_active_advent_clock(self):
        MigratedRun = self.apps.get_model("quiz", "Run")
        active = MigratedRun.objects.get(pk=self.active_run_id)
        paused = MigratedRun.objects.get(pk=self.paused_run_id)
        self.assertEqual(active.gameplay_elapsed_ms, 0)
        self.assertIsNotNone(active.advent_clock_anchor)
        self.assertEqual(paused.gameplay_elapsed_ms, 0)
        self.assertIsNone(paused.advent_clock_anchor)


class PhaseThreeConfigurationTests(TestCase):
    def test_v3_costs_are_pinned_and_must_be_nonnegative_integers(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            games = root / "games"
            package, config = _write_package(games, "phase3")
            game_file = package / "game.json"
            with override_settings(
                QUIZ_GAMES_ROOT=games, QUIZ_SNAPSHOT_ROOT=root / "snapshots"
            ):
                staged = stage_snapshot("phase3")
                config["freeze_cost"] = 99
                config["uno_reverse_cost"] = 98
                game_file.write_text(json.dumps(config))
                pinned = load_snapshot(staged.path)
                self.assertEqual(pinned["freeze_cost"], 4)
                self.assertEqual(pinned["uno_reverse_cost"], 5)

                for key, value in (
                    ("freeze_cost", -1),
                    ("freeze_cost", True),
                    ("uno_reverse_cost", -1),
                    ("uno_reverse_cost", False),
                ):
                    invalid = _package_config("phase3")
                    invalid[key] = value
                    game_file.write_text(json.dumps(invalid))
                    with self.subTest(key=key, value=value):
                        with self.assertRaises(InvalidPackage):
                            stage_snapshot("phase3")

                missing = _package_config("phase3")
                del missing["uno_reverse_cost"]
                game_file.write_text(json.dumps(missing))
                with self.assertRaises(InvalidPackage):
                    stage_snapshot("phase3")

    def test_v1_and_v2_snapshots_remain_readable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            games = root / "games"
            for version in (1, 2):
                _write_package(games, f"legacy-{version}", version)
            with override_settings(
                QUIZ_GAMES_ROOT=games, QUIZ_SNAPSHOT_ROOT=root / "snapshots"
            ):
                for version in (1, 2):
                    with self.subTest(version=version):
                        staged = stage_snapshot(f"legacy-{version}")
                        self.assertEqual(
                            load_snapshot(staged.path)["schema_version"], version
                        )


class PhaseThreePrivateMediaTests(TestCase):
    def setUp(self):
        self.runtime = tempfile.TemporaryDirectory()
        self.addCleanup(self.runtime.cleanup)
        root = Path(self.runtime.name)
        games = root / "games"
        _write_package(games, "phase3-media")
        scope = override_settings(
            QUIZ_GAMES_ROOT=games, QUIZ_SNAPSHOT_ROOT=root / "snapshots"
        )
        scope.enable()
        self.addCleanup(scope.disable)
        staged = stage_snapshot("phase3-media")
        self.anchor = datetime(2026, 12, 1, 18, 0, tzinfo=UTC)
        self.run = Run.objects.create(
            global_state="ADVENT_QUIZ",
            package_id="phase3-media",
            snapshot_path=staged.path,
            snapshot_digest=staged.digest,
            gameplay_elapsed_ms=1_000,
            advent_clock_anchor=self.anchor,
        )
        self.team_run = TeamRun.objects.create(
            run=self.run,
            team_id="a",
            activity_state="PUZZLE",
        )
        user = get_user_model().objects.create_user("media-a", password="pin")
        AccountRole.objects.create(user=user, role="team", team_id="a")
        self.client.force_login(user)
        self.url = reverse(
            "private_media",
            kwargs={
                "run_id": self.run.pk,
                "team_id": "a",
                "asset_path": "a/private.txt",
            },
        )

    def test_active_freeze_denies_media_but_logically_expired_freeze_permits_it(self):
        initial = self.client.get(self.url)
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(b"".join(initial.streaming_content), b"private media")

        TeamRun.objects.filter(pk=self.team_run.pk).update(
            activity_state="FREEZE", freeze_started_gameplay_ms=1_000
        )

        with patch("quiz.web.media_views.server_now", return_value=self.anchor):
            self.assertEqual(self.client.get(self.url).status_code, 404)

        expired_at = self.anchor + timedelta(milliseconds=300_000)
        with patch("quiz.web.media_views.server_now", return_value=expired_at):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"private media")

        self.team_run.refresh_from_db()
        self.assertEqual(self.team_run.activity_state, "FREEZE")
        self.assertEqual(self.team_run.freeze_started_gameplay_ms, 1_000)

    def test_pause_denies_media_without_advancing_the_stopped_clock(self):
        Run.objects.filter(pk=self.run.pk).update(
            global_state="PAUSED", advent_clock_anchor=None
        )
        TeamRun.objects.filter(pk=self.team_run.pk).update(
            activity_state="FREEZE", freeze_started_gameplay_ms=1_000
        )
        much_later = self.anchor + timedelta(days=30)
        with patch("quiz.web.media_views.server_now", return_value=much_later):
            self.assertEqual(self.client.get(self.url).status_code, 404)
