"""Create or rotate the two team and two named admin credentials."""

import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from quiz.models import AccountRole

ACCOUNTS = (
    ("team-a", "team", "a", "QUIZ_TEAM_A_PIN"),
    ("team-b", "team", "b", "QUIZ_TEAM_B_PIN"),
    ("admin-one", "admin", None, "QUIZ_ADMIN_ONE_PASSWORD"),
    ("admin-two", "admin", None, "QUIZ_ADMIN_TWO_PASSWORD"),
)


class Command(BaseCommand):
    help = "Provision the four named accounts from environment secrets"

    def handle(self, *args, **options):
        secrets = {}
        for username, role, _team, variable in ACCOUNTS:
            value = os.environ.get(variable, "")
            if role == "team" and (not value.isdigit() or len(value) < 6):
                raise CommandError(f"{variable} must be a PIN of at least 6 digits")
            if role == "admin" and len(value) < 12:
                raise CommandError(f"{variable} must be at least 12 characters")
            secrets[username] = value
        User = get_user_model()
        with transaction.atomic():
            for username, role, team_id, _variable in ACCOUNTS:
                user, created = User.objects.get_or_create(
                    username=username, defaults={"is_active": True}
                )
                mapping = AccountRole.objects.filter(user=user).first()
                if not created and (
                    mapping is None
                    or mapping.role != role
                    or mapping.team_id != team_id
                ):
                    raise CommandError(f"Existing {username} has an incompatible role")
                user.is_active = True
                user.is_staff = False
                user.is_superuser = False
                user.set_password(secrets[username])
                user.save()
                if created:
                    AccountRole.objects.create(user=user, role=role, team_id=team_id)
        self.stdout.write("Provisioned two team and two admin accounts")
