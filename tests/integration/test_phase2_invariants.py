"""Phase 2 application invariants, including real SQLite writer contention.

The contention checks need TEST_DATABASE_PATH set to a disposable file path.
They use separate connections and deliberately hold the first writer slot.
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connections
from django.test import TestCase, TransactionTestCase, override_settings

from quiz.application import (
    adjust_points,
    force_complete_current,
    get_team_state,
    pause_game,
    provide_hint,
    purchase_hint,
    reset_game,
    resume_game,
    skip_current,
    start_game,
    submit_answer,
    use_hint,
)
from quiz.contracts import (
    Actor,
    AdminPoints,
    AdminPuzzle,
    ApplicationError,
    RunCommand,
    StartGame,
    SubmitAnswer,
    TeamPuzzle,
)
from quiz.models import (
    AccountRole,
    Attempt,
    AuditEvent,
    CommandReceipt,
    FragmentAward,
    HintReveal,
    PuzzleProgress,
    Run,
    TeamRun,
)
from quiz.persistence import immediate_transaction


class PhaseTwoSetup:
    def setUp(self):
        super().setUp()
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)
        users = get_user_model()
        admin = users.objects.create_user("phase2-admin-one", password="pin")
        admin2 = users.objects.create_user("phase2-admin-two", password="pin")
        team_a = users.objects.create_user("phase2-team-a", password="pin")
        team_b = users.objects.create_user("phase2-team-b", password="pin")
        for user in (admin, admin2):
            AccountRole.objects.create(user=user, role="admin")
        AccountRole.objects.create(user=team_a, role="team", team_id="a")
        AccountRole.objects.create(user=team_b, role="team", team_id="b")
        self.admin = Actor(admin.pk, "admin")
        self.admin2 = Actor(admin2.pk, "admin")
        self.a = Actor(team_a.pk, "team", "a")
        self.b = Actor(team_b.pk, "team", "b")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id

    def command(self):
        return RunCommand(str(uuid4()), self.run_id)

    def points(self, delta, *, team="a"):
        return adjust_points(
            self.admin, AdminPoints(str(uuid4()), self.run_id, team, delta)
        )

    def assert_error(self, code, call, *args):
        with self.assertRaises(ApplicationError) as caught:
            call(*args)
        self.assertEqual(caught.exception.code, code)


class PhaseTwoJourneyTests(PhaseTwoSetup, TestCase):
    def test_pause_preserves_team_state_and_blocks_gameplay(self):
        before_a = get_team_state(self.a)
        before_b = get_team_state(self.b)
        paused = pause_game(self.admin, self.command())
        self.assertEqual(paused.global_state, "PAUSED")
        self.assertEqual(get_team_state(self.a).team_state, before_a.team_state)
        self.assertEqual(get_team_state(self.b).team_state, before_b.team_state)
        self.assertIsNone(get_team_state(self.a).question)
        self.assert_error("disallowed_state", purchase_hint, self.a, self.command())
        self.assert_error(
            "disallowed_state",
            skip_current,
            self.a,
            TeamPuzzle(str(uuid4()), self.run_id, "a-1"),
        )
        self.assert_error(
            "disallowed_state",
            submit_answer,
            self.a,
            SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red"),
        )
        self.assert_error(
            "disallowed_state",
            provide_hint,
            self.admin,
            AdminPuzzle(str(uuid4()), self.run_id, "a", "a-1"),
        )
        self.points(-1)
        self.assertEqual(get_team_state(self.a).points, before_a.points - 1)
        resumed = resume_game(self.admin, self.command())
        self.assertEqual(resumed.global_state, "ADVENT_QUIZ")
        self.assertEqual(get_team_state(self.a).team_state, before_a.team_state)
        self.assertEqual(get_team_state(self.b).team_state, before_b.team_state)
        self.assertEqual(get_team_state(self.a).question.id, "a-1")

    def test_hint_inventory_reveal_privacy_and_receipts(self):
        bought = RunCommand(str(uuid4()), self.run_id)
        result = purchase_hint(self.a, bought)
        self.assertEqual(purchase_hint(self.a, bought), result)
        self.assertEqual(get_team_state(self.a).hint_tokens, 1)
        reveal = TeamPuzzle(str(uuid4()), self.run_id, "a-1")
        first = use_hint(self.a, reveal)
        self.assertEqual(first.outcome, "revealed")
        self.assertEqual(use_hint(self.a, reveal), first)
        self.assertEqual(get_team_state(self.a).hint_tokens, 0)
        self.assertEqual(
            get_team_state(self.a).question.hint, "The colour starts with R."
        )
        self.assertIsNone(get_team_state(self.b).question.hint)
        repeat = use_hint(self.a, TeamPuzzle(str(uuid4()), self.run_id, "a-1"))
        self.assertEqual(repeat.outcome, "already_revealed")
        self.assertEqual(
            HintReveal.objects.filter(team_id="a", puzzle_id="a-1").count(), 1
        )
        self.assertEqual(
            list(
                AuditEvent.objects.filter(action="use_hint")
                .order_by("id")
                .values_list("result", flat=True)
            ),
            ["revealed", "already_revealed"],
        )
        self.assertEqual(CommandReceipt.objects.filter(action="use_hint").count(), 2)
        self.assertEqual(
            provide_hint(
                self.admin, AdminPuzzle(str(uuid4()), self.run_id, "a", "a-1")
            ).outcome,
            "already_revealed",
        )
        self.assertEqual(HintReveal.objects.count(), 1)

    def test_admin_reveal_does_not_consume_tokens_and_inventory_survives_progression(
        self,
    ):
        purchase_hint(self.a, self.command())
        provide_hint(self.admin, AdminPuzzle(str(uuid4()), self.run_id, "a", "a-1"))
        self.assertEqual(get_team_state(self.a).hint_tokens, 1)
        self.assertEqual(
            use_hint(self.a, TeamPuzzle(str(uuid4()), self.run_id, "a-1")).outcome,
            "already_revealed",
        )
        submit_answer(self.a, SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red"))
        self.assertEqual(get_team_state(self.a).hint_tokens, 1)
        self.assertIsNone(get_team_state(self.a).question.hint)
        self.assertEqual(HintReveal.objects.filter(team_id="a").count(), 1)

    def test_completion_routes_are_once_only_and_stale_questions_do_not_charge(self):
        # Distinct puzzles/teams exercise all three routes through the public API.
        answer = submit_answer(
            self.a, SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red")
        )
        self.assertEqual(answer.outcome, "completed")
        skip = TeamPuzzle(str(uuid4()), self.run_id, "a-2")
        self.assertEqual(skip_current(self.a, skip).outcome, "completed")
        self.assertEqual(skip_current(self.a, skip).outcome, "completed")
        self.assertEqual(
            force_complete_current(
                self.admin, AdminPuzzle(str(uuid4()), self.run_id, "b", "b-1")
            ).outcome,
            "completed",
        )
        self.assert_error(
            "stale_question",
            skip_current,
            self.a,
            TeamPuzzle(str(uuid4()), self.run_id, "a-2"),
        )
        self.assert_error(
            "stale_question",
            force_complete_current,
            self.admin,
            AdminPuzzle(str(uuid4()), self.run_id, "b", "b-1"),
        )
        self.assertEqual(FragmentAward.objects.filter(run_id=self.run_id).count(), 3)
        self.assertEqual(
            PuzzleProgress.objects.filter(run_id=self.run_id, completed=True).count(), 3
        )
        self.assertEqual(TeamRun.objects.get(run_id=self.run_id, team_id="a").points, 7)
        self.assertEqual(TeamRun.objects.get(run_id=self.run_id, team_id="b").points, 7)

    def test_rejections_roll_back_receipt_event_and_balances(self):
        self.points(-3)
        before = (CommandReceipt.objects.count(), AuditEvent.objects.count())
        self.assert_error("insufficient_points", purchase_hint, self.a, self.command())
        self.assert_error(
            "insufficient_points",
            skip_current,
            self.a,
            TeamPuzzle(str(uuid4()), self.run_id, "a-1"),
        )
        self.assert_error(
            "insufficient_points",
            adjust_points,
            self.admin,
            AdminPoints(str(uuid4()), self.run_id, "a", -1),
        )
        self.assertEqual(
            (CommandReceipt.objects.count(), AuditEvent.objects.count()), before
        )
        self.assertEqual(get_team_state(self.a).points, 0)
        self.assertFalse(
            PuzzleProgress.objects.get(
                run_id=self.run_id, team_id="a", number=1
            ).completed
        )

    def test_adjustment_audit_and_conflicting_receipt_payload(self):
        request_id = str(uuid4())
        command = AdminPoints(request_id, self.run_id, "a", 5)
        result = adjust_points(self.admin, command)
        self.assertEqual(adjust_points(self.admin, command), result)
        self.assertEqual(get_team_state(self.a).points, 8)
        event = AuditEvent.objects.get(action="adjust_points")
        self.assertEqual(event.changes["points"], {"previous": 3, "delta": 5, "new": 8})
        self.assertEqual(
            CommandReceipt.objects.filter(action="adjust_points").count(), 1
        )
        self.assert_error(
            "request_conflict",
            adjust_points,
            self.admin,
            AdminPoints(request_id, self.run_id, "a", 6),
        )
        self.assertEqual(get_team_state(self.a).points, 8)

    def test_reset_stales_old_commands_and_preserves_audit(self):
        purchase_hint(self.a, self.command())
        provide_hint(self.admin, AdminPuzzle(str(uuid4()), self.run_id, "a", "a-1"))
        old_events = tuple(
            AuditEvent.objects.filter(run_id=self.run_id).values_list("id", flat=True)
        )
        reset_command = self.command()
        result = reset_game(self.admin, reset_command)
        self.assertEqual(reset_game(self.admin, reset_command), result)
        self.assertEqual(result.run_id, self.run_id)
        self.assertEqual(result.global_state, "READY")
        self.assertEqual(Run.objects.filter(active=True).count(), 0)
        self.assertEqual(get_team_state(self.a).points, 0)
        self.assertEqual(get_team_state(self.a).hint_tokens, 0)
        self.assertIsNone(get_team_state(self.a).question)
        self.assertTrue(HintReveal.objects.filter(run_id=self.run_id).exists())
        self.assertTrue(
            set(old_events).issubset(
                set(AuditEvent.objects.values_list("id", flat=True))
            )
        )
        self.assertEqual(
            AuditEvent.objects.filter(run_id=self.run_id, action="reset").count(), 1
        )
        self.assert_error(
            "stale_run", purchase_hint, self.a, RunCommand(str(uuid4()), self.run_id)
        )
        self.assert_error(
            "stale_run",
            skip_current,
            self.a,
            TeamPuzzle(str(uuid4()), self.run_id, "a-1"),
        )
        self.assert_error(
            "stale_run",
            submit_answer,
            self.a,
            SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red"),
        )
        restarted = start_game(
            self.admin2, StartGame(str(uuid4()), "christmas-2026-demo")
        )
        self.assertNotEqual(restarted.run_id, result.run_id)
        self.assertEqual(get_team_state(self.a).question.id, "a-1")


class PhaseTwoContentionTests(PhaseTwoSetup, TransactionTestCase):
    def setUp(self):
        if (
            not os.environ.get("TEST_DATABASE_PATH")
            or os.environ["TEST_DATABASE_PATH"] == ":memory:"
        ):
            self.skipTest("requires disposable file-backed TEST_DATABASE_PATH")
        super().setUp()

    def compete(self, first, second):
        """Commit first writer only after second reaches BEGIN IMMEDIATE."""
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
                return second()
            except ApplicationError as error:
                return error
            finally:
                connection.connection.set_trace_callback(None)
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with immediate_transaction():
                first_result = first()
                future = pool.submit(contender)
                self.assertTrue(
                    attempted.wait(2), "contender did not reach SQLite writer slot"
                )
                self.assertFalse(
                    future.done(), "contender crossed the held writer slot"
                )
            second_result = future.result(timeout=8)
        return first_result, second_result

    def test_two_hint_purchases_cannot_overspend(self):
        self.points(-2)  # exactly one token affordable
        first, second = self.compete(
            lambda: purchase_hint(self.a, self.command()),
            lambda: purchase_hint(self.a, self.command()),
        )
        self.assertEqual(first.outcome, "purchased")
        self.assertIsInstance(second, ApplicationError)
        self.assertEqual(second.code, "insufficient_points")
        state = get_team_state(self.a)
        self.assertEqual((state.points, state.hint_tokens), (0, 1))
        self.assertEqual(AuditEvent.objects.filter(action="purchase_hint").count(), 1)
        self.assertEqual(
            CommandReceipt.objects.filter(action="purchase_hint").count(), 1
        )

    def test_hint_purchase_and_skip_serialize_against_same_balance(self):
        # With 2 points, Skip costs 2 and Hint costs 1. If Hint commits first,
        # a stale balance cannot allow the concurrent Skip to spend another 2.
        self.points(-1)
        first, second = self.compete(
            lambda: purchase_hint(self.a, self.command()),
            lambda: skip_current(self.a, TeamPuzzle(str(uuid4()), self.run_id, "a-1")),
        )
        self.assertEqual(first.outcome, "purchased")
        self.assertIsInstance(second, ApplicationError)
        self.assertEqual(second.code, "insufficient_points")
        self.assertEqual(
            (get_team_state(self.a).points, get_team_state(self.a).hint_tokens), (1, 1)
        )
        self.assertFalse(
            PuzzleProgress.objects.get(
                run_id=self.run_id, team_id="a", number=1
            ).completed
        )

    def test_two_admin_resets_leave_no_competing_active_runs(self):
        first, second = self.compete(
            lambda: reset_game(self.admin, self.command()),
            lambda: reset_game(self.admin2, self.command()),
        )
        self.assertEqual(first.outcome, "reset")
        self.assertIsInstance(second, ApplicationError)
        self.assertEqual(second.code, "stale_run")
        self.assertEqual(Run.objects.filter(active=True).count(), 0)
        self.assertEqual(first.run_id, self.run_id)
        self.assertEqual(AuditEvent.objects.filter(action="reset").count(), 1)
        self.assertEqual(CommandReceipt.objects.filter(action="reset").count(), 1)

    def test_start_waiting_for_reset_creates_a_fresh_run(self):
        first, second = self.compete(
            lambda: reset_game(self.admin, self.command()),
            lambda: start_game(
                self.admin2, StartGame(str(uuid4()), "christmas-2026-demo")
            ),
        )
        self.assertEqual(first.outcome, "reset")
        self.assertNotEqual(second.run_id, first.run_id)
        self.assertEqual(second.global_state, "ADVENT_QUIZ")
        self.assertEqual(Run.objects.filter(active=True).count(), 1)
        self.assertEqual(str(Run.objects.get(active=True).pk), second.run_id)
        self.assertEqual(get_team_state(self.a).question.id, "a-1")
        self.assertEqual(AuditEvent.objects.filter(action="reset").count(), 1)


class MusicBoundaryTests(TestCase):
    """Legacy snapshots cannot complete puzzle 13 without Phase-4 Music data."""

    def test_all_completion_routes_stop_at_puzzle_thirteen_atomically(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "games" / "thirteen-puzzles"
            package.mkdir(parents=True)

            def puzzles(team):
                return [
                    {
                        "id": f"{team}-{number}",
                        "number": number,
                        "title": f"Puzzle {number}",
                        "body": "Demo clue",
                        "validator": {"type": "text_exact", "answer": "red"},
                        "reward_points": 0,
                        "hint": "Demo hint",
                        "fragment": None,
                        "media": [],
                    }
                    for number in range(1, 14)
                ]

            (package / "game.json").write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "package_id": "thirteen-puzzles",
                        "initial_points": 30,
                        "hint_cost": 1,
                        "skip_cost": 1,
                        "teams": {
                            team: {"puzzles": puzzles(team)} for team in ("a", "b")
                        },
                    }
                )
            )
            with override_settings(
                QUIZ_GAMES_ROOT=root / "games",
                QUIZ_SNAPSHOT_ROOT=root / "snapshots",
            ):
                users = get_user_model()
                admin_user = users.objects.create_user("music-boundary-admin")
                team_user = users.objects.create_user("music-boundary-a")
                AccountRole.objects.create(user=admin_user, role="admin")
                AccountRole.objects.create(user=team_user, role="team", team_id="a")
                admin = Actor(admin_user.pk, "admin")
                team = Actor(team_user.pk, "team", "a")
                run_id = start_game(
                    admin, StartGame(str(uuid4()), "thirteen-puzzles")
                ).run_id
                for number in range(1, 13):
                    self.assertEqual(
                        skip_current(
                            team,
                            TeamPuzzle(str(uuid4()), run_id, f"a-{number}"),
                        ).outcome,
                        "completed",
                    )
                self.assertEqual(get_team_state(team).current_number, 13)
                before = (
                    get_team_state(team).points,
                    Attempt.objects.count(),
                    CommandReceipt.objects.count(),
                    AuditEvent.objects.count(),
                )
                for action, actor, command in (
                    (
                        submit_answer,
                        team,
                        SubmitAnswer(str(uuid4()), run_id, "a-13", "red"),
                    ),
                    (
                        skip_current,
                        team,
                        TeamPuzzle(str(uuid4()), run_id, "a-13"),
                    ),
                    (
                        force_complete_current,
                        admin,
                        AdminPuzzle(str(uuid4()), run_id, "a", "a-13"),
                    ),
                ):
                    with self.assertRaises(ApplicationError) as caught:
                        action(actor, command)
                    self.assertEqual(caught.exception.code, "disallowed_state")
                self.assertEqual(
                    (
                        get_team_state(team).points,
                        Attempt.objects.count(),
                        CommandReceipt.objects.count(),
                        AuditEvent.objects.count(),
                    ),
                    before,
                )
                self.assertFalse(
                    PuzzleProgress.objects.get(
                        run_id=run_id, team_id="a", number=13
                    ).completed
                )
