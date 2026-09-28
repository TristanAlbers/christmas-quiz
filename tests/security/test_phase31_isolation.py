"""Phase 3.1 READY and package-discovery privacy boundaries."""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from quiz.application import get_admin_state, reset_game, start_game
from quiz.configuration import discover_packages
from quiz.contracts import Actor, RunCommand, StartGame
from quiz.models import AccountRole, Run


class Phase31IsolationTests(TestCase):
    def setUp(self):
        users = get_user_model()
        self.admin_user = users.objects.create_user("phase31-security-admin")
        self.team_user = users.objects.create_user("phase31-security-a")
        self.other_user = users.objects.create_user("phase31-security-b")
        AccountRole.objects.create(user=self.admin_user, role="admin")
        AccountRole.objects.create(user=self.team_user, role="team", team_id="a")
        AccountRole.objects.create(user=self.other_user, role="team", team_id="b")
        self.admin = Actor(self.admin_user.pk, "admin")
        self.snapshots = TemporaryDirectory()
        self.addCleanup(self.snapshots.cleanup)
        scope = override_settings(QUIZ_SNAPSHOT_ROOT=Path(self.snapshots.name))
        scope.enable()
        self.addCleanup(scope.disable)

    def test_ready_team_endpoints_do_not_disclose_package_or_prior_run_data(self):
        run_id = start_game(
            self.admin, StartGame(str(uuid4()), "christmas-2026-demo")
        ).run_id
        reset_game(self.admin, RunCommand(str(uuid4()), run_id))

        self.client.force_login(self.team_user)
        page = self.client.get(reverse("team"))
        poll = self.client.get(reverse("team_state"))
        for response in (page, poll):
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Wachten tot de Game Master het spel start.")
            self.assertNotContains(response, "Demo A1: Poolster")
            self.assertNotContains(response, "christmas-2026-demo")
            self.assertNotContains(response, "points")
            self.assertNotContains(response, "/media/")

    def test_package_discovery_is_admin_only_and_creates_no_snapshot(self):
        games = TemporaryDirectory()
        self.addCleanup(games.cleanup)
        root = Path(games.name)
        valid = root / "valid-package"
        invalid = root / "invalid-package"
        valid.mkdir()
        invalid.mkdir()
        config = {
            "schema_version": 3,
            "package_id": "valid-package",
            "initial_points": 0,
            "hint_cost": 1,
            "skip_cost": 2,
            "freeze_cost": 3,
            "uno_reverse_cost": 4,
            "teams": {
                team: {
                    "puzzles": [
                        {
                            "id": f"{team}-1",
                            "number": 1,
                            "title": "One",
                            "body": "Body",
                            "validator": {"type": "text_exact", "answer": "one"},
                            "reward_points": 1,
                            "hint": None,
                            "fragment": None,
                            "media": [],
                        },
                        {
                            "id": f"{team}-2",
                            "number": 2,
                            "title": "Two",
                            "body": "Body",
                            "validator": {"type": "text_exact", "answer": "two"},
                            "reward_points": 1,
                            "hint": None,
                            "fragment": None,
                            "media": [],
                        },
                    ]
                }
                for team in ("a", "b")
            },
        }
        (valid / "game.json").write_text(json.dumps(config))
        (invalid / "game.json").write_text("not json")
        scope = override_settings(QUIZ_GAMES_ROOT=root)
        scope.enable()
        self.addCleanup(scope.disable)

        packages = discover_packages()
        self.assertEqual(
            [(item.package_id, item.startable) for item in packages],
            [("invalid-package", False), ("valid-package", True)],
        )
        self.assertTrue(packages[0].diagnostic)
        self.assertEqual(list(Path(self.snapshots.name).iterdir()), [])
        self.assertFalse(Run.objects.exists())

        self.client.force_login(self.team_user)
        self.assertEqual(self.client.get(reverse("admin_game")).status_code, 403)
        self.assertNotContains(self.client.get(reverse("team")), "invalid-package")
        self.client.force_login(self.admin_user)
        page = self.client.get(reverse("admin_game"))
        self.assertContains(page, "valid-package")
        self.assertContains(page, "invalid-package")
        self.assertContains(page, packages[0].diagnostic)
        self.assertEqual(list(Path(self.snapshots.name).iterdir()), [])

    def test_invalid_package_cannot_be_started_even_if_team_forges_the_post(self):
        self.client.force_login(self.team_user)
        response = self.client.post(
            reverse("admin_start"),
            {"request_id": str(uuid4()), "package_id": "not-a-package"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(Run.objects.filter(active=True).exists())

        state = get_admin_state(self.admin)
        self.assertEqual(state.global_state, "READY")
