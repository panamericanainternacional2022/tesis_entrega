from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0002_remove_alerts_disabled_fields"),
    ]

    operations = [
        migrations.RenameField(
            model_name="usuario",
            old_name="alerts_cleared_at",
            new_name="history_cleared_at",
        ),
    ]
