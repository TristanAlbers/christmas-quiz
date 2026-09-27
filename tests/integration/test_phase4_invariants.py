"""Independent cross-cutting invariant checks for phase 4 Music Quiz behavior.

These tests intentionally exercise public application boundaries across domain,
persistence, lifecycle, snapshot, and idempotency concerns. They complement the
focused phase-4 domain/storage/application suites rather than duplicating them.
"""

import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.db import connections
from django.template.loader import render_to_string
from django.test import TransactionTestCase, override_settings

from quiz.application import (
    force_complete_current,
    get_public_state,
    get_team_state,
    purchase_hint,
    reset_game,
    skip_current,
    start_game,
    submit_answer,
    submit_music_answer,
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
    AuditEvent,
    CommandReceipt,
    FragmentAward,
    MusicAttempt,
    MusicQuestionResult,
    MusicQuiz,
    MusicScore,
    PuzzleProgress,
    Run,
    TeamRun,
)

NOW = datetime(2026, 12, 24, 18, 0, tzinfo=timezone.utc)


class PhaseFourIndependentInvariantTests(TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        scope = override_settings(
            QUIZ_SNAPSHOT_ROOT=Path(self.temp.name) / "snapshots"
        )
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        admin_user = users.objects.create_user("phase4-invariant-admin")
        team_a_user = users.objects.create_user("phase4-invariant-a")
        team_b_user = users.objects.create_user("phase4-invariant-b")
        AccountRole.objects.create(user=admin_user, role="admin")
        AccountRole.objects.create(user=team_a_user, role="team", team_id="a")
        AccountRole.objects.create(user=team_b_user, role="team", team_id="b")
        self.admin = Actor(admin_user.pk, "admin")
        self.a = Actor(team_a_user.pk, "team", "a")
        self.b = Actor(team_b_user.pk, "team", "b")
        self.run_id = self._start()

    def _start(self, package_id="christmas-2026-demo"):
        return start_game(
            self.admin,
            StartGame(str(uuid4()), package_id),
            now=NOW,
        ).run_id

    def _force_through(self, number, *, now=NOW):
        for puzzle_number in range(1, number + 1):
            force_complete_current(
                self.admin,
                AdminPuzzle(
                    str(uuid4()),
                    self.run_id,
                    "a",
                    f"a-{puzzle_number}",
                ),
                now=now,
            )

    def _trigger_music(self, *, now=NOW):
        self._force_through(13, now=now)
        self.assertEqual(Run.objects.get(pk=self.run_id).global_state, "MUSIC_QUIZ")
        self.assertEqual(MusicQuiz.objects.filter(run_id=self.run_id).count(), 1)

    def assert_error(self, code, call, *args, **kwargs):
        with self.assertRaises(ApplicationError) as caught:
            call(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_music_trigger_failure_rolls_back_every_side_effect(self):
        self._force_through(12)
        team_before = TeamRun.objects.get(run_id=self.run_id, team_id="a")
        before = {
            "points": team_before.points,
            "events": AuditEvent.objects.filter(run_id=self.run_id).count(),
            "receipts": CommandReceipt.objects.filter(run_id=self.run_id).count(),
            "fragments": FragmentAward.objects.filter(run_id=self.run_id).count(),
        }
        request_id = str(uuid4())

        with patch(
            "quiz.application.MusicQuiz.objects.create",
            side_effect=RuntimeError("injected trigger failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "injected trigger failure"):
                force_complete_current(
                    self.admin,
                    AdminPuzzle(request_id, self.run_id, "a", "a-13"),
                    now=NOW + timedelta(seconds=1),
                )

        run = Run.objects.get(pk=self.run_id)
        team = TeamRun.objects.get(run_id=self.run_id, team_id="a")
        progress = PuzzleProgress.objects.get(
            run_id=self.run_id, team_id="a", number=13
        )
        self.assertEqual(run.global_state, "ADVENT_QUIZ")
        self.assertFalse(progress.completed)
        self.assertFalse(progress.reward_awarded)
        self.assertEqual(team.current_number, 13)
        self.assertEqual(team.points, before["points"])
        self.assertFalse(MusicQuiz.objects.filter(run_id=self.run_id).exists())
        self.assertEqual(
            AuditEvent.objects.filter(run_id=self.run_id).count(), before["events"]
        )
        self.assertEqual(
            CommandReceipt.objects.filter(run_id=self.run_id).count(),
            before["receipts"],
        )
        self.assertEqual(
            FragmentAward.objects.filter(run_id=self.run_id).count(),
            before["fragments"],
        )

    def test_winning_answer_retry_is_idempotent_and_conflict_rejects(self):
        self._trigger_music(now=NOW + timedelta(seconds=1))
        before_points = TeamRun.objects.get(run_id=self.run_id, team_id="b").points
        request_id = str(uuid4())
        command = SubmitMusicAnswer(
            request_id,
            self.run_id,
            "music-1",
            "jingle bells",
        )

        first = submit_music_answer(self.b, command, now=NOW + timedelta(seconds=61))
        retry = submit_music_answer(self.b, command, now=NOW + timedelta(seconds=80))
        self.assertEqual(first.outcome, "won")
        self.assertEqual(retry.outcome, first.outcome)
        self.assertEqual(first.state.music.question_id, "music-2")
        self.assertEqual(retry.state.music.question_id, "music-2")
        self.assertEqual(retry.state.music.scores, first.state.music.scores)
        self.assertEqual(
            MusicAttempt.objects.filter(
                run_id=self.run_id, request_id=request_id
            ).count(),
            1,
        )
        self.assertEqual(
            MusicQuestionResult.objects.filter(
                run_id=self.run_id, question_number=1
            ).count(),
            1,
        )
        self.assertEqual(
            MusicScore.objects.get(run_id=self.run_id, team_id="b").score,
            1,
        )
        self.assertEqual(
            TeamRun.objects.get(run_id=self.run_id, team_id="b").points,
            before_points + 2,
        )
        self.assertEqual(
            CommandReceipt.objects.filter(
                run_id=self.run_id, request_id=request_id
            ).count(),
            1,
        )
        self.assertEqual(
            AuditEvent.objects.filter(
                run_id=self.run_id,
                request_id=request_id,
                action="music_answer",
            ).count(),
            1,
        )

        self.assert_error(
            "request_conflict",
            submit_music_answer,
            self.b,
            SubmitMusicAnswer(request_id, self.run_id, "music-1", "wrong"),
            now=NOW + timedelta(seconds=21),
        )
        self.assertEqual(
            TeamRun.objects.get(run_id=self.run_id, team_id="b").points,
            before_points + 2,
        )
        self.assertEqual(
            MusicQuestionResult.objects.filter(run_id=self.run_id).count(), 1
        )

    def test_music_blocks_advent_completion_routes_without_mutation(self):
        self._trigger_music(now=NOW + timedelta(seconds=1))
        before_b = TeamRun.objects.get(run_id=self.run_id, team_id="b")
        before = (
            before_b.points,
            before_b.current_number,
            PuzzleProgress.objects.filter(
                run_id=self.run_id, team_id="b", completed=True
            ).count(),
            CommandReceipt.objects.filter(run_id=self.run_id).count(),
            AuditEvent.objects.filter(run_id=self.run_id).count(),
        )

        state = get_team_state(self.b, now=NOW + timedelta(seconds=62))
        self.assertIsNone(state.question)
        self.assert_error(
            "disallowed_state",
            submit_answer,
            self.b,
            SubmitAnswer(str(uuid4()), self.run_id, "b-1", "anything"),
            now=NOW + timedelta(seconds=2),
        )
        self.assert_error(
            "disallowed_state",
            skip_current,
            self.b,
            TeamPuzzle(str(uuid4()), self.run_id, "b-1"),
            now=NOW + timedelta(seconds=2),
        )
        self.assert_error(
            "disallowed_state",
            force_complete_current,
            self.admin,
            AdminPuzzle(str(uuid4()), self.run_id, "b", "b-1"),
            now=NOW + timedelta(seconds=2),
        )

        self.assert_error(
            "disallowed_state",
            purchase_hint,
            self.b,
            RunCommand(str(uuid4()), self.run_id),
            now=NOW + timedelta(seconds=2),
        )

        after_b = TeamRun.objects.get(run_id=self.run_id, team_id="b")
        after = (
            after_b.points,
            after_b.current_number,
            PuzzleProgress.objects.filter(
                run_id=self.run_id, team_id="b", completed=True
            ).count(),
            CommandReceipt.objects.filter(run_id=self.run_id).count(),
            AuditEvent.objects.filter(run_id=self.run_id).count(),
        )
        self.assertEqual(after, before)

    def test_frozen_team_can_render_music_answer_controls(self):
        self._trigger_music(now=NOW + timedelta(seconds=1))
        TeamRun.objects.filter(run_id=self.run_id, team_id="b").update(
            activity_state="FREEZE", freeze_started_gameplay_ms=0
        )
        state = get_team_state(self.b, now=NOW + timedelta(seconds=62))

        html = render_to_string(
            "quiz/_question_pane.html",
            {"state": state, "music_request_id": str(uuid4())},
        )

        self.assertEqual(state.team_state, "FREEZE")
        self.assertIsNotNone(state.music)
        self.assertIn('id="music-answer-input"', html)
        self.assertIn('class="music-progress"', html)
        self.assertNotIn('class="freeze-surface"', html)

    def test_reset_during_music_archives_state_and_stales_old_answers(self):
        self._trigger_music(now=NOW + timedelta(seconds=1))
        quiz_id = MusicQuiz.objects.get(run_id=self.run_id).pk
        reset = reset_game(
            self.admin,
            RunCommand(str(uuid4()), self.run_id),
            now=NOW + timedelta(seconds=2),
        )
        self.assertEqual(reset.outcome, "reset")
        self.assertFalse(Run.objects.get(pk=self.run_id).active)
        self.assertTrue(
            MusicQuiz.objects.filter(pk=quiz_id, run_id=self.run_id).exists()
        )
        waiting = get_team_state(self.a, now=NOW + timedelta(seconds=3))
        self.assertEqual((waiting.run_id, waiting.global_state), (None, "READY"))
        self.assertIsNone(waiting.music)
        self.assertIsNone(get_public_state(now=NOW + timedelta(seconds=3)).music)
        self.assert_error(
            "stale_run",
            submit_music_answer,
            self.a,
            SubmitMusicAnswer(
                str(uuid4()), self.run_id, "music-1", "jingle bells"
            ),
            now=NOW + timedelta(seconds=3),
        )

    def test_active_music_uses_snapshot_after_source_package_is_deleted(self):
        games_root = Path(self.temp.name) / "games"
        source = games_root / "phase4-copy"
        shutil.copytree(Path("games/christmas-2026-demo"), source)
        config_path = source / "game.json"
        text = config_path.read_text().replace(
            '"package_id": "christmas-2026-demo"',
            '"package_id": "phase4-copy"',
            1,
        )
        config_path.write_text(text)

        reset_game(
            self.admin,
            RunCommand(str(uuid4()), self.run_id),
            now=NOW,
        )
        games_scope = override_settings(QUIZ_GAMES_ROOT=games_root)
        games_scope.enable()
        self.addCleanup(games_scope.disable)
        self.run_id = self._start("phase4-copy")
        self._trigger_music(now=NOW + timedelta(seconds=1))
        shutil.rmtree(source)
        connections["default"].close()

        recovered = get_team_state(self.a, now=NOW + timedelta(hours=1))
        self.assertEqual(recovered.global_state, "MUSIC_QUIZ")
        self.assertEqual(recovered.music.question_id, "music-1")
        won = submit_music_answer(
            self.a,
            SubmitMusicAnswer(
                str(uuid4()), self.run_id, "music-1", "jingle bells"
            ),
            now=NOW + timedelta(hours=1, seconds=1),
        )
        self.assertEqual(won.outcome, "won")
        self.assertEqual(won.state.music.question_id, "music-2")
