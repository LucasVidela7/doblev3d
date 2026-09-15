from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        (
            "costos",
            "0002_remove_configuracioncostos_amortizacion_por_hora_and_more",
        ),
    ]

    operations = [
        migrations.CreateModel(
            name="TramoCostoFilamento",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "desde_gramos",
                    models.DecimalField(
                        decimal_places=2,
                        help_text=(
                            "Peso total de filamento de la venta a partir del cual se usa "
                            "este precio por kg. Ejemplo: 1000 para 1 kg."
                        ),
                        max_digits=12,
                        verbose_name="Desde gramos totales",
                    ),
                ),
                (
                    "coste_plastico_kg",
                    models.DecimalField(
                        decimal_places=2,
                        help_text=(
                            "Precio de compra habitual que podés conseguir para este volumen."
                        ),
                        max_digits=12,
                        verbose_name="Coste plástico por kg",
                    ),
                ),
                (
                    "activo",
                    models.BooleanField(default=True),
                ),
                (
                    "configuracion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="tramos_filamento",
                        to="costos.configuracioncostos",
                    ),
                ),
            ],
            options={
                "ordering": ["desde_gramos"],
            },
        ),
        migrations.AddConstraint(
            model_name="tramocostofilamento",
            constraint=models.UniqueConstraint(
                fields=("configuracion", "desde_gramos"),
                name="costo_filamento_tramo_unico",
            ),
        ),
    ]
