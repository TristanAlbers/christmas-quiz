"""Focused phase-4 schema, snapshot, rollback, and restart checks."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from quiz.configuration import (
    InvalidPackage,
    load_snapshot,
    snapshot_music_audio_path,
    stage_snapshot,
)
from quiz.models import (
    AccountRole,
    CommandReceipt,
    MusicAttempt,
    MusicQuestionResult,
    MusicQuiz,
    MusicScore,
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
        "reward_points": 0,
        "hint": None,
        "fragment": None,
        "media": [],
    }


def _music_question(number, audio=None):
    question = {
        "id": f"music-{number}",
        "number": number,
        "title": f"Song {number}",
        "body": "Name it",
        "validator": {"type": "text_exact", "answer": f"answer-{number}"},
    }
    if audio is not None:
        question["audio"] = audio
    return question


def _config(package_id="phase4"):
    return {
        "schema_version": 4,
        "package_id": package_id,
        "initial_points": 10,
        "hint_cost": 1,
        "skip_cost": 2,
        "freeze_cost": 3,
        "uno_reverse_cost": 4,
        "music_question_reward": 5,
        "music_score_display_duration_ms": 10_000,
        "teams": {
            "a": {"puzzles": [_puzzle("a", 1), _puzzle("a", 2)]},
            "b": {"puzzles": [_puzzle("b", 1), _puzzle("b", 2)]},
        },
        "music_questions": [
            _music_question(number, "music/current.mp3" if number == 1 else None)
            for number in range(1, 12)
        ],
    }


def _write_package(games, config):
    package = games / config["package_id"]
    (package / "music").mkdir(parents=True)
    (package / "music" / "current.mp3").write_bytes(b"pinned-current-audio")
    (package / "game.json").write_text(json.dumps(config))
    return package


class PhaseFourSchemaTests(TransactionTestCase):
    def setUp(self):
        users = get_user_model()
        self.user = users.objects.create_user("phase4-storage-a")
        AccountRole.objects.create(user=self.user, role="team", team_id="a")
        self.run = Run.objects.create(
            global_state="MUSIC_QUIZ",
            package_id="phase4",
            snapshot_path="/tmp/unused",
            snapshot_digest="a" * 64,
        )
        TeamRun.objects.create(
            run=self.run, team_id="a", activity_state="PUZZLE", points=10
        )
        TeamRun.objects.create(
            run=self.run, team_id="b", activity_state="PUZZLE", points=10
        )

    def test_music_schema_defends_trigger_score_phase_and_winner_uniqueness(self):
        MusicQuiz.objects.create(
            run=self.run,
            phase="question",
            current_question_number=1,
            music_clock_anchor=timezone.now(),
        )
        self.assertEqual(self.run.music_quiz.current_question_started_ms, 0)
        MusicScore.objects.create(run=self.run, team_id="a")
        MusicScore.objects.create(run=self.run, team_id="b")
        attempt = MusicAttempt.objects.create(
            run=self.run,
            team_id="a",
            actor=self.user,
            request_id=uuid4(),
            question_number=1,
            question_id="music-1",
            is_correct=True,
        )
        MusicQuestionResult.objects.create(
            run=self.run,
            question_number=1,
            question_id="music-1",
            winner_team_id="a",
            reward_points=5,
            winning_attempt=attempt,
        )

        invalid_writes = (
            lambda: MusicQuiz.objects.create(
                run=self.run, phase="question", current_question_number=1
            ),
            lambda: MusicScore.objects.create(run=self.run, team_id="a"),
            lambda: MusicScore.objects.filter(run=self.run, team_id="a").update(
                score=12
            ),
            lambda: MusicQuestionResult.objects.create(
                run=self.run,
                question_number=1,
                question_id="other-id",
                winner_team_id="b",
                reward_points=5,
                winning_attempt=MusicAttempt.objects.create(
                    run=self.run,
                    team_id="b",
                    actor=self.user,
                    request_id=uuid4(),
                    question_number=1,
                    question_id="other-id",
                    is_correct=True,
                ),
            ),
        )
        for write in invalid_writes:
            with self.subTest(write=write), self.assertRaises(IntegrityError):
                with immediate_transaction():
                    write()

    def test_pause_target_pairing_and_music_phase_consistency_are_constrained(self):
        invalid = (
            lambda: Run.objects.filter(pk=self.run.pk).update(
                pause_resume_target="MUSIC_QUIZ"
            ),
            lambda: MusicQuiz.objects.create(
                run=self.run,
                phase="question",
                current_question_number=None,
            ),
            lambda: MusicQuiz.objects.create(
                run=self.run,
                phase="final_results",
                final_results_started_ms=-1,
                current_question_started_ms=None,
            ),
            lambda: MusicQuiz.objects.create(
                run=self.run,
                phase="question",
                current_question_number=1,
                current_question_started_ms=-1,
            ),
        )
        for write in invalid:
            with self.subTest(write=write), self.assertRaises(IntegrityError):
                with immediate_transaction():
                    write()

        self.run.global_state = "PAUSED"
        self.run.pause_resume_target = "MUSIC_QUIZ"
        self.run.save(update_fields=["global_state", "pause_resume_target"])

    def test_failed_completion_and_music_trigger_roll_back_together(self):
        self.run.global_state = "ADVENT_QUIZ"
        self.run.advent_clock_anchor = timezone.now()
        self.run.save(update_fields=["global_state", "advent_clock_anchor"])
        progress = PuzzleProgress.objects.create(
            run=self.run,
            team_id="a",
            puzzle_id="a-13",
            number=13,
        )
        with self.assertRaises(RuntimeError):
            with immediate_transaction():
                progress.completed = True
                progress.save(update_fields=["completed"])
                MusicQuiz.objects.create(
                    run=self.run,
                    phase="question",
                    current_question_number=1,
                    music_clock_anchor=timezone.now(),
                )
                MusicScore.objects.create(run=self.run, team_id="a")
                MusicScore.objects.create(run=self.run, team_id="b")
                raise RuntimeError("force rollback")
        progress.refresh_from_db()
        self.assertFalse(progress.completed)
        self.assertFalse(MusicQuiz.objects.filter(run=self.run).exists())
        self.assertEqual(MusicScore.objects.filter(run=self.run).count(), 0)

    def test_music_facts_and_receipt_survive_connection_reopen(self):
        music = MusicQuiz.objects.create(
            run=self.run,
            phase="question",
            current_question_number=4,
            current_question_started_ms=1000,
            music_elapsed_ms=1234,
            music_clock_anchor=timezone.now(),
            previous_winner_team="b",
        )
        MusicScore.objects.bulk_create(
            [
                MusicScore(run=self.run, team_id="a", score=1),
                MusicScore(run=self.run, team_id="b", score=2),
            ]
        )
        request_id = uuid4()
        attempt = MusicAttempt.objects.create(
            run=self.run,
            team_id="b",
            actor=self.user,
            request_id=request_id,
            question_number=3,
            question_id="music-3",
            is_correct=True,
        )
        MusicQuestionResult.objects.create(
            run=self.run,
            question_number=3,
            question_id="music-3",
            winner_team_id="b",
            reward_points=5,
            winning_attempt=attempt,
        )
        CommandReceipt.objects.create(
            run=self.run,
            actor=self.user,
            request_id=request_id,
            action="submit_music_answer",
            payload_digest="d" * 64,
            result={"outcome": "won", "question_id": "music-3"},
        )

        connections.close_all()

        recovered = MusicQuiz.objects.get(run_id=self.run.pk)
        self.assertEqual(
            (
                recovered.phase,
                recovered.current_question_number,
                recovered.current_question_started_ms,
                recovered.music_elapsed_ms,
                recovered.previous_winner_team,
            ),
            ("question", 4, 1000, 1234, "b"),
        )
        self.assertEqual(
            list(
                MusicScore.objects.filter(run_id=self.run.pk)
                .order_by("team_id")
                .values_list("score", flat=True)
            ),
            [1, 2],
        )
        self.assertTrue(
            CommandReceipt.objects.filter(
                actor=self.user, request_id=request_id
            ).exists()
        )
        self.assertEqual(MusicQuestionResult.objects.filter(run=self.run).count(), 1)
        self.assertIsNotNone(music.music_clock_anchor)

    def test_existing_receipt_supports_exact_retry_and_rejects_conflicting_reuse(self):
        request_id = uuid4()
        committed = CommandReceipt.objects.create(
            run=self.run,
            actor=self.user,
            request_id=request_id,
            action="submit_music_answer",
            payload_digest="a" * 64,
            result={"outcome": "incorrect", "question_id": "music-1"},
        )
        retry = CommandReceipt.objects.get(actor=self.user, request_id=request_id)
        self.assertEqual(retry.payload_digest, committed.payload_digest)
        self.assertEqual(retry.result, committed.result)
        with self.assertRaises(IntegrityError):
            with immediate_transaction():
                CommandReceipt.objects.create(
                    run=self.run,
                    actor=self.user,
                    request_id=request_id,
                    action="submit_music_answer",
                    payload_digest="b" * 64,
                    result={"outcome": "won", "question_id": "music-2"},
                )


class PhaseFourConfigurationTests(TestCase):
    def test_v4_music_data_and_audio_are_validated_and_pinned(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            games = root / "games"
            config = _config()
            package = _write_package(games, config)
            with override_settings(
                QUIZ_GAMES_ROOT=games, QUIZ_SNAPSHOT_ROOT=root / "snapshots"
            ):
                staged = stage_snapshot("phase4")
                (package / "music" / "current.mp3").write_bytes(b"source-mutated")
                config["music_question_reward"] = 99
                (package / "game.json").write_text(json.dumps(config))
                pinned = load_snapshot(staged.path)
                self.assertEqual(pinned["music_question_reward"], 5)
                run = Run(
                    snapshot_path=staged.path,
                    snapshot_digest=staged.digest,
                )
                self.assertEqual(
                    snapshot_music_audio_path(run, 1).read_bytes(),
                    b"pinned-current-audio",
                )
                self.assertIsNone(snapshot_music_audio_path(run, 2))

    def test_v4_rejects_bad_counts_values_ids_and_audio(self):
        mutations = (
            lambda config: config.update(music_question_reward=-1),
            lambda config: config.update(music_score_display_duration_ms=0),
            lambda config: config["music_questions"].pop(),
            lambda config: config["music_questions"][1].update(id="music-1"),
            lambda config: config["music_questions"][0].update(audio="../future.mp3"),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), TemporaryDirectory() as directory:
                root = Path(directory)
                games = root / "games"
                config = _config()
                mutate(config)
                _write_package(games, config)
                with (
                    override_settings(
                        QUIZ_GAMES_ROOT=games,
                        QUIZ_SNAPSHOT_ROOT=root / "snapshots",
                    ),
                    self.assertRaises(InvalidPackage),
                ):
                    stage_snapshot("phase4")


class PhaseFourMigrationTests(TransactionTestCase):
    migrate_from = ("quiz", "0004_retire_legacy_ready_runs")
    migrate_to = ("quiz", "0005_phase4_music")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        OldRun = old_apps.get_model("quiz", "Run")
        self.active_paused_id = OldRun.objects.create(
            active=True,
            global_state="PAUSED",
            package_id="old-active",
            snapshot_path="/persistent/active",
            snapshot_digest="a" * 64,
        ).pk
        self.historical_paused_id = OldRun.objects.create(
            active=False,
            global_state="PAUSED",
            package_id="old-history",
            snapshot_path="/persistent/history",
            snapshot_digest="b" * 64,
        ).pk
        self.advent_id = OldRun.objects.create(
            active=False,
            global_state="ADVENT_QUIZ",
            package_id="old-advent",
            snapshot_path="/persistent/advent",
            snapshot_digest="c" * 64,
        ).pk
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_all_existing_pauses_resume_advent_and_other_states_have_no_target(self):
        MigratedRun = self.apps.get_model("quiz", "Run")
        self.assertEqual(
            MigratedRun.objects.get(pk=self.active_paused_id).pause_resume_target,
            "ADVENT_QUIZ",
        )
        self.assertEqual(
            MigratedRun.objects.get(pk=self.historical_paused_id).pause_resume_target,
            "ADVENT_QUIZ",
        )
        self.assertIsNone(
            MigratedRun.objects.get(pk=self.advent_id).pause_resume_target
        )
