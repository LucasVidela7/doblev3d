from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0019_empaque_categorias_complementos"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReembolsoGasto",
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
                    "fecha",
                    models.DateField(),
                ),
                (
                    "monto",
                    models.DecimalField(
                        decimal_places=2,
                        max_digits=14,
                    ),
                ),
                (
                    "observaciones",
                    models.TextField(
                        blank=True,
                    ),
                ),
                (
                    "registrado_en",
                    models.DateTimeField(
                        auto_now_add=True,
                    ),
                ),
                (
                    "gasto",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="reembolsos",
                        to="pedidos.gasto",
                    ),
                ),
            ],
            options={
                "ordering": ["-fecha", "-id"],
            },
        ),
    ]
