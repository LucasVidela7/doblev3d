from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kits", "0005_kit_proteger_rentabilidad_libre"),
    ]

    operations = [
        migrations.AddField(
            model_name="kit",
            name="permite_elegir_color",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "Permite elegir un único color para todo el kit. "
                    "Los kits libres usan el adicional configurado en la tienda; "
                    "los kits fijos no tienen adicional."
                ),
            ),
        ),
    ]
