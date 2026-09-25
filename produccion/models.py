from datetime import timedelta
from decimal import Decimal

from django.db import models

from pedidos.models import Pedido
from productos.models import Producto


class Impresora(models.Model):
    nombre = models.CharField(
        max_length=100,
        unique=True,
    )

    activa = models.BooleanField(
        default=True,
    )

    def __str__(self):
        return self.nombre

    class Meta:
        ordering = ["nombre"]


class ImpresoraEstadoBambu(models.Model):
    impresora = models.OneToOneField(
        Impresora,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="estado_bambu",
    )

    serial = models.CharField(
        max_length=32,
        unique=True,
    )

    nombre_bridge = models.CharField(
        max_length=100,
        blank=True,
    )

    ip = models.GenericIPAddressField(
        protocol="IPv4",
        null=True,
        blank=True,
    )

    conectada = models.BooleanField(
        default=False,
    )

    estado = models.CharField(
        max_length=50,
        blank=True,
    )

    progreso = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
    )

    minutos_restantes = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    trabajo = models.CharField(
        max_length=255,
        blank=True,
    )

    temperatura_nozzle = models.FloatField(
        null=True,
        blank=True,
    )

    temperatura_bed = models.FloatField(
        null=True,
        blank=True,
    )

    wifi = models.CharField(
        max_length=32,
        blank=True,
    )

    ultimo_evento_impresora = models.DateTimeField(
        null=True,
        blank=True,
    )

    ultimo_contacto = models.DateTimeField(
        auto_now=True,
    )

    ams = models.JSONField(
        default=dict,
        blank=True,
    )

    carrete_externo = models.JSONField(
        default=dict,
        blank=True,
    )

    payload = models.JSONField(
        default=dict,
        blank=True,
    )

    class Meta:
        ordering = ["nombre_bridge", "serial"]

    def __str__(self):
        return self.nombre_bridge or self.serial


class Produccion(models.Model):
    DESTINOS = [
        ("STOCK", "Stock"),
        ("PEDIDO", "Pedido"),
    ]

    ESTADOS = [
        ("PENDIENTE", "Pendiente"),
        ("IMPRIMIENDO", "Imprimiendo"),
        ("CONTROL", "Pendiente de control"),
        ("LISTO", "Listo"),
        ("FALLIDA", "Fallida"),
        ("CANCELADO", "Cancelado"),
    ]

    fecha = models.DateTimeField(
        auto_now_add=True,
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="producciones",
    )

    cantidad = models.PositiveIntegerField(
        default=1,
    )

    destino = models.CharField(
        max_length=20,
        choices=DESTINOS,
        default="STOCK",
    )

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="producciones",
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default="PENDIENTE",
    )

    impresora = models.ForeignKey(
        Impresora,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="producciones",
    )

    inicio_impresion = models.DateTimeField(
        null=True,
        blank=True,
    )

    tiempo_impresion_minutos = models.PositiveIntegerField(
        default=0,
    )

    ingresado_stock = models.BooleanField(
        default=False,
    )

    fin_impresion_detectado = models.DateTimeField(
        null=True,
        blank=True,
    )

    control_calidad_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    resultado_control = models.CharField(
        max_length=20,
        blank=True,
    )

    evento_fin_bambu = models.CharField(
        max_length=30,
        blank=True,
    )

    reimpresion_de = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reimpresiones",
    )

    observaciones = models.TextField(
        blank=True,
    )

    @property
    def codigo(self):
        return (
            f"PRD{self.id:04d}"
            if self.id
            else "NUEVO"
        )

    @property
    def fin_estimado(self):
        if (
            not self.inicio_impresion
            or not self.tiempo_impresion_minutos
        ):
            return None

        return (
            self.inicio_impresion
            + timedelta(
                minutes=self.tiempo_impresion_minutos
            )
        )

    @property
    def peso_total_gramos(self):
        peso_unitario = Decimal(
            str(
                getattr(
                    self.producto,
                    "peso_gramos",
                    0,
                )
                or 0
            )
        )

        return (
            peso_unitario
            * Decimal(int(self.cantidad or 0))
        )

    @property
    def peso_total_formateado(self):
        total = self.peso_total_gramos

        if total >= Decimal("1000"):
            valor = total / Decimal("1000")
            texto = f"{valor:.2f}".rstrip("0").rstrip(".")
            return f"{texto} kg"

        texto = f"{total:.1f}".rstrip("0").rstrip(".")
        return f"{texto or '0'} g"

    @property
    def tiempo_impresion_formateado(self):
        total = int(
            self.tiempo_impresion_minutos or 0
        )

        if total <= 0:
            return f"⚖ {self.peso_total_formateado}"

        horas = total // 60
        minutos = total % 60

        if horas and minutos:
            duracion = f"{horas} h {minutos} min"
        elif horas:
            duracion = f"{horas} h"
        else:
            duracion = f"{minutos} min"

        return (
            f"{duracion} · "
            f"⚖ {self.peso_total_formateado}"
        )

    def __str__(self):
        return (
            f"{self.codigo} - "
            f"{self.producto.nombre} x{self.cantidad}"
        )



class ConfiguracionProduccion(models.Model):
    avisos_impresion_activos = models.BooleanField(
        default=True,
    )

    avisar_antes_finalizar = models.BooleanField(
        default=True,
    )

    minutos_aviso_finalizacion = models.PositiveSmallIntegerField(
        default=15,
    )

    avisar_finalizacion = models.BooleanField(
        default=True,
    )

    avisar_cancelacion = models.BooleanField(
        default=True,
    )

    def __str__(self):
        return "Configuración de producción"


class EventoBambu(models.Model):
    TIPOS = [
        ("PROXIMO_FIN", "Próxima a finalizar"),
        ("FINALIZADA", "Finalizada"),
        ("CANCELADA", "Cancelada"),
    ]

    clave = models.CharField(
        max_length=180,
        unique=True,
    )

    tipo = models.CharField(
        max_length=30,
        choices=TIPOS,
    )

    impresora_estado = models.ForeignKey(
        ImpresoraEstadoBambu,
        on_delete=models.CASCADE,
        related_name="eventos",
    )

    produccion = models.ForeignKey(
        Produccion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="eventos_bambu",
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    payload = models.JSONField(
        default=dict,
        blank=True,
    )

    class Meta:
        ordering = ["-creado_en", "-id"]

    def __str__(self):
        return f"{self.get_tipo_display()} · {self.impresora_estado}"
