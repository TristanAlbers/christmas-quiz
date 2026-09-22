"""Adversarial checks for normative security invariants in section 23."""

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
from quiz.contracts import Actor, ApplicationError, StartGame, SubmitAnswer
from quiz.models import AccountRole


class TeamIsolationTests(TestCase):
    def setUp(self):
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        root = Path(self.snapshots.name)
        games = root / "games"
        package = games / "christmas-2026-demo"
        shutil.copytree(settings.BASE_DIR / "games" / "christmas-2026-demo", package)
        future_image = package / "a" / "future.png"
        future_image.write_bytes((package / "a" / "star.png").read_bytes())
        config_file = package / "game.json"
        config = json.loads(config_file.read_text())
        config["teams"]["a"]["puzzles"][1]["media"] = ["a/future.png"]
        config_file.write_text(json.dumps(config))
        settings_scope = override_settings(
            QUIZ_GAMES_ROOT=games, QUIZ_SNAPSHOT_ROOT=root / "snapshots"
        )
        settings_scope.enable()
        self.addCleanup(settings_scope.disable)

        users = get_user_model()
        self.admin = users.objects.create_user("isolation-admin", password="admin-pin")
        self.a = users.objects.create_user("isolation-a", password="a-pin")
        self.b = users.objects.create_user("isolation-b", password="b-pin")
        AccountRole.objects.create(user=self.admin, role="admin")
        AccountRole.objects.create(user=self.a, role="team", team_id="a")
        AccountRole.objects.create(user=self.b, role="team", team_id="b")
        self.admin_actor = Actor(self.admin.pk, "admin")
        self.a_actor = Actor(self.a.pk, "team", "a")
        self.b_actor = Actor(self.b.pk, "team", "b")
        self.run_id = start_game(
            self.admin_actor, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id

    def test_forged_actor_and_client_team_parameter_cannot_access_b(self):
        forged = Actor(self.a.pk, "team", "b")
        with self.assertRaises(ApplicationError) as caught:
            get_team_state(forged)
        self.assertEqual(caught.exception.code, "forbidden")
        with self.assertRaises(ApplicationError) as caught:
            submit_answer(
                forged,
                SubmitAnswer(str(uuid4()), self.run_id, "b-1", "blue"),
            )
        self.assertEqual(caught.exception.code, "forbidden")

        self.client.force_login(self.a)
        response = self.client.get(reverse("team_state"), {"team_id": "b"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Demo B1")
        self.assertNotContains(response, "blue")
        self.assertContains(response, "Demo A1")

        response = self.client.post(
            reverse("team_answer"),
            {
                "request_id": str(uuid4()),
                "run_id": self.run_id,
                "question_id": "b-1",
                "answer": "blue",
                "team_id": "b",
            },
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(get_team_state(self.b_actor).current_number, 1)
        self.assertEqual(get_team_state(self.a_actor).current_number, 1)

    def test_private_media_existing_and_missing_opponent_paths_are_identical(self):
        self.client.force_login(self.a)
        own_url = reverse(
            "private_media",
            kwargs={
                "run_id": self.run_id,
                "team_id": "a",
                "asset_path": "a/star.png",
            },
        )
        own = self.client.get(own_url)
        self.assertEqual(own.status_code, 200)
        self.assertTrue(b"".join(own.streaming_content).startswith(b"\x89PNG"))

        def denied(path):
            url = reverse(
                "private_media",
                kwargs={
                    "run_id": self.run_id,
                    "team_id": "b",
                    "asset_path": path,
                },
            )
            return self.client.get(url)

        existing = denied("b/sky.png")
        missing = denied("b/does-not-exist.png")
        self.assertEqual(existing.status_code, 404)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(existing.content, missing.content)

        future_url = reverse(
            "private_media",
            kwargs={
                "run_id": self.run_id,
                "team_id": "a",
                "asset_path": "a/future.png",
            },
        )
        self.assertEqual(self.client.get(future_url).status_code, 404)
        submit_answer(
            self.a_actor,
            SubmitAnswer(str(uuid4()), self.run_id, "a-1", "red"),
        )
        self.assertEqual(self.client.get(future_url).status_code, 200)
        self.assertEqual(self.client.get(own_url).status_code, 404)

    def test_team_cannot_start_and_anonymous_cannot_read_team_projection(self):
        self.client.force_login(self.a)
        response = self.client.post(
            reverse("admin_start"),
            {"request_id": str(uuid4()), "package_id": "christmas-2026-demo"},
        )
        self.assertEqual(response.status_code, 403)
        self.client.logout()
        response = self.client.get(reverse("team_state"))
        self.assertIn(response.status_code, (302, 401, 403))
        self.assertNotIn(b"Demo A1", response.content)
