"""Real SQLite writer-contention checks for the first completion boundary.

Run with TEST_DATABASE_PATH=/tmp/christmas-quiz-phase1.sqlite3 so Django creates a
disposable file-backed test database. Each competing thread has its own connection.
"""

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase, override_settings

from quiz.application import get_team_state, start_game, submit_answer
from quiz.contracts import Actor, ApplicationError, StartGame, SubmitAnswer
from quiz.models import (
    AccountRole,
    AnswerReceipt,
    Attempt,
    AuditEvent,
    FragmentAward,
    PuzzleProgress,
)
from quiz.persistence import immediate_transaction


class CompletionContentionTests(TransactionTestCase):
    def setUp(self):
        test_database = os.environ.get("TEST_DATABASE_PATH", "")
        if not test_database or test_database == ":memory:":
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)
        users = get_user_model()
        admin = users.objects.create_user("race-admin", password="admin-pin")
        team = users.objects.create_user("race-a", password="a-pin")
        AccountRole.objects.create(user=admin, role="admin")
        AccountRole.objects.create(user=team, role="team", team_id="a")
        self.actor = Actor(team.pk, "team", "a")
        self.run_id = start_game(
            Actor(admin.pk, "admin"),
            StartGame(str(uuid4()), "christmas-2026-demo"),
        ).run_id

    def _assert_first_writer_wins(self, first_answer, second_answer):
        first = SubmitAnswer(str(uuid4()), self.run_id, "a-1", first_answer)
        second = SubmitAnswer(str(uuid4()), self.run_id, "a-1", second_answer)
        writer_attempted = Event()

        def competing_request():
            connections.close_all()  # Guaranteed independent SQLite connection.
            own_connection = connections["default"]
            own_connection.ensure_connection()
            own_connection.connection.set_trace_callback(
                lambda sql: writer_attempted.set()
                if sql.strip().upper() == "BEGIN IMMEDIATE"
                else None
            )
            try:
                return submit_answer(self.actor, second)
            except ApplicationError as error:
                return error
            finally:
                own_connection.connection.set_trace_callback(None)
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with immediate_transaction():
                first_result = submit_answer(self.actor, first)
                future = pool.submit(competing_request)
                self.assertTrue(writer_attempted.wait(timeout=2))
                self.assertFalse(
                    future.done(), "second writer passed the held transaction"
                )
            second_result = future.result(timeout=8)

        self.assertEqual(first_result.outcome, "completed")
        self.assertIsInstance(second_result, ApplicationError)
        self.assertEqual(second_result.code, "stale_question")
        state = get_team_state(self.actor)
        self.assertEqual(state.current_number, 2)
        self.assertEqual(state.points, 7)
        self.assertEqual(state.fragments, ("DEMO-A-STAR",))
        self.assertEqual(Attempt.objects.filter(team_id="a").count(), 1)
        self.assertEqual(
            AnswerReceipt.objects.filter(actor_id=self.actor.user_id).count(), 1
        )
        self.assertEqual(FragmentAward.objects.filter(team_id="a").count(), 1)
        self.assertEqual(
            PuzzleProgress.objects.filter(
                team_id="a", number=1, completed=True
            ).count(),
            1,
        )
        self.assertEqual(AuditEvent.objects.filter(team_id="a").count(), 1)

    def test_first_correct_writer_wins_then_duplicate_correct_is_stale(self):
        self._assert_first_writer_wins("red", "red")

    def test_first_correct_writer_wins_then_late_wrong_is_stale(self):
        self._assert_first_writer_wins("red", "blue")
