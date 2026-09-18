from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("kits", "0004_alter_kit_options_kit_modalidad_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="kit",
            name="proteger_rentabilidad_libre",
            field=models.BooleanField(
                default=False,
                help_text=(
                    "En kits libres, separa opciones incluidas de opciones "
                    "premium con extra según la calculadora de costos."
                ),
            ),
        ),
    ]
