"""Security checks for the centralized current-Music-audio boundary."""

import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from django.http import Http404
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone

from quiz.configuration import stage_snapshot
from quiz.models import MusicQuiz, Run
from quiz.web.music_media_views import current_music_audio


def _puzzle(team_id, number):
    return {
        "id": f"{team_id}-{number}",
        "number": number,
        "title": "Private puzzle",
        "body": "Private body",
        "validator": {"type": "text_exact", "answer": "private-answer"},
        "reward_points": 0,
        "hint": None,
        "fragment": None,
        "media": [],
    }


def _question(number, audio):
    question = {
        "id": f"music-{number}",
        "number": number,
        "title": f"Music {number}",
        "body": "Shared prompt",
        "validator": {"type": "text_exact", "answer": f"secret-{number}"},
    }
    if audio is not None:
        question["audio"] = audio
    return question


class PhaseFourMusicAudioSecurityTests(TestCase):
    def setUp(self):
        self.runtime = TemporaryDirectory()
        self.addCleanup(self.runtime.cleanup)
        root = Path(self.runtime.name)
        games = root / "games"
        package = games / "secure-music"
        (package / "music").mkdir(parents=True)
        (package / "music" / "current.mp3").write_bytes(b"current-audio")
        (package / "music" / "future.mp3").write_bytes(b"future-audio")
        questions = [
            _question(
                number,
                (
                    "music/current.mp3"
                    if number == 1
                    else "music/future.mp3"
                    if number < 11
                    else None
                ),
            )
            for number in range(1, 12)
        ]
        config = {
            "schema_version": 4,
            "package_id": "secure-music",
            "initial_points": 0,
            "hint_cost": 0,
            "skip_cost": 0,
            "freeze_cost": 0,
            "uno_reverse_cost": 0,
            "music_question_reward": 1,
            "music_score_display_duration_ms": 1000,
            "teams": {
                "a": {"puzzles": [_puzzle("a", 1), _puzzle("a", 2)]},
                "b": {"puzzles": [_puzzle("b", 1), _puzzle("b", 2)]},
            },
            "music_questions": questions,
        }
        (package / "game.json").write_text(json.dumps(config))
        self.settings_scope = override_settings(
            QUIZ_GAMES_ROOT=games,
            QUIZ_SNAPSHOT_ROOT=root / "snapshots",
        )
        self.settings_scope.enable()
        self.addCleanup(self.settings_scope.disable)
        staged = stage_snapshot("secure-music")
        self.run = Run.objects.create(
            global_state="MUSIC_QUIZ",
            package_id="secure-music",
            snapshot_path=staged.path,
            snapshot_digest=staged.digest,
        )
        self.music = MusicQuiz.objects.create(
            run=self.run,
            phase="question",
            current_question_number=1,
            current_question_started_ms=0,
            music_clock_anchor=timezone.now(),
        )
        self.factory = RequestFactory()

    def _content(self, response):
        return b"".join(response.streaming_content)

    def test_public_route_serves_current_audio_and_ignores_future_path_probes(self):
        request = self.factory.get(
            "/music/audio/?question=2&asset_path=music/future.mp3"
        )
        response = current_music_audio(request, self.run.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._content(response), b"current-audio")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertNotIn(b"future-audio", b"current-audio")

    def test_gathering_audio_uses_effective_clock_without_persisting_transition(self):
        request = self.factory.get("/music/audio/")
        MusicQuiz.objects.filter(pk=self.music.pk).update(
            phase="gathering",
            current_question_number=None,
            current_question_started_ms=None,
            music_elapsed_ms=0,
            music_clock_anchor=timezone.now() - timedelta(seconds=55),
        )
        with self.assertRaises(Http404):
            current_music_audio(request, self.run.pk)

        MusicQuiz.objects.filter(pk=self.music.pk).update(
            music_clock_anchor=timezone.now() - timedelta(seconds=75)
        )
        response = current_music_audio(request, self.run.pk)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._content(response), b"current-audio")
        self.music.refresh_from_db()
        self.assertEqual(self.music.phase, "gathering")
        self.assertIsNone(self.music.current_question_number)

    def test_paused_gathering_never_exposes_question_one_audio(self):
        Run.objects.filter(pk=self.run.pk).update(
            global_state="PAUSED", pause_resume_target="MUSIC_QUIZ"
        )
        MusicQuiz.objects.filter(pk=self.music.pk).update(
            phase="gathering",
            current_question_number=None,
            current_question_started_ms=None,
            music_elapsed_ms=59_999,
            music_clock_anchor=None,
        )
        with self.assertRaises(Http404):
            current_music_audio(self.factory.get("/music/audio/"), self.run.pk)

    def test_paused_completed_inactive_and_wrong_run_audio_are_not_shareable(self):
        request = self.factory.get("/music/audio/")
        cases = (
            (
                "paused",
                lambda: Run.objects.filter(pk=self.run.pk).update(
                    global_state="PAUSED", pause_resume_target="MUSIC_QUIZ"
                ),
            ),
            (
                "completed",
                lambda: (
                    Run.objects.filter(pk=self.run.pk).update(
                        global_state="ADVENT_QUIZ"
                    ),
                    MusicQuiz.objects.filter(pk=self.music.pk).update(
                        phase="completed",
                        current_question_number=None,
                        current_question_started_ms=None,
                        final_results_started_ms=0,
                        music_clock_anchor=None,
                    ),
                ),
            ),
            (
                "inactive",
                lambda: Run.objects.filter(pk=self.run.pk).update(active=False),
            ),
        )
        for label, mutate in cases:
            with self.subTest(label=label):
                Run.objects.filter(pk=self.run.pk).update(
                    active=True,
                    global_state="MUSIC_QUIZ",
                    pause_resume_target=None,
                )
                MusicQuiz.objects.filter(pk=self.music.pk).update(
                    phase="question",
                    current_question_number=1,
                    current_question_started_ms=0,
                    final_results_started_ms=None,
                    music_elapsed_ms=0,
                    music_clock_anchor=timezone.now(),
                )
                mutate()
                with self.assertRaises(Http404):
                    current_music_audio(request, self.run.pk)

        with self.assertRaises(Http404):
            current_music_audio(request, "00000000-0000-0000-0000-000000000000")

    def test_question_without_audio_is_not_a_broad_snapshot_file_route(self):
        self.music.current_question_number = 11
        self.music.save(update_fields=["current_question_number"])
        with self.assertRaises(Http404):
            current_music_audio(self.factory.get("/music/audio/"), self.run.pk)
