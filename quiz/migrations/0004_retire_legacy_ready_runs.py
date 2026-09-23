from django.db import migrations


def retire_legacy_ready_runs(apps, schema_editor):
    """Retire phase-2/3 Reset shells without changing historical run data."""
    Run = apps.get_model("quiz", "Run")
    Run.objects.filter(active=True, global_state="READY").update(active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("quiz", "0003_phase3"),
    ]

    operations = [
        migrations.RunPython(
            retire_legacy_ready_runs,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
