"""Focused Phase 5 application journeys, projections, and recovery checks."""

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings

from quiz.application import (
    force_complete_current,
    freeze_opponent,
    get_admin_state,
    get_public_state,
    get_team_state,
    purchase_hint,
    purchase_uno_reverse,
    skip_current,
    start_game,
    submit_answer,
    submit_music_answer,
    use_hint,
)
from quiz.contracts import (
    Actor,
    AdminPuzzle,
    ApplicationError,
    RunCommand,
    StartGame,
    SubmitAnswer,
    SubmitMusicAnswer,
    TeamPuzzle,
)
from quiz.models import (
    AccountRole,
    AnswerReceipt,
    AuditEvent,
    FirstFinisher,
    FragmentAward,
    PuzzleProgress,
    Run,
    TeamRun,
)
from quiz.persistence import immediate_transaction
from quiz.web.views import _question_context, _team_actions_context

NOW = datetime(2026, 12, 24, 18, 0, tzinfo=timezone.utc)
MUSIC_ANSWERS = (
    "jingle bells",
    "silent night",
    "white christmas",
    "feliz navidad",
    "last christmas",
    "santa baby",
    "winter wonderland",
    "let it snow",
    "the christmas song",
    "rudolph",
    "deck the halls",
)
ADVENT_ANSWERS = {
    "a": (
        "red",
        "3",
        "snow",
        "4",
        "holly",
        "6",
        "sleigh",
        "8",
        "tinsel",
        "10",
        "mistletoe",
        "12",
        "music",
        "candle",
        "15",
        "robin",
        "17",
        "lantern",
        "evergreen",
        "20",
        "nutcracker",
        "22",
        "pudding",
        "24",
        "carol",
    ),
    "b": (
        "blue",
        "7",
        "frost",
        "4",
        "ivy",
        "6",
        "reindeer",
        "8",
        "garland",
        "10",
        "stocking",
        "12",
        "songs",
        "nutmeg",
        "15",
        "ribbon",
        "17",
        "hearth",
        "snowflake",
        "20",
        "chimney",
        "22",
        "cranberry",
        "24",
        "north",
    ),
}


