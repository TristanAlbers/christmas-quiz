import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("quiz", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="teamrun",
            name="hint_tokens",
            field=models.IntegerField(default=0),
        ),
        migrations.AddConstraint(
            model_name="teamrun",
            constraint=models.CheckConstraint(
                condition=models.Q(hint_tokens__gte=0), name="hint_tokens_nonnegative"
            ),
        ),
        migrations.CreateModel(
            name="CommandReceipt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("request_id", models.UUIDField()),
                ("action", models.CharField(max_length=40)),
                ("payload_digest", models.CharField(max_length=64)),
                ("result", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="quiz.run")),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("actor", "request_id"), name="unique_command_receipt")
                ],
            },
        ),
        migrations.CreateModel(
            name="HintReveal",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("team_id", models.CharField(max_length=1)),
                ("puzzle_id", models.CharField(max_length=100)),
                ("source", models.CharField(choices=[("player", "Player"), ("admin", "Admin")], max_length=8)),
                ("request_id", models.UUIDField()),
                ("revealed_at", models.DateTimeField(auto_now_add=True)),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
                ("run", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="quiz.run")),
            ],
            options={
                "constraints": [
                    models.UniqueConstraint(fields=("run", "team_id", "puzzle_id"), name="unique_hint_reveal"),
                    models.CheckConstraint(condition=models.Q(team_id__in=["a", "b"]), name="valid_hint_team"),
                ],
            },
        ),
    ]
