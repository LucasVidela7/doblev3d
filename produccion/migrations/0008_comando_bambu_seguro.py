# Generated manually for safer Bambu command delivery.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("produccion", "0007_reimpresion_filamento"),
    ]

    operations = [
        migrations.AddField(
            model_name="comandobambu",
            name="expira_en",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="comandobambu",
            name="trabajo_bambu_esperado",
            field=models.CharField(blank=True, max_length=255),
        ),
        migrations.AlterField(
            model_name="comandobambu",
            name="estado",
            field=models.CharField(
                choices=[
                    ("PENDIENTE", "Pendiente"),
                    ("EJECUTADO", "Ejecutado"),
                    ("ERROR", "Error"),
                    ("EXPIRADO", "Expirado"),
                ],
                default="PENDIENTE",
                max_length=20,
            ),
        ),
    ]
