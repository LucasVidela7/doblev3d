from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("clientes", "0002_contactocliente"),
    ]

    operations = [
        migrations.AlterField(
            model_name="contactocliente",
            name="motivo",
            field=models.CharField(
                choices=[
                    ("GENERICO", "Contacto general"),
                    ("PEDIDO_APROBADO", "Pedido aprobado"),
                    ("PEDIDO_LISTO", "Pedido listo"),
                    ("SALDO", "Saldo pendiente"),
                    ("PRESUPUESTO", "Presupuesto pendiente"),
                    ("REACTIVACION", "Reactivar cliente"),
                ],
                default="GENERICO",
                max_length=30,
            ),
        ),
    ]
