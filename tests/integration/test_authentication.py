"""Focused role mapping and credential provisioning checks."""

import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase

from quiz.auth import actor_for_user
from quiz.contracts import ApplicationError
from quiz.models import AccountRole

SECRETS = {
    "QUIZ_TEAM_A_PIN": "12345678",
    "QUIZ_TEAM_B_PIN": "87654321",
    "QUIZ_ADMIN_ONE_PASSWORD": "first-admin-secret",
    "QUIZ_ADMIN_TWO_PASSWORD": "second-admin-secret",
}


class AuthenticationTests(TestCase):
    def test_provisioning_creates_distinct_team_and_admin_roles(self):
        with patch.dict(os.environ, SECRETS):
            call_command("provision_accounts")
        User = get_user_model()
        team_a = User.objects.get(username="team-a")
        team_b = User.objects.get(username="team-b")
        admin_one = User.objects.get(username="admin-one")
        admin_two = User.objects.get(username="admin-two")
        self.assertEqual(actor_for_user(team_a).team_id, "a")
        self.assertEqual(actor_for_user(team_b).team_id, "b")
        self.assertEqual(actor_for_user(admin_one).role, "admin")
        self.assertEqual(actor_for_user(admin_two).role, "admin")
        self.assertTrue(team_a.check_password(SECRETS["QUIZ_TEAM_A_PIN"]))
        self.assertTrue(admin_one.check_password(SECRETS["QUIZ_ADMIN_ONE_PASSWORD"]))
        self.assertEqual(AccountRole.objects.count(), 4)
        self.assertFalse(team_a.is_staff)
        self.assertFalse(admin_one.is_superuser)

    def test_unmapped_or_inactive_user_cannot_gain_role(self):
        User = get_user_model()
        unmapped = User.objects.create_user("unmapped", password="secret")
        with self.assertRaises(ApplicationError) as error:
            actor_for_user(unmapped)
        self.assertEqual(error.exception.code, "forbidden")
        inactive = User.objects.create_user(
            "team-a", password="secret", is_active=False
        )
        AccountRole.objects.create(user=inactive, role="team", team_id="a")
        with self.assertRaises(ApplicationError) as error:
            actor_for_user(inactive)
        self.assertEqual(error.exception.code, "unauthenticated")

    def test_team_and_admin_login_are_separate_sessions(self):
        with patch.dict(os.environ, SECRETS):
            call_command("provision_accounts")
        rejected = self.client.post(
            "/login/", {"team": "a", "pin": SECRETS["QUIZ_ADMIN_ONE_PASSWORD"]}
        )
        self.assertEqual(rejected.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        accepted = self.client.post(
            "/login/", {"team": "a", "pin": SECRETS["QUIZ_TEAM_A_PIN"]}
        )
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(
            actor_for_user(
                get_user_model().objects.get(pk=self.client.session["_auth_user_id"])
            ).team_id,
            "a",
        )
        self.assertEqual(self.client.get("/logout/").status_code, 405)
        self.client.post("/logout/")
        self.assertNotIn("_auth_user_id", self.client.session)
        accepted = self.client.post(
            "/admin-login/",
            {"username": "admin-one", "password": SECRETS["QUIZ_ADMIN_ONE_PASSWORD"]},
        )
        self.assertEqual(accepted.status_code, 302)
        self.assertEqual(
            actor_for_user(
                get_user_model().objects.get(pk=self.client.session["_auth_user_id"])
            ).role,
            "admin",
        )
