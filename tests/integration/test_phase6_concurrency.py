"""Separate-connection Phase 6 races through the production application commands."""

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from datetime import timezone as datetime_timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase, override_settings

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
    TeamRun,
)
from quiz.persistence import immediate_transaction

NOW = datetime(2026, 12, 24, 18, 0, tzinfo=datetime_timezone.utc)
GRACE_END = NOW + timedelta(seconds=15)


class PhaseSixProductionCommandRaceTests(TransactionTestCase):
    """Race real Challenge commands over separate SQLite connections."""

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
        connection_ids = []

        def contender():
            connections.close_all()
            connection = connections["default"]
            connection.ensure_connection()
            connection_ids.append(id(connection.connection))
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

    def _initiate(self, team_id, request_id, now=NOW):
        return self._command_outcome(
            lambda: initiate_challenge(
                self.actors[team_id],
                RunCommand(request_id, self.run_id),
                now=now,
            )
        )

    def _answer(self, team_id, challenge, request_id, answer, now=GRACE_END):
        return self._command_outcome(
            lambda: submit_challenge_answer(
                self.actors[team_id],
                SubmitChallengeAnswer(
                    request_id,
                    self.run_id,
                    str(challenge.id),
                    challenge.question_id,
                    answer,
                ),
                now=now,
            )
        )

    def test_competing_initiations_consume_only_first_opportunity_and_no_points(self):
        request_ids = {team_id: str(uuid4()) for team_id in ("a", "b")}
        results = self._compete(
            lambda: self._initiate("a", request_ids["a"]),
            lambda: self._initiate("b", request_ids["b"]),
        )
        self.assertEqual(results, ("challenge_started", "disallowed_state"))

        teams = {
            team.team_id: team
            for team in TeamRun.objects.filter(run_id=self.run_id).order_by("team_id")
        }
        self.assertEqual(teams["a"].points, 3)
        self.assertFalse(teams["a"].challenge_available)
        self.assertEqual(teams["b"].points, 3)
        self.assertTrue(teams["b"].challenge_available)
        self.assertEqual(teams["a"].activity_state, "CHALLENGE")
        self.assertEqual(teams["b"].activity_state, "CHALLENGE")

        challenge = Challenge.objects.get(run_id=self.run_id)
        self.assertEqual(challenge.initiator_team_id, "a")
        self.assertEqual(challenge.question_id, "challenge-a-reindeer")
        self.assertEqual(challenge.paid_cost, 0)
        self.assertEqual(challenge.started_gameplay_ms, 0)
        self.assertEqual(
            CommandReceipt.objects.filter(
                run_id=self.run_id, action="initiate_challenge"
            ).count(),
            1,
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                run_id=self.run_id, action="initiate_challenge"
            ).count(),
            1,
        )

        self.assertEqual(
            self._initiate("a", request_ids["a"]), "challenge_started"
        )
        self.assertEqual(
            CommandReceipt.objects.filter(
                run_id=self.run_id, action="initiate_challenge"
            ).count(),
            1,
        )

    def test_first_correct_answer_after_grace_wins_once(self):
        self.assertEqual(
            self._initiate("a", str(uuid4())),
            "challenge_started",
        )
        challenge = Challenge.objects.get(run_id=self.run_id, status="active")
        request_ids = {team_id: str(uuid4()) for team_id in ("a", "b")}

        results = self._compete(
            lambda: self._answer(
                "a", challenge, request_ids["a"], "rudolph", GRACE_END
            ),
            lambda: self._answer(
                "b", challenge, request_ids["b"], "rudolph", GRACE_END
            ),
        )
        self.assertEqual(results, ("won", "stale_challenge"))

        challenge.refresh_from_db()
        loser = TeamRun.objects.get(run_id=self.run_id, team_id="b")
        self.assertEqual(challenge.winner_team_id, "a")
        self.assertTrue(challenge.freeze_applied)
        self.assertEqual(loser.activity_state, "FREEZE")
        self.assertEqual(loser.freeze_started_gameplay_ms, 15_000)
        correct_attempts = ChallengeAttempt.objects.filter(
            challenge=challenge, is_correct=True
        ).count()
        self.assertEqual(correct_attempts, 1)
        self.assertEqual(
            CommandReceipt.objects.filter(
                run_id=self.run_id, action="submit_challenge_answer"
            ).count(),
            1,
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                run_id=self.run_id, action="submit_challenge_answer"
            ).count(),
            1,
        )

        self.assertEqual(
            self._answer(
                "a", challenge, request_ids["a"], "rudolph", GRACE_END
            ),
            "won",
        )
        loser.refresh_from_db()
        self.assertEqual(loser.freeze_started_gameplay_ms, 15_000)
        attempts = ChallengeAttempt.objects.filter(challenge=challenge).count()
        self.assertEqual(attempts, 1)

    def test_challenged_win_allows_other_team_to_start_distinct_second_challenge(self):
        self.assertEqual(self._initiate("a", str(uuid4())), "challenge_started")
        first = Challenge.objects.get(run_id=self.run_id, status="active")
        self.assertEqual(
            self._answer("b", first, str(uuid4()), "rudolph", GRACE_END),
            "won",
        )

        second_start = GRACE_END + timedelta(seconds=1)
        self.assertEqual(
            self._initiate("b", str(uuid4()), second_start),
            "challenge_started",
        )
        second = Challenge.objects.get(
            run_id=self.run_id,
            initiator_team_id="b",
        )
        self.assertEqual(second.question_id, "challenge-b-five-gifts")
        self.assertNotEqual(first.question_id, second.question_id)
        self.assertEqual(Challenge.objects.filter(run_id=self.run_id).count(), 2)

        self.assertEqual(
            self._initiate("a", str(uuid4()), second_start),
            "challenge_spent",
        )
        self.assertEqual(
            self._answer(
                "a",
                second,
                str(uuid4()),
                "5",
                second_start + timedelta(seconds=14),
            ),
            "challenge_starting",
        )
        self.assertEqual(
            self._answer(
                "a",
                second,
                str(uuid4()),
                "5",
                second_start + timedelta(seconds=15),
            ),
            "won",
        )
        self.assertEqual(
            ChallengeAttempt.objects.filter(challenge=second, is_correct=True).count(),
            1,
        )
