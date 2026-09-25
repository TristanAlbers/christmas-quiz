import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


CHALLENGE_RESULT_TRIGGER = """
CREATE TRIGGER challenge_winning_attempt_matches_result
BEFORE UPDATE OF winning_attempt_id, winner_team_id, status, question_id
ON quiz_challenge
WHEN NEW.winning_attempt_id IS NOT NULL
BEGIN
    SELECT CASE
        WHEN NOT EXISTS (
            SELECT 1
            FROM quiz_challengeattempt AS attempt
            WHERE attempt.id = NEW.winning_attempt_id
              AND attempt.challenge_id = NEW.id
              AND attempt.team_id = NEW.winner_team_id
              AND attempt.question_id = NEW.question_id
              AND attempt.is_correct = 1
        )
        THEN RAISE(ABORT, 'invalid challenge winning attempt')
    END;
END;
"""


CHALLENGE_ATTEMPT_TRIGGER = """
CREATE TRIGGER challenge_winning_attempt_remains_valid
BEFORE UPDATE OF challenge_id, team_id, question_id, is_correct
ON quiz_challengeattempt
WHEN EXISTS (
    SELECT 1
    FROM quiz_challenge AS challenge
    WHERE challenge.winning_attempt_id = OLD.id
)
BEGIN
    SELECT CASE
        WHEN EXISTS (
            SELECT 1
            FROM quiz_challenge AS challenge
            WHERE challenge.winning_attempt_id = OLD.id
              AND (
                  NEW.challenge_id <> challenge.id
                  OR NEW.team_id <> challenge.winner_team_id
                  OR NEW.question_id <> challenge.question_id
                  OR NEW.is_correct <> 1
              )
        )
        THEN RAISE(ABORT, 'invalid challenge winning attempt mutation')
    END;
END;
"""


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("quiz", "0006_phase5_finish"),
    ]

    operations = [
        migrations.AddField(
            model_name="teamrun",
            name="challenge_available",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="Challenge",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("initiator_team_id", models.CharField(max_length=1)),
                ("challenged_team_id", models.CharField(max_length=1)),
                ("question_id", models.CharField(max_length=100)),
                ("paid_cost", models.PositiveIntegerField(default=0)),
                ("started_gameplay_ms", models.BigIntegerField()),
                ("status", models.CharField(default="active", max_length=8)),
                (
                    "winner_team_id",
                    models.CharField(blank=True, max_length=1, null=True),
                ),
                ("freeze_applied", models.BooleanField(default=False)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("resolved_at", models.DateTimeField(blank=True, null=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="challenges",
                        to="quiz.run",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ChallengeAttempt",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("team_id", models.CharField(max_length=1)),
                ("request_id", models.UUIDField()),
                ("question_id", models.CharField(max_length=100)),
                ("is_correct", models.BooleanField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "actor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "challenge",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="attempts",
                        to="quiz.challenge",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="challenge",
            name="winning_attempt",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="winning_challenge",
                to="quiz.challengeattempt",
            ),
        ),
        migrations.AddConstraint(
            model_name="challenge",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "active")),
                fields=("run",),
                name="one_active_challenge_per_run",
            ),
        ),
        migrations.AddConstraint(
            model_name="challenge",
            constraint=models.UniqueConstraint(
                fields=("run", "initiator_team_id"),
                name="one_challenge_per_initiator",
            ),
        ),
        migrations.AddConstraint(
            model_name="challenge",
            constraint=models.UniqueConstraint(
                fields=("run", "question_id"),
                name="unique_challenge_question_per_run",
            ),
        ),
        migrations.AddConstraint(
            model_name="challenge",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        ("challenged_team_id", "b"),
                        ("initiator_team_id", "a"),
                    )
                    | models.Q(
                        ("challenged_team_id", "a"),
                        ("initiator_team_id", "b"),
                    )
                ),
                name="valid_challenge_team_pair",
            ),
        ),
        migrations.AddConstraint(
            model_name="challenge",
            constraint=models.CheckConstraint(
                condition=models.Q(("paid_cost", 0)),
                name="challenge_cost_always_zero",
            ),
        ),
        migrations.AddConstraint(
            model_name="challenge",
            constraint=models.CheckConstraint(
                condition=models.Q(("started_gameplay_ms__gte", 0)),
                name="challenge_start_gameplay_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="challenge",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        ("freeze_applied", False),
                        ("resolved_at__isnull", True),
                        ("status", "active"),
                        ("winner_team_id__isnull", True),
                        ("winning_attempt__isnull", True),
                    )
                    | (
                        models.Q(
                            ("resolved_at__isnull", False),
                            ("status", "resolved"),
                            ("winner_team_id__isnull", False),
                            ("winning_attempt__isnull", False),
                        )
                        & (
                            models.Q(
                                ("freeze_applied", True),
                                winner_team_id=models.F("initiator_team_id"),
                            )
                            | models.Q(
                                ("freeze_applied", False),
                                winner_team_id=models.F("challenged_team_id"),
                            )
                        )
                    )
                ),
                name="valid_challenge_result_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="challengeattempt",
            constraint=models.UniqueConstraint(
                fields=("actor", "request_id"),
                name="unique_challenge_attempt_request",
            ),
        ),
        migrations.AddConstraint(
            model_name="challengeattempt",
            constraint=models.UniqueConstraint(
                condition=models.Q(("is_correct", True)),
                fields=("challenge",),
                name="unique_correct_challenge_attempt",
            ),
        ),
        migrations.AddConstraint(
            model_name="challengeattempt",
            constraint=models.CheckConstraint(
                condition=models.Q(("team_id__in", ["a", "b"])),
                name="valid_challenge_attempt_team",
            ),
        ),
        migrations.RunSQL(
            sql=CHALLENGE_RESULT_TRIGGER,
            reverse_sql=(
                "DROP TRIGGER IF EXISTS challenge_winning_attempt_matches_result;"
            ),
        ),
        migrations.RunSQL(
            sql=CHALLENGE_ATTEMPT_TRIGGER,
            reverse_sql=(
                "DROP TRIGGER IF EXISTS challenge_winning_attempt_remains_valid;"
            ),
        ),
    ]
