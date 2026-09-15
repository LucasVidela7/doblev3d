from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("stock", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="movimientostock",
            name="tipo",
            field=models.CharField(
                choices=[
                    ("ENTRADA_PRODUCCION", "Entrada por producción"),
                    ("ENTRADA_ARMADO", "Entrada por armado"),
                    ("SALIDA_PEDIDO", "Salida por pedido"),
                    ("SALIDA_ARMADO", "Salida por armado"),
                    ("AJUSTE_POSITIVO", "Ajuste positivo"),
                    ("AJUSTE_NEGATIVO", "Ajuste negativo"),
                    ("DESCARTE", "Descarte"),
                ],
                max_length=30,
            ),
        ),
    ]
