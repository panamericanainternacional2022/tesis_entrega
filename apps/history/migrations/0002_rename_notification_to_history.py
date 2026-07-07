import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('history', '0001_initial'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Notification',
            new_name='History',
        ),
        migrations.AlterModelTable(
            name='history',
            table='historial',
        ),
        migrations.AlterField(
            model_name='history',
            name='id',
            field=models.AutoField(db_column='id_historial', primary_key=True, serialize=False),
        ),
    ]
