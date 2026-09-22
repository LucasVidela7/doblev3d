from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pedidos", "0015_solicitudweb_public_token"),
    ]

    operations = [
        migrations.AddField(
            model_name="solicitudwebitem",
            name="modo_color",
            field=models.CharField(
                blank=True,
                default="",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="solicitudwebitem",
            name="color_elegido",
            field=models.CharField(
                blank=True,
                default="",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="solicitudwebitem",
            name="adicional_color_unitario",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                max_digits=12,
            ),
        ),
    ]
