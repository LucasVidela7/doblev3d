from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("produccion", "0011_backfill_gcode_pendientes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="comandobambu",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("STOP", "Detener impresión"),
                    ("PRINT", "Iniciar impresión"),
                ],
                max_length=30,
            ),
        ),
    ]
