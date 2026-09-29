"""Adversarial isolation checks for issue #39 private puzzle audio."""

import json
import shutil
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from quiz import _application_core as core
from quiz import phase6_application
from quiz.application import (
    force_complete_current,
    get_team_state,
    reset_game,
    start_game,
    submit_answer,
    submit_music_answer,
)
from quiz.contracts import (
    Actor,
    AdminPuzzle,
    PuzzleMediaProjection,
    RunCommand,
    StartGame,
    SubmitAnswer,
    SubmitMusicAnswer,
)
from quiz.models import AccountRole, Run

NOW = datetime(2026, 12, 24, 18, 0, tzinfo=timezone.utc)


class TypedPuzzleAudioIsolationTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        games = root / "games"
        package = games / "christmas-2026-demo"
        shutil.copytree(settings.BASE_DIR / "games" / "christmas-2026-demo", package)

        (package / "a" / "clue.mp3").write_bytes(b"ID3-team-a-current")
        (package / "a" / "future.mp3").write_bytes(b"ID3-team-a-future")
        (package / "b" / "clue.mp3").write_bytes(b"ID3-team-b-current")
        config_file = package / "game.json"
        config = json.loads(config_file.read_text())
        config["teams"]["a"]["puzzles"][0]["media"] = [
            {"type": "image", "path": "a/star.png", "alt": "Rode ster"},
            {"type": "audio", "path": "a/clue.mp3"},
        ]
        config["teams"]["a"]["puzzles"][1]["media"] = [
            {"type": "audio", "path": "a/future.mp3"}
        ]
        config["teams"]["a"]["puzzles"][13]["media"] = [
            {"type": "audio", "path": "a/future.mp3"}
        ]
        config["teams"]["b"]["puzzles"][0]["media"] = [
            "b/sky.png",
            {"type": "audio", "path": "b/clue.mp3"},
        ]
        config_file.write_text(json.dumps(config))

        scope = override_settings(
            QUIZ_GAMES_ROOT=games,
            QUIZ_SNAPSHOT_ROOT=root / "snapshots",
        )
        scope.enable()
        self.addCleanup(scope.disable)

        users = get_user_model()
        self.admin = users.objects.create_user("issue39-admin")
        self.team_a = users.objects.create_user("issue39-a")
        self.team_b = users.objects.create_user("issue39-b")
        AccountRole.objects.create(user=self.admin, role="admin")
        AccountRole.objects.create(user=self.team_a, role="team", team_id="a")
        AccountRole.objects.create(user=self.team_b, role="team", team_id="b")
        self.admin_actor = Actor(self.admin.pk, "admin")
        self.a_actor = Actor(self.team_a.pk, "team", "a")
        self.b_actor = Actor(self.team_b.pk, "team", "b")
        self.run_id = start_game(
            self.admin_actor,
            StartGame(str(uuid4()), "christmas-2026-demo"),
            now=NOW,
        ).run_id

    def _media_url(self, team_id, path):
        return reverse(
            "private_media",
            kwargs={
                "run_id": self.run_id,
                "team_id": team_id,
                "asset_path": path,
            },
        )

    def test_projection_exposes_type_without_weakening_current_question_boundary(self):
        state = get_team_state(self.a_actor, now=NOW)
        self.assertEqual(
            [item.type for item in state.question.media],
            ["image", "audio"],
        )
        self.assertEqual(state.question.media[0].alt, "Rode ster")
        self.assertIn("a/clue.mp3", state.question.media[1].url)

        legacy = get_team_state(self.b_actor, now=NOW)
        self.assertEqual(
            [item.type for item in legacy.question.media],
            ["image", "audio"],
        )
        self.assertIsNone(legacy.question.media[0].alt)
        self.assertIn("b/sky.png", legacy.question.media[0].url)

        self.client.force_login(self.team_a)
        current = self.client.get(self._media_url("a", "a/clue.mp3"))
        self.assertEqual(current.status_code, 200)
        self.assertEqual(b"".join(current.streaming_content), b"ID3-team-a-current")

        future_url = self._media_url("a", "a/future.mp3")
        self.assertEqual(self.client.get(future_url).status_code, 404)

        submit_answer(
            self.a_actor,
            SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red"),
            now=NOW + timedelta(seconds=1),
        )
        previous = self.client.get(self._media_url("a", "a/clue.mp3"))
        self.assertEqual(previous.status_code, 404)
        future = self.client.get(future_url)
        self.assertEqual(future.status_code, 200)
        self.assertEqual(b"".join(future.streaming_content), b"ID3-team-a-future")

    def test_cross_team_and_anonymous_audio_requests_are_hidden(self):
        self.client.force_login(self.team_a)
        existing = self.client.get(self._media_url("b", "b/clue.mp3"))
        missing = self.client.get(self._media_url("b", "b/missing.mp3"))
        self.assertEqual(existing.status_code, 404)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(existing.content, missing.content)

        self.client.logout()
        anonymous = self.client.get(self._media_url("a", "a/clue.mp3"))
        self.assertEqual(anonymous.status_code, 404)

    def test_audio_bytes_are_served_from_the_pinned_snapshot(self):
        source = (
            Path(settings.QUIZ_GAMES_ROOT)
            / "christmas-2026-demo"
            / "a"
            / "clue.mp3"
        )
        source.write_bytes(b"ID3-edited-after-start")

        self.client.force_login(self.team_a)
        response = self.client.get(self._media_url("a", "a/clue.mp3"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"ID3-team-a-current")

    def test_team_projection_verifies_snapshot_once_per_poll(self):
        original = phase6_application._CORE_LOAD_SNAPSHOT
        with patch.object(
            phase6_application,
            "_CORE_LOAD_SNAPSHOT",
            wraps=original,
        ) as load_snapshot:
            state = get_team_state(self.a_actor, now=NOW + timedelta(seconds=1))

        self.assertEqual(state.question.media[1].type, "audio")
        self.assertEqual(load_snapshot.call_count, 1)

    def test_answer_enrichment_does_not_reselect_a_different_active_run(self):
        current = get_team_state(self.a_actor, now=NOW)
        wrong_run = replace(current, run_id=str(uuid4()))

        with patch(
            "quiz.application.get_team_state",
            return_value=wrong_run,
        ) as reselect:
            result = submit_answer(
                self.a_actor,
                SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red"),
                now=NOW + timedelta(seconds=1),
            )

        reselect.assert_not_called()
        self.assertEqual(result.state.run_id, self.run_id)
        self.assertEqual(result.state.current_number, 2)

    def test_archived_answer_retry_restores_typed_next_puzzle_media(self):
        command = SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red")
        first = submit_answer(
            self.a_actor,
            command,
            now=NOW + timedelta(seconds=1),
        )
        self.assertEqual(first.outcome, "completed")
        self.assertEqual(first.state.current_number, 2)
        self.assertEqual([item.type for item in first.state.question.media], ["audio"])

        reset_game(
            self.admin_actor,
            RunCommand(str(uuid4()), self.run_id),
            now=NOW + timedelta(seconds=2),
        )
        self.assertFalse(Run.objects.get(pk=self.run_id).active)

        retry = submit_answer(
            self.a_actor,
            command,
            now=NOW + timedelta(seconds=3),
        )
        self.assertEqual(retry.outcome, "completed")
        self.assertEqual(retry.state.run_id, self.run_id)
        self.assertEqual(retry.state.current_number, 2)
        self.assertEqual([item.type for item in retry.state.question.media], ["audio"])
        self.assertIn("a/future.mp3", retry.state.question.media[0].url)

    def test_receipt_restore_rehydrates_typed_media_objects(self):
        state = get_team_state(self.a_actor, now=NOW)
        serialized = asdict(state)

        restored = core._restore_team_projection(serialized)

        self.assertIsInstance(restored.question.media, tuple)
        self.assertEqual(len(restored.question.media), 2)
        self.assertIsInstance(restored.question.media[0], PuzzleMediaProjection)
        self.assertEqual(restored.question.media[1].type, "audio")

    def test_final_music_answer_retry_keeps_typed_advent_media(self):
        trigger_time = NOW + timedelta(seconds=5)
        for number in range(1, 14):
            force_complete_current(
                self.admin_actor,
                AdminPuzzle(
                    str(uuid4()),
                    self.run_id,
                    "a",
                    f"a-{number}",
                ),
                now=trigger_time,
            )

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
        first_answer_time = trigger_time + timedelta(seconds=61)
        final_command = None
        final_time = None
        for number, answer in enumerate(answers, 1):
            command = SubmitMusicAnswer(
                str(uuid4()),
                self.run_id,
                f"music-{number}",
                answer,
            )
            answer_time = first_answer_time + timedelta(seconds=number)
            submit_music_answer(self.a_actor, command, now=answer_time)
            if number == 11:
                final_command = command
                final_time = answer_time

        expired_time = final_time + timedelta(seconds=120)
        retry = submit_music_answer(
            self.a_actor,
            final_command,
            now=expired_time,
        )
        self.assertEqual(retry.outcome, "won")
        self.assertEqual(retry.state.global_state, "ADVENT_QUIZ")
        self.assertEqual(retry.state.current_number, 14)
        self.assertEqual([item.type for item in retry.state.question.media], ["audio"])
        self.assertIn("a/future.mp3", retry.state.question.media[0].url)

        # Exact receipt retry projects the effective post-Music state without
        # persisting the timed transition. The media boundary must use that same
        # effective state or it will advertise an audio URL that always 404s.
        self.assertEqual(Run.objects.get(pk=self.run_id).global_state, "MUSIC_QUIZ")
        self.client.force_login(self.team_a)
        with patch("quiz.web.media_views.server_now", return_value=expired_time):
            response = self.client.get(retry.state.question.media[0].url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), b"ID3-team-a-future")
