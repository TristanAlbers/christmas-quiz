"""Focused Phase 6 schema, snapshot, rollback, and restart checks."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from quiz.configuration import InvalidPackage, load_snapshot, stage_snapshot
from quiz.models import (
    AccountRole,
    AuditEvent,
    Challenge,
    ChallengeAttempt,
    CommandReceipt,
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
        "fragment": None,
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


def phase6_config(package_id="phase6"):
    return {
        "schema_version": 6,
        "package_id": package_id,
        "initial_points": 10,
        "hint_cost": 1,
        "skip_cost": 2,
        "freeze_cost": 3,
        "uno_reverse_cost": 4,
        "challenge_cost": 7,
        "music_question_reward": 5,
        "music_score_display_duration_ms": 10_000,
        "teams": {
            team_id: {
                "puzzles": [
                    _puzzle(team_id, number) for number in range(1, 26)
                ]
            }
            for team_id in ("a", "b")
        },
        "music_questions": [_music_question(number) for number in range(1, 12)],
        "challenge_puzzle": {
            "id": "shared-challenge",
            "title": "Christmas Challenge",
            "body": "Solve the shared clue",
            "validator": {"type": "text_exact", "answer": "mistletoe"},
            "media": ["challenge/clue.png"],
        },
    }


def write_package(root, config):
    package = root / config["package_id"]
    (package / "challenge").mkdir(parents=True)
    (package / "challenge" / "clue.png").write_bytes(b"challenge-media")
    (package / "game.json").write_text(json.dumps(config))
    return package


class PhaseSixConfigurationTests(TestCase):
    def test_v6_challenge_data_and_media_are_validated_and_pinned(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            games = root / "games"
            config = phase6_config()
            package = write_package(games, config)
            with override_settings(
                QUIZ_GAMES_ROOT=games,
                QUIZ_SNAPSHOT_ROOT=root / "snapshots",
            ):
                staged = stage_snapshot("phase6")
                config["challenge_cost"] = 99
                (package / "game.json").write_text(json.dumps(config))
                (package / "challenge" / "clue.png").unlink()

                pinned = load_snapshot(staged.path)
                pinned_media = (
                    Path(staged.path) / "media" / "challenge" / "clue.png"
                )

            self.assertEqual(pinned["challenge_cost"], 7)
            self.assertEqual(pinned["challenge_puzzle"]["id"], "shared-challenge")
            self.assertEqual(pinned_media.read_bytes(), b"challenge-media")

    def test_v6_rejects_invalid_cost_question_shape_validator_and_media(self):
        mutations = (
            lambda config: config.update(challenge_cost=-1),
            lambda config: config["challenge_puzzle"].update(reward_points=5),
            lambda config: config["challenge_puzzle"].update(id="not valid"),
            lambda config: config["challenge_puzzle"]["validator"].update(
                type="contains"
            ),
            lambda config: config["challenge_puzzle"].update(
                media=["../private.png"]
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), TemporaryDirectory() as directory:
                root = Path(directory)
                games = root / "games"
                config = phase6_config()
                mutate(config)
                write_package(games, config)
                with (
                    override_settings(
                        QUIZ_GAMES_ROOT=games,
                        QUIZ_SNAPSHOT_ROOT=root / "snapshots",
                    ),
                    self.assertRaises(InvalidPackage),
                ):
                    stage_snapshot("phase6")


class PhaseSixPersistenceTests(TransactionTestCase):
    def setUp(self):
        users = get_user_model()
        self.users = {
            team_id: users.objects.create_user(f"phase6-storage-{team_id}")
            for team_id in ("a", "b")
        }
        for team_id, user in self.users.items():
            AccountRole.objects.create(user=user, role="team", team_id=team_id)
        self.run = Run.objects.create(
            global_state="ADVENT_QUIZ",
            package_id="phase6",
            snapshot_path="/tmp/pinned",
            snapshot_digest="a" * 64,
        )
        self.teams = {
            team_id: TeamRun.objects.create(
                run=self.run,
                team_id=team_id,
                activity_state="PUZZLE",
                points=10,
            )
            for team_id in ("a", "b")
        }

    def _challenge(self, **changes):
        values = {
            "run": self.run,
            "initiator_team_id": "a",
            "challenged_team_id": "b",
            "question_id": "shared-challenge",
            "paid_cost": 7,
        }
        values.update(changes)
        return Challenge.objects.create(**values)

    def test_schema_guards_active_pair_cost_request_and_first_correct_attempt(self):
        challenge = self._challenge()
        invalid_writes = (
            lambda: self._challenge(
                initiator_team_id="b", challenged_team_id="a"
            ),
            lambda: Challenge.objects.create(
                run=Run.objects.create(
                    active=False,
                    global_state="ADVENT_QUIZ",
                    package_id="invalid-pair",
                    snapshot_path="/tmp/invalid",
                    snapshot_digest="b" * 64,
                ),
                initiator_team_id="a",
                challenged_team_id="a",
                question_id="shared-challenge",
                paid_cost=7,
            ),
        )
        for write in invalid_writes:
            with self.subTest(write=write), self.assertRaises(IntegrityError):
                with immediate_transaction():
                    write()

        request_id = uuid4()
        winning = ChallengeAttempt.objects.create(
            challenge=challenge,
            actor=self.users["a"],
            team_id="a",
            request_id=request_id,
            question_id="shared-challenge",
            is_correct=True,
        )
        duplicate_writes = (
            lambda: ChallengeAttempt.objects.create(
                challenge=challenge,
                actor=self.users["b"],
                team_id="b",
                request_id=uuid4(),
                question_id="shared-challenge",
                is_correct=True,
            ),
            lambda: ChallengeAttempt.objects.create(
                challenge=challenge,
                actor=self.users["a"],
                team_id="a",
                request_id=request_id,
                question_id="shared-challenge",
                is_correct=False,
            ),
        )
        for write in duplicate_writes:
            with self.subTest(write=write), self.assertRaises(IntegrityError):
                with immediate_transaction():
                    write()

        challenge.status = "resolved"
        challenge.winner_team_id = "a"
        challenge.freeze_applied = True
        challenge.winning_attempt = winning
        challenge.resolved_at = timezone.now()
        challenge.save(
            update_fields=[
                "status",
                "winner_team_id",
                "freeze_applied",
                "winning_attempt",
                "resolved_at",
            ]
        )
        with self.assertRaisesRegex(ValueError, "cannot be deleted"):
            challenge.delete()
        with self.assertRaisesRegex(ValueError, "immutable"):
            winning.save()

    def test_result_pairing_rejects_wrong_freeze_semantics(self):
        challenge = self._challenge()
        attempt = ChallengeAttempt.objects.create(
            challenge=challenge,
            actor=self.users["b"],
            team_id="b",
            request_id=uuid4(),
            question_id="shared-challenge",
            is_correct=True,
        )
        with self.assertRaises(IntegrityError):
            with immediate_transaction():
                Challenge.objects.filter(pk=challenge.pk).update(
                    status="resolved",
                    winner_team_id="b",
                    freeze_applied=True,
                    winning_attempt=attempt,
                    resolved_at=timezone.now(),
                )

    def test_initiation_facts_roll_back_together(self):
        request_id = uuid4()
        with self.assertRaisesRegex(RuntimeError, "force rollback"):
            with immediate_transaction():
                for team in self.teams.values():
                    team.activity_state = "CHALLENGE"
                    fields = ["activity_state"]
                    if team.team_id == "a":
                        team.points -= 7
                        team.challenge_available = False
                        fields.extend(["points", "challenge_available"])
                    team.save(update_fields=fields)
                self._challenge()
                CommandReceipt.objects.create(
                    run=self.run,
                    actor=self.users["a"],
                    request_id=request_id,
                    action="initiate_challenge",
                    payload_digest="c" * 64,
                    result={"outcome": "challenge_started"},
                )
                AuditEvent.objects.create(
                    run=self.run,
                    actor=self.users["a"],
                    request_id=request_id,
                    actor_role="team",
                    team_id="a",
                    action="initiate_challenge",
                    result="challenge_started",
                )
                raise RuntimeError("force rollback")

        for team_id, team in self.teams.items():
            team.refresh_from_db()
            self.assertEqual(team.activity_state, "PUZZLE")
            self.assertEqual(team.points, 10)
            self.assertTrue(team.challenge_available, team_id)
        self.assertFalse(Challenge.objects.exists())
        self.assertFalse(CommandReceipt.objects.exists())
        self.assertFalse(AuditEvent.objects.exists())

    def test_active_context_payment_and_receipt_survive_restart(self):
        request_id = uuid4()
        initiator = self.teams["a"]
        challenged = self.teams["b"]
        with immediate_transaction():
            initiator.points = 3
            initiator.challenge_available = False
            initiator.activity_state = "CHALLENGE"
            initiator.save(
                update_fields=["points", "challenge_available", "activity_state"]
            )
            challenged.activity_state = "CHALLENGE"
            challenged.save(update_fields=["activity_state"])
            challenge = self._challenge()
            CommandReceipt.objects.create(
                run=self.run,
                actor=self.users["a"],
                request_id=request_id,
                action="initiate_challenge",
                payload_digest="d" * 64,
                result={
                    "outcome": "challenge_started",
                    "challenge_id": str(challenge.pk),
                },
            )

        connections.close_all()

        recovered = Challenge.objects.get(pk=challenge.pk)
        recovered_initiator = TeamRun.objects.get(run=self.run, team_id="a")
        self.assertEqual(recovered.status, "active")
        self.assertEqual(recovered.paid_cost, 7)
        self.assertEqual(recovered_initiator.points, 3)
        self.assertFalse(recovered_initiator.challenge_available)
        self.assertEqual(recovered_initiator.activity_state, "CHALLENGE")
        self.assertTrue(
            CommandReceipt.objects.filter(
                actor=self.users["a"], request_id=request_id
            ).exists()
        )


class PhaseSixMigrationTests(TransactionTestCase):
    migrate_from = ("quiz", "0006_phase5_finish")
    migrate_to = ("quiz", "0007_phase6_challenge")

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        OldRun = old_apps.get_model("quiz", "Run")
        OldTeamRun = old_apps.get_model("quiz", "TeamRun")
        run = OldRun.objects.create(
            active=True,
            global_state="ADVENT_QUIZ",
            package_id="phase5-existing",
            snapshot_path="/persistent/phase5",
            snapshot_digest="e" * 64,
        )
        self.run_id = run.pk
        OldTeamRun.objects.bulk_create(
            [
                OldTeamRun(run=run, team_id=team_id, activity_state="PUZZLE")
                for team_id in ("a", "b")
            ]
        )
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_existing_teams_gain_one_available_opportunity_and_empty_history(self):
        MigratedTeamRun = self.apps.get_model("quiz", "TeamRun")
        MigratedChallenge = self.apps.get_model("quiz", "Challenge")
        self.assertEqual(
            list(
                MigratedTeamRun.objects.filter(run_id=self.run_id)
                .order_by("team_id")
                .values_list("challenge_available", flat=True)
            ),
            [True, True],
        )
        self.assertFalse(MigratedChallenge.objects.filter(run_id=self.run_id).exists())
