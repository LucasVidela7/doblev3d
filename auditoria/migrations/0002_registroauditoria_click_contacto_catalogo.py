from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("auditoria", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="registroauditoria",
            name="accion",
            field=models.CharField(
                choices=[
                    ("CREAR", "Crear"),
                    ("MODIFICAR", "Modificar"),
                    ("ELIMINAR", "Eliminar"),
                    ("ENTREGAR_PEDIDO", "Entregar pedido"),
                    ("CANCELAR_PEDIDO", "Cancelar pedido"),
                    ("CAMBIAR_ESTADO_PEDIDO", "Cambiar estado de pedido"),
                    ("CAMBIAR_ESTADO_PRODUCCION", "Cambiar estado de producción"),
                    ("REGISTRAR_PAGO", "Registrar pago"),
                    ("INICIAR_SESION", "Iniciar sesión"),
                    ("CERRAR_SESION", "Cerrar sesión"),
                    ("CLICK_CONTACTO_CATALOGO", "Click contacto catálogo"),
                ],
                db_index=True,
                max_length=40,
            ),
        ),
    ]
