import django.core.serializers.json
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RegistroAuditoria",
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
                ("fecha", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("usuario_nombre", models.CharField(blank=True, max_length=150)),
                (
                    "accion",
                    models.CharField(
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
                        ],
                        db_index=True,
                        max_length=40,
                    ),
                ),
                ("app_label", models.CharField(db_index=True, max_length=100)),
                ("modelo", models.CharField(db_index=True, max_length=100)),
                ("objeto_id", models.CharField(blank=True, db_index=True, max_length=100)),
                ("objeto_representacion", models.CharField(blank=True, max_length=255)),
                (
                    "cambios",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        encoder=django.core.serializers.json.DjangoJSONEncoder,
                    ),
                ),
                ("ruta", models.CharField(blank=True, max_length=500)),
                ("metodo", models.CharField(blank=True, max_length=10)),
                ("ip", models.GenericIPAddressField(blank=True, null=True)),
                (
                    "usuario",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="registros_auditoria",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "registro de auditoría",
                "verbose_name_plural": "registros de auditoría",
                "ordering": ["-fecha", "-id"],
            },
        ),
    ]
