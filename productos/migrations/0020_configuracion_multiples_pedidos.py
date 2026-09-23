from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0019_configuracioncatalogo_mostrar_productos_sin_foto"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_cliente_multiples_pedidos",
            field=models.TextField(
                blank=True,
                default=(
                    "Hola {nombre} 👋 Te escribo por {cantidad_pedidos} pedidos "
                    "que tenés activos en Doble V 3D:\n\n"
                    "{pedidos}\n\n"
                    "*Saldo total pendiente: ${saldo_total}*\n\n"
                    "Cuando puedas, escribinos y coordinamos el pago 😊"
                ),
                help_text=(
                    "Podés usar {nombre}, {cantidad_pedidos}, {pedidos} y "
                    "{saldo_total}. {pedidos} genera el detalle y la URL pública "
                    "individual de cada pedido."
                ),
                verbose_name="Mensaje de múltiples pedidos",
            ),
        ),
    ]
