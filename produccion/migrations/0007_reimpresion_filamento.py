# Generated manually for advanced Bambu reprint filament selection.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("produccion", "0006_comandobambu"),
    ]

    operations = [
        migrations.AddField(
            model_name="produccion",
            name="bambu_ams_id",
            field=models.SmallIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="produccion",
            name="bambu_color_hex",
            field=models.CharField(blank=True, max_length=9),
        ),
        migrations.AddField(
            model_name="produccion",
            name="bambu_color_nombre",
            field=models.CharField(blank=True, max_length=100),
        ),
        migrations.AddField(
            model_name="produccion",
            name="bambu_fuente_filamento",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="produccion",
            name="bambu_material",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="produccion",
            name="bambu_requiere_cambio_manual",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="produccion",
            name="bambu_tray_id",
            field=models.SmallIntegerField(blank=True, null=True),
        ),
    ]
