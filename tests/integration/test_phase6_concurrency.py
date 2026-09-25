"""Separate-connection Phase 6 initiation and first-correct-answer races."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from datetime import timezone as datetime_timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from quiz.application import (
    initiate_challenge,
    start_game,
    submit_challenge_answer,
)
from quiz.contracts import (
    Actor,
    ApplicationError,
    RunCommand,
    StartGame,
    SubmitChallengeAnswer,
)
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

NOW = datetime(2026, 12, 24, 18, 0, tzinfo=datetime_timezone.utc)


class PhaseSixRaceTests(TransactionTestCase):
    def setUp(self):
        if (
            not os.environ.get("TEST_DATABASE_PATH")
            or os.environ["TEST_DATABASE_PATH"] == ":memory:"
        ):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        users = get_user_model()
        self.users = {
            team_id: users.objects.create_user(f"phase6-race-{team_id}")
            for team_id in ("a", "b")
        }
        for team_id, user in self.users.items():
            AccountRole.objects.create(user=user, role="team", team_id=team_id)
        self.run = Run.objects.create(
            global_state="ADVENT_QUIZ",
            package_id="phase6",
            snapshot_path="/tmp/pinned",
            snapshot_digest="f" * 64,
        )
        TeamRun.objects.bulk_create(
            [
                TeamRun(
                    run=self.run,
                    team_id=team_id,
                    activity_state="PUZZLE",
                    points=10,
                )
                for team_id in ("a", "b")
            ]
        )

    def _start(self, team_id, request_id):
        actor = self.users[team_id]
        digest = team_id * 64
        with immediate_transaction():
            prior = CommandReceipt.objects.filter(
                actor=actor, request_id=request_id
            ).first()
            if prior is not None:
                return prior.result["outcome"]
            run = Run.objects.get(pk=self.run.pk)
            if Challenge.objects.filter(run=run, status="active").exists():
                return "challenge_unavailable"
            teams = {
                row.team_id: row
                for row in TeamRun.objects.filter(run=run).order_by("team_id")
            }
            initiator = teams[team_id]
            challenged = teams["b" if team_id == "a" else "a"]
            if (
                initiator.activity_state != "PUZZLE"
                or challenged.activity_state != "PUZZLE"
                or not initiator.challenge_available
                or initiator.points < 7
            ):
                return "challenge_unavailable"
            initiator.points -= 7
            initiator.challenge_available = False
            initiator.activity_state = "CHALLENGE"
            initiator.save(
                update_fields=["points", "challenge_available", "activity_state"]
            )
            challenged.activity_state = "CHALLENGE"
            challenged.save(update_fields=["activity_state"])
            challenge = Challenge.objects.create(
                run=run,
                initiator_team_id=initiator.team_id,
                challenged_team_id=challenged.team_id,
                question_id="shared-challenge",
                paid_cost=7,
            )
            result = {
                "outcome": "challenge_started",
                "challenge_id": str(challenge.pk),
            }
            CommandReceipt.objects.create(
                run=run,
                actor=actor,
                request_id=request_id,
                action="initiate_challenge",
                payload_digest=digest,
                result=result,
            )
            AuditEvent.objects.create(
                run=run,
                actor=actor,
                request_id=request_id,
                actor_role="team",
                team_id=team_id,
                action="initiate_challenge",
                result="challenge_started",
                changes={"cost": 7, "challenge_id": str(challenge.pk)},
            )
            return result["outcome"]

    def _answer(self, team_id, request_id, *, is_correct=True):
        actor = self.users[team_id]
        with immediate_transaction():
            prior = CommandReceipt.objects.filter(
                actor=actor, request_id=request_id
            ).first()
            if prior is not None:
                return prior.result["outcome"]
            challenge = Challenge.objects.filter(
                run_id=self.run.pk, status="active"
            ).first()
            if challenge is None:
                return "stale_challenge"
            attempt = ChallengeAttempt.objects.create(
                challenge=challenge,
                actor=actor,
                team_id=team_id,
                request_id=request_id,
                question_id=challenge.question_id,
                is_correct=is_correct,
            )
            outcome = "won" if is_correct else "incorrect"
            if is_correct:
                teams = {
                    row.team_id: row
                    for row in TeamRun.objects.filter(run_id=self.run.pk).order_by(
                        "team_id"
                    )
                }
                initiator = teams[challenge.initiator_team_id]
                challenged = teams[challenge.challenged_team_id]
                initiator.activity_state = "PUZZLE"
                initiator.save(update_fields=["activity_state"])
                if team_id == challenge.initiator_team_id:
                    challenged.activity_state = "FREEZE"
                    challenged.freeze_started_gameplay_ms = 123_000
                    challenged.save(
                        update_fields=[
                            "activity_state",
                            "freeze_started_gameplay_ms",
                        ]
                    )
                else:
                    challenged.activity_state = "PUZZLE"
                    challenged.save(update_fields=["activity_state"])
                challenge.status = "resolved"
                challenge.winner_team_id = team_id
                challenge.freeze_applied = (
                    team_id == challenge.initiator_team_id
                )
                challenge.winning_attempt = attempt
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
            result = {"outcome": outcome, "challenge_id": str(challenge.pk)}
            CommandReceipt.objects.create(
                run_id=self.run.pk,
                actor=actor,
                request_id=request_id,
                action="submit_challenge_answer",
                payload_digest=team_id * 64,
                result=result,
            )
            AuditEvent.objects.create(
                run_id=self.run.pk,
                actor=actor,
                request_id=request_id,
                actor_role="team",
                team_id=team_id,
                action="submit_challenge_answer",
                result=outcome,
                puzzle_id=challenge.question_id,
            )
            return outcome

    def _compete(self, first_call, waiting_call):
        attempted = Event()
        connection_ids = []

        def contender():
            connections.close_all()
            own_connection = connections["default"]
            own_connection.ensure_connection()
            connection_ids.append(id(own_connection.connection))
            own_connection.connection.set_trace_callback(
                lambda sql: (
                    attempted.set()
                    if sql.strip().upper() == "BEGIN IMMEDIATE"
                    else None
                )
            )
            try:
                return waiting_call()
            finally:
                own_connection.connection.set_trace_callback(None)
                connections.close_all()

        main_connection = connections["default"]
        main_connection.ensure_connection()
        main_id = id(main_connection.connection)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with immediate_transaction():
                first_result = first_call()
                future = pool.submit(contender)
                self.assertTrue(attempted.wait(2))
                self.assertFalse(future.done())
            waiting_result = future.result(timeout=8)
        self.assertEqual(len(connection_ids), 1)
        self.assertNotEqual(main_id, connection_ids[0])
        return first_result, waiting_result

    def test_competing_initiations_spend_only_the_first_team(self):
        request_ids = {"a": uuid4(), "b": uuid4()}
        results = self._compete(
            lambda: self._start("b", request_ids["b"]),
            lambda: self._start("a", request_ids["a"]),
        )
        self.assertEqual(results, ("challenge_started", "challenge_unavailable"))
        teams = {
            row.team_id: row
            for row in TeamRun.objects.filter(run=self.run).order_by("team_id")
        }
        self.assertEqual(teams["b"].points, 3)
        self.assertFalse(teams["b"].challenge_available)
        self.assertEqual(teams["a"].points, 10)
        self.assertTrue(teams["a"].challenge_available)
        self.assertEqual(Challenge.objects.filter(run=self.run).count(), 1)
        self.assertEqual(CommandReceipt.objects.filter(run=self.run).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(run=self.run).count(), 1)

        self.assertEqual(
            self._start("b", request_ids["b"]), "challenge_started"
        )
        self.assertEqual(CommandReceipt.objects.filter(run=self.run).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(run=self.run).count(), 1)

    def _start_active_challenge(self):
        request_id = uuid4()
        self.assertEqual(self._start("a", request_id), "challenge_started")
        return Challenge.objects.get(run=self.run, status="active")

    def test_first_correct_answer_wins_once_and_freeze_is_not_replayed(self):
        challenge = self._start_active_challenge()
        request_ids = {"a": uuid4(), "b": uuid4()}
        results = self._compete(
            lambda: self._answer("a", request_ids["a"]),
            lambda: self._answer("b", request_ids["b"]),
        )
        self.assertEqual(results, ("won", "stale_challenge"))
        challenge.refresh_from_db()
        loser = TeamRun.objects.get(run=self.run, team_id="b")
        self.assertEqual(challenge.winner_team_id, "a")
        self.assertTrue(challenge.freeze_applied)
        self.assertEqual(loser.activity_state, "FREEZE")
        self.assertEqual(loser.freeze_started_gameplay_ms, 123_000)
        self.assertEqual(ChallengeAttempt.objects.filter(is_correct=True).count(), 1)

        self.assertEqual(self._answer("a", request_ids["a"]), "won")
        loser.refresh_from_db()
        self.assertEqual(loser.freeze_started_gameplay_ms, 123_000)
        self.assertEqual(ChallengeAttempt.objects.count(), 1)
        self.assertEqual(
            AuditEvent.objects.filter(action="submit_challenge_answer").count(), 1
        )

    def test_challenged_team_can_win_race_without_freeze(self):
        challenge = self._start_active_challenge()
        request_ids = {"a": uuid4(), "b": uuid4()}
        results = self._compete(
            lambda: self._answer("b", request_ids["b"]),
            lambda: self._answer("a", request_ids["a"]),
        )
        self.assertEqual(results, ("won", "stale_challenge"))
        challenge.refresh_from_db()
        self.assertEqual(challenge.winner_team_id, "b")
        self.assertFalse(challenge.freeze_applied)
        self.assertEqual(
            set(
                TeamRun.objects.filter(run=self.run).values_list(
                    "activity_state", flat=True
                )
            ),
            {"PUZZLE"},
        )

    def test_wrong_answer_retry_records_one_penalty_free_attempt(self):
        challenge = self._start_active_challenge()
        request_id = uuid4()
        self.assertEqual(
            self._answer("b", request_id, is_correct=False), "incorrect"
        )
        self.assertEqual(
            self._answer("b", request_id, is_correct=False), "incorrect"
        )
        challenge.refresh_from_db()
        teams = list(TeamRun.objects.filter(run=self.run).order_by("team_id"))
        self.assertEqual(challenge.status, "active")
        self.assertEqual([team.activity_state for team in teams], ["CHALLENGE"] * 2)
        self.assertEqual([team.points for team in teams], [3, 10])
        self.assertEqual(ChallengeAttempt.objects.count(), 1)
        self.assertEqual(
            AuditEvent.objects.filter(action="submit_challenge_answer").count(), 1
        )


class PhaseSixProductionCommandRaceTests(TransactionTestCase):
    """Race the public application commands, not a test-only transaction copy."""

    def setUp(self):
        if (
            not os.environ.get("TEST_DATABASE_PATH")
            or os.environ["TEST_DATABASE_PATH"] == ":memory:"
        ):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        settings = override_settings(
            QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name) / "snapshots"
        )
        settings.enable()
        self.addCleanup(settings.disable)
        users = get_user_model()
        admin_user = users.objects.create_user("phase6-production-race-admin")
        self.users = {
            team_id: users.objects.create_user(
                f"phase6-production-race-{team_id}"
            )
            for team_id in ("a", "b")
        }
        AccountRole.objects.create(user=admin_user, role="admin")
        for team_id, user in self.users.items():
            AccountRole.objects.create(user=user, role="team", team_id=team_id)
        self.admin = Actor(admin_user.pk, "admin")
        self.actors = {
            team_id: Actor(user.pk, "team", team_id)
            for team_id, user in self.users.items()
        }
        self.run_id = start_game(
            self.admin,
            StartGame(str(uuid4()), "christmas-2026-demo"),
            now=NOW,
        ).run_id

    def _command_outcome(self, command):
        try:
            return command().outcome
        except ApplicationError as exc:
            return exc.code

    def _compete(self, first_call, waiting_call):
        attempted = Event()

        def contender():
            connections.close_all()
            connection = connections["default"]
            connection.ensure_connection()
            connection.connection.set_trace_callback(
                lambda sql: (
                    attempted.set()
                    if sql.strip().upper() == "BEGIN IMMEDIATE"
                    else None
                )
            )
            try:
                return waiting_call()
            finally:
                connection.connection.set_trace_callback(None)
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with immediate_transaction():
                first_result = first_call()
                future = pool.submit(contender)
                self.assertTrue(attempted.wait(2))
                self.assertFalse(future.done())
            waiting_result = future.result(timeout=8)
        return first_result, waiting_result

    def test_production_initiation_race_charges_only_one_team(self):
        request_ids = {team_id: str(uuid4()) for team_id in ("a", "b")}
        results = self._compete(
            lambda: self._command_outcome(
                lambda: initiate_challenge(
                    self.actors["a"],
                    RunCommand(request_ids["a"], self.run_id),
                    now=NOW,
                )
            ),
            lambda: self._command_outcome(
                lambda: initiate_challenge(
                    self.actors["b"],
                    RunCommand(request_ids["b"], self.run_id),
                    now=NOW,
                )
            ),
        )
        self.assertEqual(results, ("challenge_started", "disallowed_state"))
        teams = {
            team.team_id: team
            for team in TeamRun.objects.filter(run_id=self.run_id).order_by("team_id")
        }
        self.assertEqual(teams["a"].points, 1)
        self.assertFalse(teams["a"].challenge_available)
        self.assertEqual(teams["b"].points, 3)
        self.assertTrue(teams["b"].challenge_available)
        self.assertEqual(Challenge.objects.filter(run_id=self.run_id).count(), 1)
        self.assertEqual(
            CommandReceipt.objects.filter(
                run_id=self.run_id, action="initiate_challenge"
            ).count(),
            1,
        )

    def test_production_correct_answer_race_resolves_and_freezes_once(self):
        initiate_challenge(
            self.actors["a"], RunCommand(str(uuid4()), self.run_id), now=NOW
        )
        challenge = Challenge.objects.get(run_id=self.run_id, status="active")
        request_ids = {team_id: str(uuid4()) for team_id in ("a", "b")}
        results = self._compete(
            lambda: self._command_outcome(
                lambda: submit_challenge_answer(
                    self.actors["a"],
                    SubmitChallengeAnswer(
                        request_ids["a"],
                        self.run_id,
                        str(challenge.id),
                        challenge.question_id,
                        "santa",
                    ),
                    now=NOW,
                )
            ),
            lambda: self._command_outcome(
                lambda: submit_challenge_answer(
                    self.actors["b"],
                    SubmitChallengeAnswer(
                        request_ids["b"],
                        self.run_id,
                        str(challenge.id),
                        challenge.question_id,
                        "santa",
                    ),
                    now=NOW,
                )
            ),
        )
        self.assertEqual(results, ("won", "stale_challenge"))
        challenge.refresh_from_db()
        frozen = TeamRun.objects.get(run_id=self.run_id, team_id="b")
        self.assertEqual(challenge.winner_team_id, "a")
        self.assertTrue(challenge.freeze_applied)
        self.assertEqual(frozen.activity_state, "FREEZE")
        self.assertEqual(
            ChallengeAttempt.objects.filter(challenge=challenge).count(), 1
        )
        self.assertEqual(
            CommandReceipt.objects.filter(
                run_id=self.run_id, action="submit_challenge_answer"
            ).count(),
            1,
        )
