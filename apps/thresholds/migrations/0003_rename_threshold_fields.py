from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("thresholds", "0002_alter_thresholdconfig_id"),
    ]

    operations = [
        # 1. Rename high → critic first (before low takes the name "high")
        migrations.RenameField(
            model_name="thresholdconfig",
            old_name="high",
            new_name="critic",
        ),
        # 2. Rename low → high (Alto threshold)
        migrations.RenameField(
            model_name="thresholdconfig",
            old_name="low",
            new_name="high",
        ),
        # 3. Remove the obsolete medium field
        migrations.RemoveField(
            model_name="thresholdconfig",
            name="medium",
        ),
    ]