class PhaseFiveApplicationTests(TestCase):
    def setUp(self):
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        settings = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        settings.enable()
        self.addCleanup(settings.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("phase5-app-admin")
        a_user = users.objects.create_user("phase5-app-a")
        b_user = users.objects.create_user("phase5-app-b")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=a_user, role="team", team_id="a")
        AccountRole.objects.create(user=b_user, role="team", team_id="b")
        self.admin = Actor(admin_user.pk, "admin")
        self.a = Actor(a_user.pk, "team", "a")
        self.b = Actor(b_user.pk, "team", "b")
        self.run_id = start_game(
            self.admin,
            StartGame(str(uuid4()), "christmas-2026-demo"),
            now=NOW,
        ).run_id

    def force(self, team_id, number, *, now):
        return force_complete_current(
            self.admin,
            AdminPuzzle(
                str(uuid4()),
                self.run_id,
                team_id,
                f"{team_id}-{number}",
            ),
            now=now,
        )

    def answer(self, actor, team_id, number, *, now, request_id=None):
        return submit_answer(
            actor,
            SubmitAnswer(
                request_id or str(uuid4()),
                self.run_id,
                f"{team_id}-{number}",
                ADVENT_ANSWERS[team_id][number - 1],
            ),
            now=now,
        )

    def reach_music_and_resume(self):
        for number in range(1, 13):
            self.answer(self.a, "a", number, now=NOW)
            self.answer(self.b, "b", number, now=NOW)
        self.answer(self.a, "a", 13, now=NOW + timedelta(seconds=5))
        for number, answer in enumerate(MUSIC_ANSWERS, start=1):
            actor = self.a if number % 2 else self.b
            submit_music_answer(
                actor,
                SubmitMusicAnswer(str(uuid4()), self.run_id, f"music-{number}", answer),
                now=NOW + timedelta(seconds=65 + number),
            )
        resumed_at = NOW + timedelta(seconds=136)
        self.answer(self.b, "b", 13, now=resumed_at)
        return resumed_at

    def test_complete_two_team_journeys_finish_once_and_recover(self):
        resumed_at = self.reach_music_and_resume()
        for number in range(14, 25):
            self.answer(self.a, "a", number, now=resumed_at)
            self.answer(self.b, "b", number, now=resumed_at)

        a_final = get_team_state(self.a, now=resumed_at)
        b_final = get_team_state(self.b, now=resumed_at)
        self.assertEqual(a_final.fragments[-5:], ("C", "A", "R", "O", "L"))
        self.assertEqual(b_final.fragments[-5:], ("N", "O", "R", "T", "H"))
        self.assertIn("five single-letter fragments", a_final.question.body)
        self.assertIn("five single-letter fragments", b_final.question.body)

        a_request = str(uuid4())
        a_finish = self.answer(
            self.a,
            "a",
            25,
            request_id=a_request,
            now=resumed_at + timedelta(seconds=10),
        )
        self.assertEqual(a_finish.outcome, "completed")
        self.assertEqual(a_finish.state.team_state, "FINISHED")
        self.assertEqual(a_finish.state.current_number, 25)
        self.assertIsNone(a_finish.state.question)
        self.assertEqual(a_finish.state.first_finisher_team_id, "a")
        self.assertEqual(a_finish.state.advent_progress.completed_count, 25)
        self.assertIsNone(a_finish.state.advent_progress.current_number)
        self.assertTrue(a_finish.state.advent_progress.is_finished)
        self.assertEqual(
            {door.status for door in a_finish.state.advent_progress.doors},
            {"completed"},
        )

        continuing = get_team_state(self.b, now=resumed_at + timedelta(seconds=11))
        self.assertEqual(continuing.global_state, "ADVENT_QUIZ")
        self.assertEqual(continuing.team_state, "PUZZLE")
        self.assertEqual(continuing.question.id, "b-25")
        self.assertEqual(continuing.advent_progress.current_number, 25)
        self.assertEqual(continuing.first_finisher_team_id, "a")
        with self.assertRaises(ApplicationError) as finished_action:
            purchase_hint(
                self.a,
                RunCommand(str(uuid4()), self.run_id),
                now=resumed_at + timedelta(seconds=11),
            )
        self.assertEqual(finished_action.exception.code, "disallowed_state")

        b_finish = self.answer(
            self.b,
            "b",
            25,
            now=resumed_at + timedelta(seconds=20),
        )
        self.assertEqual(b_finish.state.global_state, "FINISHED")
        run = Run.objects.get(pk=self.run_id)
        self.assertEqual(run.global_state, "FINISHED")
        self.assertIsNone(run.advent_clock_anchor)
        stopped_elapsed = run.gameplay_elapsed_ms

        retry = submit_answer(
            self.a,
            SubmitAnswer(a_request, self.run_id, "a-25", "carol"),
            now=resumed_at + timedelta(days=1),
        )
        self.assertEqual(retry.outcome, "completed")
        self.assertEqual(retry.state.global_state, "FINISHED")
        self.assertEqual(retry.state.gameplay_elapsed_ms, stopped_elapsed)
        recovered_public = get_public_state(now=resumed_at + timedelta(days=1))
        self.assertEqual(recovered_public.global_state, "FINISHED")
        self.assertEqual(recovered_public.first_finisher_team_id, "a")
        self.assertEqual(recovered_public.gameplay_elapsed_ms, stopped_elapsed)
        self.assertTrue(
            all(team.advent_progress.is_finished for team in recovered_public.teams)
        )
        self.assertEqual(FirstFinisher.objects.get(run=run).team_id, "a")
        self.assertEqual(AnswerReceipt.objects.filter(run=run).count(), 50)
        self.assertEqual(
            PuzzleProgress.objects.filter(
                run=run, number=25, completed=True, reward_awarded=True
            ).count(),
            2,
        )
        self.assertEqual(
            FragmentAward.objects.filter(
                run=run, puzzle_id__in=("a-25", "b-25")
            ).count(),
            2,
        )
        self.assertEqual(
            AuditEvent.objects.filter(run=run, action="team_finished").count(), 2
        )
        self.assertEqual(
            AuditEvent.objects.filter(run=run, action="first_finisher").count(), 1
        )
        self.assertEqual(
            AuditEvent.objects.filter(run=run, action="game_finished").count(), 1
        )

    def test_projection_boundaries_and_polling_context_after_first_finish(self):
        resumed_at = self.reach_music_and_resume()
        for number in range(14, 25):
            self.force("a", number, now=resumed_at)

        before = get_team_state(self.b, now=resumed_at)
        answer_context = _question_context(before)
        action_context = _team_actions_context(before)
        self.force("a", 25, now=resumed_at + timedelta(seconds=1))
        after = get_team_state(self.b, now=resumed_at + timedelta(seconds=2))
        self.assertEqual(_question_context(after), answer_context)
        self.assertNotEqual(_team_actions_context(after), action_context)

        admin = get_admin_state(self.admin, now=resumed_at + timedelta(seconds=2))
        self.assertEqual(admin.first_finisher_team_id, "a")
        self.assertEqual(len(admin.teams), 2)
        self.assertTrue(admin.teams[0].advent_progress.is_finished)
        self.assertFalse(admin.teams[1].advent_progress.is_finished)

        public = get_public_state(now=resumed_at + timedelta(seconds=2))
        self.assertEqual(public.first_finisher_team_id, "a")
        self.assertEqual([team.team_id for team in public.teams], ["a", "b"])
        public_data = asdict(public)
        self.assertEqual(
            set(public_data),
            {
                "global_state",
                "music",
                "challenge",
                "teams",
                "first_finisher_team_id",
                "gameplay_elapsed_ms",
            },
        )
        self.assertEqual(set(public_data["teams"][0]), {"team_id", "advent_progress"})
        self.assertEqual(
            set(public_data["teams"][0]["advent_progress"]),
            {"doors", "completed_count", "current_number", "is_finished"},
        )
        serialized = repr(public_data).lower()
        for private_name in (
            "points",
            "hint",
            "fragment",
            "reverse",
            "freeze",
            "question_id",
            "answer",
        ):
            self.assertNotIn(private_name, serialized)

    def test_finished_team_cannot_mutate_or_target_the_other_team(self):
        """Every player action rejects after canonical puzzle-25 completion."""
        resumed_at = self.reach_music_and_resume()
        for number in range(14, 25):
            self.force("a", number, now=resumed_at)
        self.answer(self.a, "a", 25, now=resumed_at + timedelta(seconds=1))

        before_a = TeamRun.objects.get(run_id=self.run_id, team_id="a")
        before_b = TeamRun.objects.get(run_id=self.run_id, team_id="b")
        before_audit_count = AuditEvent.objects.filter(run_id=self.run_id).count()

        commands = (
            lambda: submit_answer(
                self.a,
                SubmitAnswer(str(uuid4()), self.run_id, "a-25", "carol"),
                now=resumed_at + timedelta(seconds=2),
            ),
            lambda: purchase_hint(
                self.a,
                RunCommand(str(uuid4()), self.run_id),
                now=resumed_at + timedelta(seconds=2),
            ),
            lambda: use_hint(
                self.a,
                TeamPuzzle(str(uuid4()), self.run_id, "a-25"),
                now=resumed_at + timedelta(seconds=2),
            ),
            lambda: skip_current(
                self.a,
                TeamPuzzle(str(uuid4()), self.run_id, "a-25"),
                now=resumed_at + timedelta(seconds=2),
            ),
            lambda: purchase_uno_reverse(
                self.a,
                RunCommand(str(uuid4()), self.run_id),
                now=resumed_at + timedelta(seconds=2),
            ),
            lambda: freeze_opponent(
                self.a,
                RunCommand(str(uuid4()), self.run_id),
                now=resumed_at + timedelta(seconds=2),
            ),
            lambda: freeze_opponent(
                self.b,
                RunCommand(str(uuid4()), self.run_id),
                now=resumed_at + timedelta(seconds=2),
            ),
        )
        for command in commands:
            with self.assertRaisesRegex(ApplicationError, "disallowed_state"):
                command()

        after_a = TeamRun.objects.get(run_id=self.run_id, team_id="a")
        after_b = TeamRun.objects.get(run_id=self.run_id, team_id="b")
        self.assertEqual(after_a.activity_state, "FINISHED")
        self.assertEqual(after_a.points, before_a.points)
        self.assertEqual(after_a.hint_tokens, before_a.hint_tokens)
        self.assertEqual(after_a.reverse_active, before_a.reverse_active)
        self.assertEqual(after_b.activity_state, before_b.activity_state)
        self.assertEqual(after_b.points, before_b.points)
        self.assertEqual(
            AuditEvent.objects.filter(run_id=self.run_id).count(),
            before_audit_count,
        )


