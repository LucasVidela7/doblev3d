from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0012_webpushsubscription"),
    ]

    operations = [
        migrations.AddField(
            model_name="estadoimpresionpedido",
            name="reservado_stock",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="estadoimpresionpedido",
            name="cantidad_stock_reservada",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
