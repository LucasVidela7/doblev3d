from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models


class RegistroAuditoria(models.Model):
    ACCIONES = [
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
    ]

    fecha = models.DateTimeField(auto_now_add=True, db_index=True)
    usuario = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="registros_auditoria",
    )
    usuario_nombre = models.CharField(max_length=150, blank=True)
    accion = models.CharField(max_length=40, choices=ACCIONES, db_index=True)
    app_label = models.CharField(max_length=100, db_index=True)
    modelo = models.CharField(max_length=100, db_index=True)
    objeto_id = models.CharField(max_length=100, blank=True, db_index=True)
    objeto_representacion = models.CharField(max_length=255, blank=True)
    cambios = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)
    ruta = models.CharField(max_length=500, blank=True)
    metodo = models.CharField(max_length=10, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-fecha", "-id"]
        verbose_name = "registro de auditoría"
        verbose_name_plural = "registros de auditoría"

    def __str__(self):
        usuario = self.usuario_nombre or "Sistema"
        return f"{self.fecha:%d/%m/%Y %H:%M} - {usuario} - {self.get_accion_display()} - {self.objeto_representacion}"
