from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("quiz", "0007_phase6_challenge"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="musicquiz",
            name="valid_music_phase_state",
        ),
        migrations.AlterField(
            model_name="musicquiz",
            name="current_question_started_ms",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="musicquiz",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        phase="gathering",
                        current_question_number__isnull=True,
                        current_question_started_ms__isnull=True,
                        final_results_started_ms__isnull=True,
                    )
                    | models.Q(
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
    ]
