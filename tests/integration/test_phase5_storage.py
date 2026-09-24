"""Focused Phase 5 schema, package, rollback, and recovery checks."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings

from quiz.configuration import (
    InvalidPackage,
    load_snapshot,
    snapshot_music_audio_path,
    stage_snapshot,
)
from quiz.models import (
    AccountRole,
    AuditEvent,
    CommandReceipt,
    FirstFinisher,
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
        "fragment": f"fragment-{number}" if number % 5 == 0 else None,
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


def _config(package_id="phase5", *, version=5, puzzle_count=25):
    return {
        "schema_version": version,
        "package_id": package_id,
        "initial_points": 10,
        "hint_cost": 1,
        "skip_cost": 2,
        "freeze_cost": 3,
        "uno_reverse_cost": 4,
        "music_question_reward": 5,
        "music_score_display_duration_ms": 10_000,
        "teams": {
            team_id: {
                "puzzles": [
                    _puzzle(team_id, number)
                    for number in range(1, puzzle_count + 1)
                ]
            }
            for team_id in ("a", "b")
        },
        "music_questions": [_music_question(number) for number in range(1, 12)],
    }


def _write_package(root, config):
    package = root / config["package_id"]
    package.mkdir(parents=True)
    (package / "game.json").write_text(json.dumps(config))
    return package


class PhaseFiveConfigurationTests(TestCase):
    def test_v5_requires_and_pins_exactly_twenty_five_puzzles_per_team(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            games = root / "games"
            config = _config()
            config["music_questions"][0]["audio"] = "music/first.mp3"
            package = _write_package(games, config)
            (package / "music").mkdir()
            (package / "music" / "first.mp3").write_bytes(b"phase5-audio")
            with override_settings(
                QUIZ_GAMES_ROOT=games,
                QUIZ_SNAPSHOT_ROOT=root / "snapshots",
            ):
                staged = stage_snapshot("phase5")
                config["teams"]["a"]["puzzles"].pop()
                (package / "game.json").write_text(json.dumps(config))

                pinned = load_snapshot(staged.path)
                run = Run(snapshot_path=staged.path, snapshot_digest=staged.digest)
                audio_bytes = snapshot_music_audio_path(run, 1).read_bytes()

            self.assertEqual(pinned["schema_version"], 5)
            self.assertEqual(len(pinned["teams"]["a"]["puzzles"]), 25)
            self.assertEqual(len(pinned["teams"]["b"]["puzzles"]), 25)
            self.assertEqual(audio_bytes, b"phase5-audio")

    def test_v5_rejects_a_short_team_but_v4_snapshots_remain_readable(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            games = root / "games"
            _write_package(games, _config("short-v5", puzzle_count=24))
            _write_package(games, _config("legacy-v4", version=4, puzzle_count=2))
            with override_settings(
                QUIZ_GAMES_ROOT=games,
                QUIZ_SNAPSHOT_ROOT=root / "snapshots",
            ):
                with self.assertRaisesRegex(
                    InvalidPackage,
                    "Schema v5 requires exactly 25 puzzles per team",
                ):
                    stage_snapshot("short-v5")
                legacy = stage_snapshot("legacy-v4")
                self.assertEqual(load_snapshot(legacy.path)["schema_version"], 4)


class PhaseFivePersistenceTests(TransactionTestCase):
    def setUp(self):
        users = get_user_model()
        self.user = users.objects.create_user("phase5-storage-a")
        AccountRole.objects.create(user=self.user, role="team", team_id="a")
        self.run = Run.objects.create(
            global_state="ADVENT_QUIZ",
            package_id="phase5",
            snapshot_path="/tmp/pinned",
            snapshot_digest="a" * 64,
        )
        self.team = TeamRun.objects.create(
            run=self.run,
            team_id="a",
            activity_state="PUZZLE",
            current_number=25,
        )
        self.progress = PuzzleProgress.objects.create(
            run=self.run,
            team_id="a",
            puzzle_id="a-25",
            number=25,
        )

    def test_first_finisher_is_unique_valid_immutable_and_archival_safe(self):
        claim = FirstFinisher.objects.create(run=self.run, team_id="a")
        with self.assertRaises(IntegrityError):
            with immediate_transaction():
                FirstFinisher.objects.create(run=self.run, team_id="b")
        with self.assertRaises(IntegrityError):
            with immediate_transaction():
                other = Run.objects.create(
                    active=False,
                    global_state="ADVENT_QUIZ",
                    package_id="phase5-other",
                    snapshot_path="/tmp/other",
                    snapshot_digest="b" * 64,
                )
                FirstFinisher.objects.create(run=other, team_id="x")

        claim.team_id = "b"
        with self.assertRaisesRegex(ValueError, "immutable"):
            claim.save()
        with self.assertRaisesRegex(ValueError, "cannot be deleted"):
            claim.delete()

        self.run.active = False
        self.run.save(update_fields=["active"])
        connections.close_all()
        recovered = FirstFinisher.objects.get(run_id=self.run.pk)
        self.assertEqual(recovered.team_id, "a")
        self.assertIsNotNone(recovered.finished_at)
        self.assertFalse(recovered.run.active)

    def test_finish_facts_roll_back_as_one_unit(self):
        request_id = uuid4()
        with self.assertRaisesRegex(RuntimeError, "force rollback"):
            with immediate_transaction():
                self.team.activity_state = "FINISHED"
                self.team.save(update_fields=["activity_state"])
                self.progress.completed = True
                self.progress.reward_awarded = True
                self.progress.save(update_fields=["completed", "reward_awarded"])
                FirstFinisher.objects.create(run=self.run, team_id="a")
                CommandReceipt.objects.create(
                    run=self.run,
                    actor=self.user,
                    request_id=request_id,
                    action="submit_answer",
                    payload_digest="c" * 64,
                    result={"outcome": "completed", "puzzle_id": "a-25"},
                )
                AuditEvent.objects.create(
                    run=self.run,
                    actor=self.user,
                    request_id=request_id,
                    actor_role="team",
                    team_id="a",
                    action="first_finisher",
                    result="recorded",
                    puzzle_id="a-25",
                )
                raise RuntimeError("force rollback")

        self.team.refresh_from_db()
        self.progress.refresh_from_db()
        self.assertEqual(self.team.activity_state, "PUZZLE")
        self.assertFalse(self.progress.completed)
        self.assertFalse(self.progress.reward_awarded)
        self.assertFalse(FirstFinisher.objects.filter(run=self.run).exists())
        self.assertFalse(CommandReceipt.objects.filter(run=self.run).exists())
        self.assertFalse(AuditEvent.objects.filter(run=self.run).exists())


class PhaseFiveMigrationTests(TransactionTestCase):
    migrate_from = ("quiz", "0005_phase4_music")
    migrate_to = ("quiz", "0006_phase5_finish")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        OldRun = old_apps.get_model("quiz", "Run")
        self.run_id = OldRun.objects.create(
            active=True,
            global_state="ADVENT_QUIZ",
            package_id="phase4-existing",
            snapshot_path="/persistent/phase4",
            snapshot_digest="d" * 64,
        ).pk
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_migration_preserves_existing_run_and_adds_claim_storage(self):
        MigratedRun = self.apps.get_model("quiz", "Run")
        MigratedFirstFinisher = self.apps.get_model("quiz", "FirstFinisher")
        run = MigratedRun.objects.get(pk=self.run_id)
        self.assertEqual(run.package_id, "phase4-existing")
        self.assertFalse(MigratedFirstFinisher.objects.filter(run=run).exists())

        claim = MigratedFirstFinisher.objects.create(run=run, team_id="b")
        self.assertEqual(claim.team_id, "b")
