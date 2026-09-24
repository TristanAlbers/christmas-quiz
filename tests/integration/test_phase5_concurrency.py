"""Deterministic separate-connection final-finish race storage checks."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase

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


class PhaseFiveFinalRaceTests(TransactionTestCase):
    def setUp(self):
        if (
            not os.environ.get("TEST_DATABASE_PATH")
            or os.environ["TEST_DATABASE_PATH"] == ":memory:"
        ):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        users = get_user_model()
        self.users = {
            "a": users.objects.create_user("phase5-race-a"),
            "b": users.objects.create_user("phase5-race-b"),
        }
        for team_id, user in self.users.items():
            AccountRole.objects.create(user=user, role="team", team_id=team_id)
        self.run = Run.objects.create(
            global_state="ADVENT_QUIZ",
            package_id="phase5",
            snapshot_path="/tmp/pinned",
            snapshot_digest="e" * 64,
        )
        TeamRun.objects.bulk_create(
            [
                TeamRun(
                    run=self.run,
                    team_id=team_id,
                    activity_state="PUZZLE",
                    current_number=25,
                )
                for team_id in ("a", "b")
            ]
        )
        PuzzleProgress.objects.bulk_create(
            [
                PuzzleProgress(
                    run=self.run,
                    team_id=team_id,
                    puzzle_id=f"{team_id}-25",
                    number=25,
                )
                for team_id in ("a", "b")
            ]
        )

    def _finish(self, team_id, request_id):
        user = self.users[team_id]
        with immediate_transaction():
            prior = CommandReceipt.objects.filter(
                actor=user,
                request_id=request_id,
            ).first()
            if prior is not None:
                return prior.result["finish_order"]

            run = Run.objects.get(pk=self.run.pk)
            team = TeamRun.objects.get(run=run, team_id=team_id)
            progress = PuzzleProgress.objects.get(
                run=run,
                team_id=team_id,
                number=25,
            )
            if team.activity_state != "PUZZLE" or progress.completed:
                return "stale_question"

            team.activity_state = "FINISHED"
            team.save(update_fields=["activity_state"])
            progress.completed = True
            progress.reward_awarded = True
            progress.completion_route = "correct_answer"
            progress.save(
                update_fields=[
                    "completed",
                    "reward_awarded",
                    "completion_route",
                ]
            )

            claim = FirstFinisher.objects.filter(run=run).first()
            if claim is None:
                FirstFinisher.objects.create(run=run, team_id=team_id)
                finish_order = "first"
                extra_action = "first_finisher"
            else:
                run.global_state = "FINISHED"
                run.advent_clock_anchor = None
                run.save(update_fields=["global_state", "advent_clock_anchor"])
                finish_order = "second"
                extra_action = "game_finished"

            result = {
                "outcome": "completed",
                "puzzle_id": f"{team_id}-25",
                "finish_order": finish_order,
            }
            CommandReceipt.objects.create(
                run=run,
                actor=user,
                request_id=request_id,
                action="submit_answer",
                payload_digest=team_id * 64,
                result=result,
            )
            for action in ("team_finished", extra_action):
                AuditEvent.objects.create(
                    run=run,
                    actor=user,
                    request_id=request_id,
                    actor_role="team",
                    team_id=team_id,
                    action=action,
                    result="recorded",
                    puzzle_id=f"{team_id}-25",
                )
            return finish_order

    def _compete(self, first_team, second_team, request_ids):
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
                return self._finish(second_team, request_ids[second_team])
            finally:
                own_connection.connection.set_trace_callback(None)
                connections.close_all()

        main_connection = connections["default"]
        main_connection.ensure_connection()
        main_id = id(main_connection.connection)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with immediate_transaction():
                first_result = self._finish(first_team, request_ids[first_team])
                future = pool.submit(contender)
                self.assertTrue(
                    attempted.wait(2),
                    "contender did not reach BEGIN IMMEDIATE",
                )
                self.assertFalse(
                    future.done(),
                    "contender crossed the held SQLite writer slot",
                )
            second_result = future.result(timeout=8)
        self.assertEqual(len(connection_ids), 1)
        self.assertNotEqual(main_id, connection_ids[0])
        return first_result, second_result

    def _assert_direction(self, first_team):
        second_team = "b" if first_team == "a" else "a"
        request_ids = {"a": uuid4(), "b": uuid4()}
        result = self._compete(first_team, second_team, request_ids)

        self.assertEqual(result, ("first", "second"))
        claim = FirstFinisher.objects.get(run=self.run)
        self.assertEqual(claim.team_id, first_team)
        self.assertEqual(
            TeamRun.objects.filter(
                run=self.run,
                activity_state="FINISHED",
            ).count(),
            2,
        )
        self.assertEqual(
            PuzzleProgress.objects.filter(
                run=self.run,
                number=25,
                completed=True,
                reward_awarded=True,
            ).count(),
            2,
        )
        self.run.refresh_from_db()
        self.assertEqual(self.run.global_state, "FINISHED")
        self.assertEqual(CommandReceipt.objects.filter(run=self.run).count(), 2)
        self.assertEqual(
            AuditEvent.objects.filter(run=self.run, action="team_finished").count(),
            2,
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                run=self.run,
                action="first_finisher",
            ).count(),
            1,
        )
        self.assertEqual(
            AuditEvent.objects.filter(run=self.run, action="game_finished").count(),
            1,
        )

        retry = self._finish(first_team, request_ids[first_team])
        self.assertEqual(retry, "first")
        self.assertEqual(FirstFinisher.objects.filter(run=self.run).count(), 1)
        self.assertEqual(CommandReceipt.objects.filter(run=self.run).count(), 2)
        self.assertEqual(AuditEvent.objects.filter(run=self.run).count(), 4)

    def test_a_commits_first_and_b_finishes_second(self):
        self._assert_direction("a")

    def test_b_commits_first_and_a_finishes_second(self):
        self._assert_direction("b")
