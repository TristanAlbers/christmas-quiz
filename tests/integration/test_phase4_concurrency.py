"""Deterministic separate-connection SQLite races for phase-4 storage."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TransactionTestCase
from django.utils import timezone

from quiz import _application_core as core
from quiz.models import (
    AccountRole,
    AuditEvent,
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


class PhaseFourSQLiteRaceTests(TransactionTestCase):
    def setUp(self):
        if (
            not os.environ.get("TEST_DATABASE_PATH")
            or os.environ["TEST_DATABASE_PATH"] == ":memory:"
        ):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        users = get_user_model()
        self.a_user = users.objects.create_user("phase4-race-a")
        self.b_user = users.objects.create_user("phase4-race-b")
        AccountRole.objects.create(user=self.a_user, role="team", team_id="a")
        AccountRole.objects.create(user=self.b_user, role="team", team_id="b")

    def _new_music_run(self):
        Run.objects.filter(active=True).update(active=False)
        run = Run.objects.create(
            global_state="MUSIC_QUIZ",
            package_id="phase4",
            snapshot_path="/tmp/pinned",
            snapshot_digest="a" * 64,
        )
        TeamRun.objects.bulk_create(
            [
                TeamRun(run=run, team_id="a", activity_state="PUZZLE", points=10),
                TeamRun(run=run, team_id="b", activity_state="PUZZLE", points=10),
            ]
        )
        MusicQuiz.objects.create(
            run=run,
            phase="question",
            current_question_number=1,
            current_question_started_ms=0,
            music_clock_anchor=timezone.now(),
        )
        MusicScore.objects.bulk_create(
            [MusicScore(run=run, team_id="a"), MusicScore(run=run, team_id="b")]
        )
        return run

    def _answer(self, run_id, team_id, user_id, request_id):
        with immediate_transaction():
            run = Run.objects.get(pk=run_id)
            music = MusicQuiz.objects.get(run=run)
            if (
                run.global_state != "MUSIC_QUIZ"
                or music.phase != "question"
                or music.current_question_number != 1
            ):
                return "stale_question"
            attempt = MusicAttempt.objects.create(
                run=run,
                team_id=team_id,
                actor_id=user_id,
                request_id=request_id,
                question_number=1,
                question_id="music-1",
                is_correct=True,
            )
            MusicQuestionResult.objects.create(
                run=run,
                question_number=1,
                question_id="music-1",
                winner_team_id=team_id,
                reward_points=5,
                winning_attempt=attempt,
            )
            score = MusicScore.objects.get(run=run, team_id=team_id)
            score.score += 1
            score.save(update_fields=["score"])
            team = TeamRun.objects.get(run=run, team_id=team_id)
            team.points += 5
            team.save(update_fields=["points"])
            music.current_question_number = 2
            music.current_question_started_ms = 25
            music.previous_winner_team = team_id
            music.save(
                update_fields=[
                    "current_question_number",
                    "current_question_started_ms",
                    "previous_winner_team",
                ]
            )
            CommandReceipt.objects.create(
                run=run,
                actor_id=user_id,
                request_id=request_id,
                action="submit_music_answer",
                payload_digest=(team_id * 64),
                result={"outcome": "won", "question_id": "music-1"},
            )
            AuditEvent.objects.create(
                run=run,
                request_id=request_id,
                actor_id=user_id,
                actor_role="team",
                team_id=team_id,
                action="music_answer",
                result="won",
                puzzle_id="music-1",
                changes={"score": 1, "reward": 5},
            )
            return "won"

    def _compete(self, first, second):
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
                return second()
            finally:
                own_connection.connection.set_trace_callback(None)
                connections.close_all()

        main_connection = connections["default"]
        main_connection.ensure_connection()
        main_id = id(main_connection.connection)
        with ThreadPoolExecutor(max_workers=1) as pool:
            with immediate_transaction():
                first_result = first()
                future = pool.submit(contender)
                self.assertTrue(
                    attempted.wait(2), "contender did not reach BEGIN IMMEDIATE"
                )
                self.assertFalse(
                    future.done(), "contender crossed the held SQLite writer slot"
                )
            second_result = future.result(timeout=8)
        self.assertEqual(len(connection_ids), 1)
        self.assertNotEqual(main_id, connection_ids[0])
        return first_result, second_result

    def _assert_music_winner_direction(self, first_team):
        run = self._new_music_run()
        second_team = "b" if first_team == "a" else "a"
        users = {"a": self.a_user, "b": self.b_user}
        first_request = uuid4()
        second_request = uuid4()
        first, second = self._compete(
            lambda: self._answer(
                run.pk,
                first_team,
                users[first_team].pk,
                first_request,
            ),
            lambda: self._answer(
                run.pk,
                second_team,
                users[second_team].pk,
                second_request,
            ),
        )
        self.assertEqual((first, second), ("won", "stale_question"))
        self.assertEqual(MusicQuestionResult.objects.filter(run=run).count(), 1)
        result = MusicQuestionResult.objects.get(run=run)
        self.assertEqual(result.winner_team_id, first_team)
        self.assertEqual(MusicAttempt.objects.filter(run=run).count(), 1)
        self.assertEqual(CommandReceipt.objects.filter(run=run).count(), 1)
        self.assertEqual(AuditEvent.objects.filter(run=run, result="won").count(), 1)
        self.assertEqual(MusicScore.objects.get(run=run, team_id=first_team).score, 1)
        self.assertEqual(MusicScore.objects.get(run=run, team_id=second_team).score, 0)
        self.assertEqual(TeamRun.objects.get(run=run, team_id=first_team).points, 15)
        self.assertEqual(TeamRun.objects.get(run=run, team_id=second_team).points, 10)
        music = MusicQuiz.objects.get(run=run)
        self.assertEqual(
            (music.current_question_number, music.current_question_started_ms),
            (2, 25),
        )

    def test_a_first_has_one_winner_reward_score_event_and_advance(self):
        self._assert_music_winner_direction("a")

    def test_b_first_has_one_winner_reward_score_event_and_advance(self):
        self._assert_music_winner_direction("b")

    def test_concurrent_puzzle_thirteen_completion_creates_one_trigger(self):
        Run.objects.filter(active=True).update(active=False)
        run = Run.objects.create(
            global_state="ADVENT_QUIZ",
            package_id="phase4",
            snapshot_path="/tmp/pinned",
            snapshot_digest="b" * 64,
            advent_clock_anchor=timezone.now(),
        )
        TeamRun.objects.bulk_create(
            [
                TeamRun(
                    run=run, team_id="a", activity_state="PUZZLE", current_number=13
                ),
                TeamRun(
                    run=run, team_id="b", activity_state="PUZZLE", current_number=13
                ),
            ]
        )
        for team_id in ("a", "b"):
            PuzzleProgress.objects.create(
                run=run,
                team_id=team_id,
                puzzle_id=f"{team_id}-13",
                number=13,
            )

        def trigger(team_id, user):
            with immediate_transaction():
                current = Run.objects.get(pk=run.pk)
                if current.global_state != "ADVENT_QUIZ":
                    return "interrupted"
                progress = PuzzleProgress.objects.get(
                    run=current, team_id=team_id, number=13
                )
                progress.completed = True
                progress.completion_route = "answer"
                progress.reward_awarded = True
                progress.completed_at = timezone.now()
                progress.save()
                current.global_state = "MUSIC_QUIZ"
                current.advent_clock_anchor = None
                current.save(update_fields=["global_state", "advent_clock_anchor"])
                MusicQuiz.objects.create(
                    run=current,
                    phase="gathering",
                    music_clock_anchor=timezone.now(),
                )
                MusicScore.objects.create(run=current, team_id="a")
                MusicScore.objects.create(run=current, team_id="b")
                AuditEvent.objects.create(
                    run=current,
                    request_id=uuid4(),
                    actor=user,
                    actor_role="team",
                    team_id=team_id,
                    action="music_started",
                    result="started",
                    puzzle_id=f"{team_id}-13",
                    changes={},
                )
                return "started"

        first, second = self._compete(
            lambda: trigger("a", self.a_user),
            lambda: trigger("b", self.b_user),
        )
        self.assertEqual((first, second), ("started", "interrupted"))
        self.assertEqual(MusicQuiz.objects.filter(run=run).count(), 1)
        self.assertEqual(MusicScore.objects.filter(run=run).count(), 2)
        self.assertEqual(
            AuditEvent.objects.filter(run=run, action="music_started").count(), 1
        )
        self.assertEqual(
            PuzzleProgress.objects.filter(run=run, number=13, completed=True).count(),
            1,
        )

    def test_boundary_reconciliation_initializes_question_one_once(self):
        Run.objects.filter(active=True).update(active=False)
        observed_at = timezone.now()
        run = Run.objects.create(
            global_state="MUSIC_QUIZ",
            package_id="phase4",
            snapshot_path="/tmp/pinned",
            snapshot_digest="c" * 64,
            gameplay_elapsed_ms=123,
            advent_clock_anchor=None,
        )
        MusicQuiz.objects.create(
            run=run,
            phase="gathering",
            music_elapsed_ms=60_000,
            music_clock_anchor=observed_at,
        )
        config = {"music_score_display_duration_ms": 1_000}

        def reconcile():
            with immediate_transaction():
                current = Run.objects.get(pk=run.pk)
                return core._persist_music_timing(current, config, observed_at)

        first, second = self._compete(reconcile, reconcile)
        self.assertEqual((first, second), ("question_started", None))
        music = MusicQuiz.objects.get(run=run)
        self.assertEqual(music.phase, "question")
        self.assertEqual(music.current_question_number, 1)
        self.assertEqual(music.current_question_started_ms, 60_000)
        self.assertEqual(music.music_elapsed_ms, 60_000)
        self.assertEqual(music.music_clock_anchor, observed_at)
        self.assertFalse(AuditEvent.objects.filter(run=run).exists())
        self.assertFalse(MusicAttempt.objects.filter(run=run).exists())
        self.assertFalse(MusicQuestionResult.objects.filter(run=run).exists())
