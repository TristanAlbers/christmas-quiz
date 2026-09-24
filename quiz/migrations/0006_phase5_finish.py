import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("quiz", "0005_phase4_music"),
    ]

    operations = [
        migrations.CreateModel(
            name="FirstFinisher",
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
                ("finished_at", models.DateTimeField(auto_now_add=True)),
                (
                    "run",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="first_finisher",
                        to="quiz.run",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="firstfinisher",
            constraint=models.CheckConstraint(
                condition=models.Q(team_id__in=["a", "b"]),
                name="valid_first_finisher_team",
            ),
        ),
    ]
