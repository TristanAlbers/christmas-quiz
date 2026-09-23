from django.db import migrations, models
from django.utils import timezone


def bootstrap_active_advent_clock(apps, schema_editor):
    """Start the new clock when upgrading an already-running phase-2 game."""
    Run = apps.get_model("quiz", "Run")
    anchor = timezone.now()
    Run.objects.filter(
        active=True,
        global_state="ADVENT_QUIZ",
        advent_clock_anchor__isnull=True,
    ).update(advent_clock_anchor=anchor)


class Migration(migrations.Migration):
    dependencies = [
        ("quiz", "0002_phase2"),
    ]

    operations = [
        migrations.AddField(
            model_name="run",
            name="advent_clock_anchor",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="run",
            name="gameplay_elapsed_ms",
            field=models.BigIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="teamrun",
            name="freeze_started_gameplay_ms",
            field=models.BigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="teamrun",
            name="reverse_active",
            field=models.BooleanField(default=False),
        ),
        migrations.RunPython(
            bootstrap_active_advent_clock,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name="run",
            constraint=models.CheckConstraint(
                condition=models.Q(gameplay_elapsed_ms__gte=0),
                name="gameplay_elapsed_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="teamrun",
            constraint=models.CheckConstraint(
                condition=models.Q(freeze_started_gameplay_ms__isnull=True)
                | models.Q(freeze_started_gameplay_ms__gte=0),
                name="freeze_start_nonnegative",
            ),
        ),
        migrations.AddConstraint(
            model_name="teamrun",
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        activity_state="FREEZE",
                        freeze_started_gameplay_ms__isnull=False,
                    )
                    | (
                        ~models.Q(activity_state="FREEZE")
                        & models.Q(freeze_started_gameplay_ms__isnull=True)
                    )
                ),
                name="freeze_state_start_paired",
            ),
        ),
    ]