class PhaseFiveApplicationRaceTests(TransactionTestCase):
    def setUp(self):
        if (
            not os.environ.get("TEST_DATABASE_PATH")
            or os.environ["TEST_DATABASE_PATH"] == ":memory:"
        ):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        settings = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        settings.enable()
        self.addCleanup(settings.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("phase5-app-race-admin")
        self.actors = {}
        for team_id in ("a", "b"):
            user = users.objects.create_user(f"phase5-app-race-{team_id}")
            AccountRole.objects.create(user=user, role="team", team_id=team_id)
            self.actors[team_id] = Actor(user.pk, "team", team_id)
        AccountRole.objects.create(user=admin_user, role="admin")
        self.run_id = start_game(
            Actor(admin_user.pk, "admin"),
            StartGame(str(uuid4()), "christmas-2026-demo"),
            now=NOW,
        ).run_id
        PuzzleProgress.objects.filter(run_id=self.run_id, number__lt=25).update(
            completed=True, reward_awarded=True, completion_route="admin_force"
        )
        TeamRun.objects.filter(run_id=self.run_id).update(current_number=25)

    def compete(self, first_team):
        second_team = "b" if first_team == "a" else "a"
        requests = {"a": str(uuid4()), "b": str(uuid4())}
        attempted = Event()

        def finish(team_id):
            return submit_answer(
                self.actors[team_id],
                SubmitAnswer(
                    requests[team_id],
                    self.run_id,
                    f"{team_id}-25",
                    ADVENT_ANSWERS[team_id][24],
                ),
                now=NOW + timedelta(seconds=10),
            )

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
                return finish(second_team)
            finally:
                connection.connection.set_trace_callback(None)
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with immediate_transaction():
                first = finish(first_team)
                future = pool.submit(contender)
                self.assertTrue(attempted.wait(2))
                self.assertFalse(future.done())
            second = future.result(timeout=8)

        self.assertEqual(first.outcome, "completed")
        self.assertEqual(second.outcome, "completed")
        self.assertEqual(first.state.global_state, "ADVENT_QUIZ")
        self.assertEqual(second.state.global_state, "FINISHED")
        self.assertEqual(
            FirstFinisher.objects.get(run_id=self.run_id).team_id,
            first_team,
        )
        self.assertEqual(
            TeamRun.objects.filter(
                run_id=self.run_id, activity_state="FINISHED"
            ).count(),
            2,
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                run_id=self.run_id, action="first_finisher"
            ).count(),
            1,
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                run_id=self.run_id, action="game_finished"
            ).count(),
            1,
        )

    def test_a_commits_first(self):
        self.compete("a")

    def test_b_commits_first(self):
        self.compete("b")
