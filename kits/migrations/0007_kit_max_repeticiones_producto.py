from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kits", "0006_kit_permite_elegir_color"),
    ]

    operations = [
        migrations.AddField(
            model_name="kit",
            name="max_repeticiones_producto",
            field=models.PositiveIntegerField(
                default=1,
                help_text=(
                    "Máximo de veces que un mismo producto puede elegirse "
                    "dentro de un kit libre. 1 impide repetir productos."
                ),
            ),
        ),
    ]
