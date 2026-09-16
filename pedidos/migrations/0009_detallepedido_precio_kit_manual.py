from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0008_cajacorte_cuotagasto_pagada_en"),
    ]

    operations = [
        migrations.AddField(
            model_name="detallepedido",
            name="precio_kit_manual",
            field=models.BooleanField(default=False),
        ),
    ]
