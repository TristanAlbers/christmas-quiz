import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_pause_resume_target(apps, schema_editor):
    """All pre-phase-4 pauses interrupted Advent, never Music."""
    Run = apps.get_model("quiz", "Run")
    Run.objects.filter(global_state="PAUSED").update(pause_resume_target="ADVENT_QUIZ")


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("quiz", "0004_retire_legacy_ready_runs"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="pause_resume_target",
            field=models.CharField(blank=True, max_length=24, null=True),
        ),
        migrations.RunPython(
            backfill_pause_resume_target,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="run",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        global_state="PAUSED",
                        pause_resume_target__in=["ADVENT_QUIZ", "MUSIC_QUIZ"],
                    )
                    | (
                        ~models.Q(global_state="PAUSED")
                        & models.Q(pause_resume_target__isnull=True)
                    )
                ),
                name="pause_resume_target_state_pair",
            ),
        ),
        migrations.CreateModel(
            name="MusicQuiz",
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
                ("phase", models.CharField(max_length=16)),
                (
                    "current_question_number",
                    models.PositiveSmallIntegerField(blank=True, null=True),
                ),
                (
                    "current_question_started_ms",
                    models.BigIntegerField(blank=True, default=0, null=True),
                ),
                ("music_elapsed_ms", models.BigIntegerField(default=0)),
                (
                    "music_clock_anchor",
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    "final_results_started_ms",
                    models.BigIntegerField(blank=True, null=True),
                ),
                (
                    "previous_winner_team",
                    models.CharField(blank=True, max_length=1, null=True),
                ),
                (
                    "run",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="music_quiz",
                        to="quiz.run",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="MusicAttempt",
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
                ("question_number", models.PositiveSmallIntegerField()),
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
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="quiz.run",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="MusicQuestionResult",
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
                ("question_number", models.PositiveSmallIntegerField()),
                ("question_id", models.CharField(max_length=100)),
                ("winner_team_id", models.CharField(max_length=1)),
                ("reward_points", models.PositiveIntegerField()),
                ("resolved_at", models.DateTimeField(auto_now_add=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="quiz.run",
                    ),
                ),
                (
                    "winning_attempt",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="quiz.musicattempt",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="MusicScore",
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
                ("score", models.PositiveSmallIntegerField(default=0)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        to="quiz.run",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="musicquiz",
            constraint=models.CheckConstraint(
                condition=models.Q(music_elapsed_ms__gte=0),
                name="music_elapsed_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="musicquiz",
            constraint=models.CheckConstraint(
                condition=models.Q(current_question_started_ms__isnull=True)
                | models.Q(current_question_started_ms__gte=0),
                name="music_question_start_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="musicquiz",
            constraint=models.CheckConstraint(
                condition=models.Q(previous_winner_team__isnull=True)
                | models.Q(previous_winner_team__in=["a", "b"]),
                name="valid_music_previous_winner",
            ),
        ),
        migrations.AddConstraint(
            model_name="musicquiz",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        phase="question",
                        current_question_number__isnull=False,
                        current_question_number__gte=1,
                        current_question_number__lte=11,
                        current_question_started_ms__isnull=False,
                        final_results_started_ms__isnull=True,
                    )
                    | models.Q(
                        phase="final_results",
                        current_question_number__isnull=True,
                        current_question_started_ms__isnull=True,
                        final_results_started_ms__isnull=False,
                        final_results_started_ms__gte=0,
                    )
                    | models.Q(
                        phase="completed",
                        current_question_number__isnull=True,
                        current_question_started_ms__isnull=True,
                        final_results_started_ms__isnull=False,
                        final_results_started_ms__gte=0,
                        music_clock_anchor__isnull=True,
                    )
                ),
                name="valid_music_phase_state",
            ),
        ),
        migrations.AddConstraint(
            model_name="musicattempt",
            constraint=models.UniqueConstraint(
                fields=("run", "actor", "request_id"),
                name="unique_music_attempt_request",
            ),
        ),
        migrations.AddConstraint(
            model_name="musicattempt",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_correct=True),
                fields=("run", "question_number"),
                name="unique_correct_music_attempt",
            ),
        ),
        migrations.AddConstraint(
            model_name="musicattempt",
            constraint=models.CheckConstraint(
                condition=models.Q(team_id__in=["a", "b"]),
                name="valid_music_attempt_team",
            ),
        ),
        migrations.AddConstraint(
            model_name="musicattempt",
            constraint=models.CheckConstraint(
                condition=models.Q(question_number__gte=1, question_number__lte=11),
                name="valid_music_attempt_number",
            ),
        ),
        migrations.AddConstraint(
            model_name="musicquestionresult",
            constraint=models.UniqueConstraint(
                fields=("run", "question_number"),
                name="unique_music_question_number",
            ),
        ),
        migrations.AddConstraint(
            model_name="musicquestionresult",
            constraint=models.UniqueConstraint(
                fields=("run", "question_id"),
                name="unique_music_question_id",
            ),
        ),
        migrations.AddConstraint(
            model_name="musicquestionresult",
            constraint=models.CheckConstraint(
                condition=models.Q(winner_team_id__in=["a", "b"]),
                name="valid_music_winner_team",
            ),
        ),
        migrations.AddConstraint(
            model_name="musicquestionresult",
            constraint=models.CheckConstraint(
                condition=models.Q(question_number__gte=1, question_number__lte=11),
                name="valid_music_result_number",
            ),
        ),
        migrations.AddConstraint(
            model_name="musicscore",
            constraint=models.UniqueConstraint(
                fields=("run", "team_id"), name="unique_music_score"
            ),
        ),
        migrations.AddConstraint(
            model_name="musicscore",
            constraint=models.CheckConstraint(
                condition=models.Q(team_id__in=["a", "b"]),
                name="valid_music_score_team",
            ),
        ),
        migrations.AddConstraint(
            model_name="musicscore",
            constraint=models.CheckConstraint(
                condition=models.Q(score__lte=11),
                name="music_score_at_most_eleven",
            ),
        ),
    ]
