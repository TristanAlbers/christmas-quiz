"""Adversarial isolation checks for issue #39 private puzzle audio."""

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from quiz.application import get_team_state, start_game, submit_answer
from quiz.contracts import Actor, StartGame, SubmitAnswer
from quiz.models import AccountRole


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
        state = get_team_state(self.a_actor)
        self.assertEqual(
            [item.type for item in state.question.media],
            ["image", "audio"],
        )
        self.assertEqual(state.question.media[0].alt, "Rode ster")
        self.assertIn("a/clue.mp3", state.question.media[1].url)

        legacy = get_team_state(self.b_actor)
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
