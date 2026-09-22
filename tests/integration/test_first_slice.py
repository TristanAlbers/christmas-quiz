"""The public application journey through the first two demo puzzles."""

import tempfile
import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from quiz.application import get_team_state, start_game, submit_answer
from quiz.contracts import Actor, StartGame, SubmitAnswer
from quiz.models import (
    AccountRole,
    AnswerReceipt,
    Attempt,
    AuditEvent,
    FragmentAward,
    PuzzleProgress,
    TeamRun,
)


class FirstSliceJourneyTests(TestCase):
    def setUp(self):
        self.snapshots = tempfile.TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        override = override_settings(QUIZ_SNAPSHOT_ROOT=self.snapshots.name)
        override.enable()
        self.addCleanup(override.disable)
        user_type = get_user_model()
        admin_user = user_type.objects.create_user("admin-one", password="secret")
        team_user = user_type.objects.create_user("team-a", password="pin")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=team_user, role="team", team_id="a")
        self.admin = Actor(admin_user.pk, "admin")
        self.team_a = Actor(team_user.pk, "team", "a")

    def test_start_wrong_correct_advance_and_reload(self):
        ready = get_team_state(self.team_a)
        self.assertEqual(ready.global_state, "READY")
        self.assertIsNone(ready.question)

        start_request = str(uuid.uuid4())
        run = start_game(self.admin, StartGame(start_request, "christmas-2026-demo"))
        self.assertEqual(run.global_state, "ADVENT_QUIZ")
        self.assertEqual(
            start_game(self.admin, StartGame(start_request, "christmas-2026-demo")),
            run,
        )
        first = get_team_state(self.team_a)
        self.assertEqual(first.question.id, "a-1")
        self.assertEqual(first.points, 3)
        self.assertNotIn("red", first.question.body.lower())

        wrong = submit_answer(
            self.team_a, SubmitAnswer(str(uuid.uuid4()), run.run_id, "a-1", "green")
        )
        self.assertEqual(wrong.outcome, "incorrect")
        self.assertEqual(wrong.state.question.id, "a-1")
        self.assertEqual(wrong.state.points, 3)
        self.assertEqual(Attempt.objects.filter(is_correct=False).count(), 1)
        self.assertFalse(PuzzleProgress.objects.get(team_id="a", number=1).completed)

        answer_request = str(uuid.uuid4())
        command = SubmitAnswer(answer_request, run.run_id, "a-1", " RED ")
        correct = submit_answer(self.team_a, command)
        self.assertEqual(correct.outcome, "completed")
        self.assertEqual(correct.state.question.id, "a-2")
        self.assertEqual(correct.state.points, 7)
        self.assertEqual(correct.state.fragments, ("DEMO-A-STAR",))
        self.assertEqual(submit_answer(self.team_a, command), correct)

        # A fresh state query reads committed database state, not in-process state.
        reloaded = get_team_state(self.team_a)
        self.assertEqual(reloaded, correct.state)
        self.assertEqual(TeamRun.objects.get(team_id="b").current_number, 1)
        self.assertEqual(AnswerReceipt.objects.count(), 2)
        self.assertEqual(Attempt.objects.count(), 2)
        self.assertEqual(FragmentAward.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.count(), 3)
        self.assertEqual(
            AuditEvent.objects.get(result="completed").changes["points"],
            {"previous": 3, "delta": 4, "new": 7},
        )
