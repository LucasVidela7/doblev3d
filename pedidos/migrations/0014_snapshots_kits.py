from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0013_estadoimpresionpedido_reserva_stock"),
    ]

    operations = [
        migrations.AddField(
            model_name="detallepedido",
            name="kit_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="detallepresupuesto",
            name="kit_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="solicitudwebitem",
            name="kit_snapshot",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
