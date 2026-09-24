"""End-to-end application invariant for the complete 11-question Music round."""

from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TransactionTestCase, override_settings

from quiz.application import (
    force_complete_current,
    get_public_state,
    get_team_state,
    start_game,
    submit_music_answer,
)
from quiz.contracts import Actor, AdminPuzzle, StartGame, SubmitMusicAnswer
from quiz.models import AccountRole, MusicQuestionResult, MusicScore, TeamRun


class PhaseFourFullMusicJourneyTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("phase4-journey-admin")
        a_user = users.objects.create_user("phase4-journey-a")
        b_user = users.objects.create_user("phase4-journey-b")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=a_user, role="team", team_id="a")
        AccountRole.objects.create(user=b_user, role="team", team_id="b")
        self.admin = Actor(admin_user.pk, "admin")
        self.a = Actor(a_user.pk, "team", "a")
        self.b = Actor(b_user.pk, "team", "b")
        self.run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id
        for number in range(1, 14):
            force_complete_current(
                self.admin,
                AdminPuzzle(str(uuid4()), self.run_id, "a", f"a-{number}"),
            )

    def test_all_eleven_questions_advance_once_and_accumulate_exact_scores_rewards(self):
        answers = (
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
        before_a = TeamRun.objects.get(run_id=self.run_id, team_id="a").points
        before_b = TeamRun.objects.get(run_id=self.run_id, team_id="b").points

        for number, answer in enumerate(answers, start=1):
            actor = self.a if number % 2 else self.b
            result = submit_music_answer(
                actor,
                SubmitMusicAnswer(
                    str(uuid4()), self.run_id, f"music-{number}", answer
                ),
            )
            self.assertEqual(result.outcome, "won")
            if number < 11:
                self.assertEqual(result.state.music.phase, "question")
                self.assertEqual(result.state.music.question_id, f"music-{number + 1}")
            else:
                self.assertEqual(result.state.music.phase, "final_results")
                self.assertIsNone(result.state.music.question_id)

        self.assertEqual(
            MusicQuestionResult.objects.filter(run_id=self.run_id).count(), 11
        )
        self.assertEqual(
            MusicScore.objects.get(run_id=self.run_id, team_id="a").score, 6
        )
        self.assertEqual(
            MusicScore.objects.get(run_id=self.run_id, team_id="b").score, 5
        )
        self.assertEqual(
            TeamRun.objects.get(run_id=self.run_id, team_id="a").points,
            before_a + 12,
        )
        self.assertEqual(
            TeamRun.objects.get(run_id=self.run_id, team_id="b").points,
            before_b + 10,
        )

        public = get_public_state()
        self.assertEqual(public.global_state, "MUSIC_QUIZ")
        self.assertEqual(public.music.phase, "final_results")
        self.assertEqual(
            [(item.team_id, item.score) for item in public.music.scores],
            [("a", 6), ("b", 5)],
        )
        self.assertEqual(get_team_state(self.a).music.phase, "final_results")
        self.assertEqual(get_team_state(self.b).music.phase, "final_results")
