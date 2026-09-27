"""Issue #45: player Skip must never complete puzzle 25."""

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from quiz.application import get_team_state, skip_current, start_game
from quiz.contracts import Actor, ApplicationError, StartGame, TeamPuzzle
from quiz.models import (
    AccountRole,
    AuditEvent,
    FirstFinisher,
    FragmentAward,
    PuzzleProgress,
    Run,
    TeamRun,
)


class FinalPuzzleSkipTests(TestCase):
    def setUp(self):
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        settings = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        settings.enable()
        self.addCleanup(settings.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("issue45-admin")
        team_user = users.objects.create_user("issue45-team-a")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=team_user, role="team", team_id="a")
        self.admin = Actor(admin_user.pk, "admin")
        self.team = Actor(team_user.pk, "team", "a")
        self.run_id = start_game(
            self.admin,
            StartGame(str(uuid4()), "christmas-2026-demo"),
        ).run_id

    def _put_team_on(self, number):
        PuzzleProgress.objects.filter(
            run_id=self.run_id,
            team_id="a",
            number__lt=number,
        ).update(completed=True, reward_awarded=True, completion_route="admin_force")
        TeamRun.objects.filter(run_id=self.run_id, team_id="a").update(
            current_number=number,
            points=20,
            activity_state="PUZZLE",
        )

    def test_puzzle_24_skip_still_works_then_stale_and_direct_final_skips_are_atomic(self):
        self._put_team_on(24)

        result = skip_current(
            self.team,
            TeamPuzzle(str(uuid4()), self.run_id, "a-24"),
        )
        self.assertEqual(result.outcome, "completed")
        state = get_team_state(self.team)
        self.assertEqual(state.current_number, 25)
        self.assertEqual(state.question.id, "a-25")

        before_points = state.points
        before_audits = AuditEvent.objects.filter(run_id=self.run_id).count()
        before_fragments = FragmentAward.objects.filter(run_id=self.run_id).count()

        with self.assertRaises(ApplicationError) as stale:
            skip_current(
                self.team,
                TeamPuzzle(str(uuid4()), self.run_id, "a-24"),
            )
        self.assertEqual(stale.exception.code, "stale_question")

        with self.assertRaises(ApplicationError) as direct:
            skip_current(
                self.team,
                TeamPuzzle(str(uuid4()), self.run_id, "a-25"),
            )
        self.assertEqual(direct.exception.code, "disallowed_state")

        after = get_team_state(self.team)
        self.assertEqual(after.current_number, 25)
        self.assertEqual(after.points, before_points)
        final_progress = PuzzleProgress.objects.get(
            run_id=self.run_id,
            team_id="a",
            number=25,
        )
        self.assertFalse(final_progress.completed)
        self.assertFalse(final_progress.reward_awarded)
        self.assertEqual(
            AuditEvent.objects.filter(run_id=self.run_id).count(),
            before_audits,
        )
        self.assertEqual(
            FragmentAward.objects.filter(run_id=self.run_id).count(),
            before_fragments,
        )
        self.assertFalse(FirstFinisher.objects.filter(run_id=self.run_id).exists())
        self.assertEqual(Run.objects.get(pk=self.run_id).global_state, "ADVENT_QUIZ")

    def test_reopened_style_final_progress_is_still_not_skippable(self):
        self._put_team_on(25)
        PuzzleProgress.objects.filter(
            run_id=self.run_id,
            team_id="a",
            number=25,
        ).update(reward_awarded=True, completion_route="admin_force")
        before = get_team_state(self.team)

        with self.assertRaises(ApplicationError) as rejected:
            skip_current(
                self.team,
                TeamPuzzle(str(uuid4()), self.run_id, "a-25"),
            )
        self.assertEqual(rejected.exception.code, "disallowed_state")

        after = get_team_state(self.team)
        self.assertEqual(after.points, before.points)
        self.assertEqual(after.current_number, 25)
        self.assertFalse(
            PuzzleProgress.objects.get(
                run_id=self.run_id,
                team_id="a",
                number=25,
            ).completed
        )
