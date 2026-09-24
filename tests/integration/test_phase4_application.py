"""Focused application integration checks for the phase-4 Music boundary."""

import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from quiz.application import (
    admin_freeze,
    force_complete_current,
    get_public_state,
    get_team_state,
    pause_game,
    resume_game,
    skip_current,
    start_game,
    submit_answer,
    submit_music_answer,
)
from quiz.contracts import (
    Actor,
    AdminPuzzle,
    AdminTeam,
    ApplicationError,
    RunCommand,
    StartGame,
    SubmitAnswer,
    SubmitMusicAnswer,
    TeamPuzzle,
)
from quiz.models import (
    AccountRole,
    AuditEvent,
    MusicQuestionResult,
    MusicQuiz,
    MusicScore,
    Run,
    TeamRun,
)

NOW = datetime(2026, 12, 24, 18, 0, tzinfo=timezone.utc)


class PhaseFourApplicationTests(TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.settings = override_settings(
            QUIZ_SNAPSHOT_ROOT=Path(self.temp.name) / "snapshots"
        )
        self.settings.enable()
        self.addCleanup(self.settings.disable)
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_user("phase4-admin")
        self.a_user = user_model.objects.create_user("phase4-a")
        self.b_user = user_model.objects.create_user("phase4-b")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.a_user, role="team", team_id="a")
        AccountRole.objects.create(user=self.b_user, role="team", team_id="b")
        self.admin = Actor(self.admin_user.pk, "admin")
        self.a = Actor(self.a_user.pk, "team", "a")
        self.b = Actor(self.b_user.pk, "team", "b")
        result = start_game(
            self.admin,
            StartGame(str(uuid.uuid4()), "christmas-2026-demo"),
            now=NOW,
        )
        self.run_id = result.run_id

    def _force_through(self, number, *, now=NOW):
        for puzzle_number in range(1, number + 1):
            force_complete_current(
                self.admin,
                AdminPuzzle(
                    str(uuid.uuid4()),
                    self.run_id,
                    "a",
                    f"a-{puzzle_number}",
                ),
                now=now,
            )

    def _reach_thirteen(self):
        self._force_through(12)

    def test_correct_answer_triggers_once_and_music_answer_is_atomic(self):
        self._reach_thirteen()
        completed = submit_answer(
            self.a,
            SubmitAnswer(str(uuid.uuid4()), self.run_id, "a-13", "music"),
            now=NOW + timedelta(seconds=5),
        )
        self.assertEqual(completed.state.global_state, "MUSIC_QUIZ")
        self.assertEqual(completed.state.music.question_id, "music-1")
        self.assertEqual(MusicQuiz.objects.filter(run_id=self.run_id).count(), 1)
        self.assertEqual(
            AuditEvent.objects.filter(
                run_id=self.run_id, action="music_started"
            ).count(),
            1,
        )

        before = TeamRun.objects.get(run_id=self.run_id, team_id="b").points
        wrong = submit_music_answer(
            self.b,
            SubmitMusicAnswer(str(uuid.uuid4()), self.run_id, "music-1", "wrong"),
            now=NOW + timedelta(seconds=8),
        )
        self.assertEqual(wrong.outcome, "incorrect")
        won = submit_music_answer(
            self.b,
            SubmitMusicAnswer(
                str(uuid.uuid4()), self.run_id, "music-1", "jingle bells"
            ),
            now=NOW + timedelta(seconds=9),
        )
        self.assertEqual(won.outcome, "won")
        self.assertEqual(won.state.music.question_id, "music-2")
        self.assertEqual(
            MusicScore.objects.get(run_id=self.run_id, team_id="b").score, 1
        )
        self.assertEqual(
            TeamRun.objects.get(run_id=self.run_id, team_id="b").points, before + 2
        )
        self.assertEqual(
            MusicQuestionResult.objects.filter(run_id=self.run_id).count(), 1
        )
        with self.assertRaises(ApplicationError) as stale:
            submit_music_answer(
                self.a,
                SubmitMusicAnswer(
                    str(uuid.uuid4()), self.run_id, "music-1", "jingle bells"
                ),
                now=NOW + timedelta(seconds=10),
            )
        self.assertEqual(stale.exception.code, "stale_question")

    def test_skip_and_admin_completion_share_the_trigger(self):
        self._reach_thirteen()
        skip_current(
            self.a,
            TeamPuzzle(str(uuid.uuid4()), self.run_id, "a-13"),
            now=NOW + timedelta(seconds=2),
        )
        self.assertEqual(Run.objects.get(pk=self.run_id).global_state, "MUSIC_QUIZ")
        self.assertEqual(MusicQuiz.objects.filter(run_id=self.run_id).count(), 1)

        # A fresh run demonstrates the third route without a route-specific trigger.
        Run.objects.filter(pk=self.run_id).update(active=False, global_state="READY")
        result = start_game(
            self.admin,
            StartGame(str(uuid.uuid4()), "christmas-2026-demo"),
            now=NOW,
        )
        self.run_id = result.run_id
        self._reach_thirteen()
        force_complete_current(
            self.admin,
            AdminPuzzle(str(uuid.uuid4()), self.run_id, "a", "a-13"),
            now=NOW + timedelta(seconds=3),
        )
        self.assertEqual(Run.objects.get(pk=self.run_id).global_state, "MUSIC_QUIZ")
        self.assertEqual(MusicQuiz.objects.filter(run_id=self.run_id).count(), 1)

    def test_pause_and_final_results_restore_exact_underlying_freeze(self):
        self._reach_thirteen()
        admin_freeze(
            self.admin,
            AdminTeam(str(uuid.uuid4()), self.run_id, "b"),
            now=NOW + timedelta(seconds=10),
        )
        frozen_before = TeamRun.objects.get(run_id=self.run_id, team_id="b")
        freeze_start = frozen_before.freeze_started_gameplay_ms
        force_complete_current(
            self.admin,
            AdminPuzzle(str(uuid.uuid4()), self.run_id, "a", "a-13"),
            now=NOW + timedelta(seconds=20),
        )
        pause_game(
            self.admin,
            RunCommand(str(uuid.uuid4()), self.run_id),
            now=NOW + timedelta(seconds=30),
        )
        paused = Run.objects.get(pk=self.run_id)
        self.assertEqual(paused.pause_resume_target, "MUSIC_QUIZ")
        self.assertEqual(
            TeamRun.objects.get(
                run_id=self.run_id, team_id="b"
            ).freeze_started_gameplay_ms,
            freeze_start,
        )
        resume_game(
            self.admin,
            RunCommand(str(uuid.uuid4()), self.run_id),
            now=NOW + timedelta(minutes=5),
        )
        self.assertEqual(Run.objects.get(pk=self.run_id).global_state, "MUSIC_QUIZ")

        answer_time = NOW + timedelta(minutes=5, seconds=1)
        answers = [
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
        ]
        for number, answer in enumerate(answers, 1):
            submit_music_answer(
                self.a,
                SubmitMusicAnswer(
                    str(uuid.uuid4()), self.run_id, f"music-{number}", answer
                ),
                now=answer_time + timedelta(seconds=number),
            )
        final_time = answer_time + timedelta(seconds=11)
        self.assertEqual(
            get_team_state(self.a, now=final_time).music.phase, "final_results"
        )
        restored = get_team_state(
            self.b,
            now=final_time + timedelta(seconds=61),
        )
        self.assertEqual(restored.global_state, "ADVENT_QUIZ")
        self.assertIsNone(restored.music)
        self.assertEqual(restored.team_state, "FREEZE")
        self.assertLess(restored.freeze_remaining_ms, 300_000)
        public = get_public_state(now=final_time + timedelta(seconds=61))
        self.assertEqual(public.global_state, "ADVENT_QUIZ")
        self.assertIsNone(public.music)
