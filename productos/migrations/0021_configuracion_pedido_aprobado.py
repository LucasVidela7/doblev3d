from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("productos", "0020_configuracion_multiples_pedidos"),
    ]

    operations = [
        migrations.AddField(
            model_name="configuracioncatalogo",
            name="whatsapp_mensaje_cliente_pedido_aprobado",
            field=models.TextField(
                blank=True,
                default=(
                    "Hola {nombre} 👋 Tu solicitud fue aprobada y ya quedó registrada "
                    "como el pedido {codigo} de Doble V 3D.\n\n"
                    "Podés ver el detalle y seguir su estado acá:\n{url}\n\n"
                    "¡Gracias!"
                ),
                help_text=(
                    "Podés usar {nombre}, {codigo}, {url}, {total}, {saldo} "
                    "y {fecha_entrega}."
                ),
                verbose_name="Mensaje de pedido aprobado",
            ),
        ),
    ]
