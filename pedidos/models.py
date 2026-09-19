from decimal import Decimal

from django.conf import settings
from django.db import models

from clientes.models import Cliente
from productos.models import Producto
from kits.models import Kit


class Pedido(models.Model):
    ESTADOS = [
        ("PENDIENTE", "Pendiente"),
        ("PREPARANDO", "Preparando"),
        ("LISTO", "Listo"),
        ("ENTREGADO", "Entregado"),
        ("CANCELADO", "Cancelado"),
    ]

    fecha = models.DateField(
        auto_now_add=True
    )

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="pedidos"
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default="PENDIENTE"
    )

    fecha_entrega = models.DateField(
        null=True,
        blank=True
    )

    observaciones = models.TextField(
        blank=True
    )

    @property
    def codigo(self):
        return f"PED{self.id:04d}" if self.id else "NUEVO"

    @property
    def total(self):
        return sum(
            (detalle.subtotal for detalle in self.detalles.all()),
            Decimal("0")
        )

    @property
    def total_pagado(self):
        return sum(
            (pago.monto for pago in self.pagos.all()),
            Decimal("0")
        )

    @property
    def saldo_pendiente(self):
        saldo = self.total - self.total_pagado
        return max(saldo, Decimal("0"))

    @property
    def estado_pago(self):
        pagado = self.total_pagado
        total = self.total

        if pagado <= 0:
            return "SIN_PAGAR"
        if pagado < total:
            return "PARCIAL"
        return "PAGADO"

    @property
    def estado_pago_display(self):
        return {
            "SIN_PAGAR": "Sin pagar",
            "PARCIAL": "Parcial",
            "PAGADO": "Pagado",
        }[self.estado_pago]

    def __str__(self):
        if self.id:
            return f"{self.codigo} - {self.cliente.nombre}"
        return f"Pedido - {self.cliente.nombre}"


class DetallePedido(models.Model):
    TIPOS_ITEM = [
        ("PRODUCTO", "Producto"),
        ("KIT", "Kit"),
        ("PERSONALIZADO", "Personalizado"),
    ]

    ESTADOS = [
        ("PENDIENTE", "Pendiente"),
        ("LISTO", "Listo"),
        ("ENTREGADO", "Entregado"),
        ("CANCELADO", "Cancelado"),
    ]

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name="detalles"
    )

    tipo_item = models.CharField(
        max_length=20,
        choices=TIPOS_ITEM
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="detalles_pedido"
    )

    kit = models.ForeignKey(
        Kit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="detalles_pedido"
    )

    cantidad = models.PositiveIntegerField(
        default=1
    )

    precio_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0
    )

    # En líneas KIT indica que el precio fue acordado explícitamente con el
    # cliente. En ese caso el cálculo automático por volumen puede seguir
    # mostrando una referencia, pero nunca debe sobrescribir este importe.
    precio_kit_manual = models.BooleanField(
        default=False
    )

    # Snapshot del costo por unidad al momento de la venta.
    # NULL = detalle anterior al módulo de rentabilidad.
    costo_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default="PENDIENTE"
    )

    personalizado = models.BooleanField(
        default=False
    )

    detalle_personalizacion = models.TextField(
        blank=True
    )

    color_personalizacion = models.CharField(
        max_length=100,
        blank=True
    )

    precio_total_personalizado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True
    )

    @property
    def subtotal(self):
        if (
            self.tipo_item == "PERSONALIZADO"
            and self.precio_total_personalizado is not None
        ):
            return self.precio_total_personalizado

        return self.precio_unitario * self.cantidad

    @property
    def costo_total_historico(self):
        if self.costo_unitario is None:
            return None
        return self.costo_unitario * self.cantidad

    @property
    def ganancia_bruta_historica(self):
        costo = self.costo_total_historico
        if costo is None:
            return None
        return self.subtotal - costo

    def save(self, *args, **kwargs):

        if self.precio_unitario == 0:

            if self.tipo_item == "PRODUCTO" and self.producto:
                self.precio_unitario = self.producto.subtotal

            elif self.tipo_item == "KIT" and self.kit:
                self.precio_unitario = self.kit.precio

        super().save(*args, **kwargs)

    def __str__(self):

        if self.tipo_item == "PRODUCTO" and self.producto:
            return f"{self.pedido.codigo} - {self.producto.nombre}"

        if self.tipo_item == "KIT" and self.kit:
            return f"{self.pedido.codigo} - {self.kit.nombre}"

        if self.tipo_item == "PERSONALIZADO" and self.producto:
            return (
                f"{self.pedido.codigo} - "
                f"{self.producto.nombre} personalizado"
            )

        return self.pedido.codigo


class DetalleKitProducto(models.Model):
    detalle = models.ForeignKey(
        DetallePedido,
        on_delete=models.CASCADE,
        related_name="productos_kit"
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT
    )

    cantidad = models.PositiveIntegerField(
        default=1
    )

    def __str__(self):
        return f"{self.detalle} - {self.producto.nombre}"


class Presupuesto(models.Model):
    ESTADOS = [
        ("PENDIENTE", "Pendiente"),
        ("APROBADO", "Aprobado"),
        ("RECHAZADO", "Rechazado"),
    ]

    fecha = models.DateField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.PROTECT,
        related_name="presupuestos",
    )

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default="PENDIENTE",
    )

    fecha_entrega = models.DateField(
        null=True,
        blank=True,
    )

    observaciones = models.TextField(
        blank=True,
    )

    pedido_generado = models.OneToOneField(
        Pedido,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="presupuesto_origen",
    )

    class Meta:
        ordering = ["-id"]

    @property
    def codigo(self):
        return f"PRE{self.id:04d}" if self.id else "NUEVO"

    @property
    def total_lista(self):
        return sum(
            (
                detalle.subtotal_lista
                for detalle in self.detalles.all()
            ),
            Decimal("0"),
        )

    @property
    def total(self):
        return sum(
            (
                detalle.subtotal
                for detalle in self.detalles.all()
            ),
            Decimal("0"),
        )

    @property
    def descuento_total(self):
        return max(
            self.total_lista - self.total,
            Decimal("0"),
        )

    @property
    def descuento_porcentaje(self):
        if self.total_lista <= 0:
            return Decimal("0")
        return (
            self.descuento_total
            / self.total_lista
            * Decimal("100")
        ).quantize(Decimal("0.1"))

    def __str__(self):
        return f"{self.codigo} - {self.cliente.nombre}"


class DetallePresupuesto(models.Model):
    TIPOS_ITEM = DetallePedido.TIPOS_ITEM

    presupuesto = models.ForeignKey(
        Presupuesto,
        on_delete=models.CASCADE,
        related_name="detalles",
    )

    tipo_item = models.CharField(
        max_length=20,
        choices=TIPOS_ITEM,
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="detalles_presupuesto",
    )

    kit = models.ForeignKey(
        Kit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="detalles_presupuesto",
    )

    cantidad = models.PositiveIntegerField(
        default=1,
    )

    precio_lista_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    precio_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    precio_kit_manual = models.BooleanField(
        default=False,
    )

    costo_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    personalizado = models.BooleanField(
        default=False,
    )

    detalle_personalizacion = models.TextField(
        blank=True,
    )

    color_personalizacion = models.CharField(
        max_length=100,
        blank=True,
    )

    precio_total_personalizado = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
    )

    @property
    def subtotal_lista(self):
        return (
            self.precio_lista_unitario
            * Decimal(self.cantidad)
        )

    @property
    def subtotal(self):
        if (
            self.tipo_item == "PERSONALIZADO"
            and self.precio_total_personalizado is not None
        ):
            return self.precio_total_personalizado

        return self.precio_unitario * Decimal(self.cantidad)

    @property
    def descuento(self):
        return max(
            self.subtotal_lista - self.subtotal,
            Decimal("0"),
        )

    @property
    def descuento_porcentaje(self):
        if self.subtotal_lista <= 0:
            return Decimal("0")
        return (
            self.descuento
            / self.subtotal_lista
            * Decimal("100")
        ).quantize(Decimal("0.1"))

    def __str__(self):
        return f"{self.presupuesto.codigo} - {self.tipo_item}"


class DetallePresupuestoKitProducto(models.Model):
    detalle = models.ForeignKey(
        DetallePresupuesto,
        on_delete=models.CASCADE,
        related_name="productos_kit",
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
    )

    cantidad = models.PositiveIntegerField(
        default=1,
    )

    def __str__(self):
        return (
            f"{self.detalle.presupuesto.codigo} - "
            f"{self.producto.nombre}"
        )



class SolicitudWeb(models.Model):
    ESTADOS = [
        ("NUEVA", "Nueva"),
        ("CONTACTADA", "Contactada"),
        ("CONVERTIDA", "Convertida"),
        ("RECHAZADA", "Rechazada"),
    ]

    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    nombre = models.CharField(max_length=150)
    telefono = models.CharField(max_length=40)
    telefono_normalizado = models.CharField(
        max_length=30,
        blank=True,
        db_index=True,
    )
    email = models.EmailField(blank=True)
    observaciones = models.TextField(blank=True)

    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default="NUEVA",
        db_index=True,
    )

    presupuesto_generado = models.OneToOneField(
        Presupuesto,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="solicitud_web_origen",
    )

    ip_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )
    fingerprint = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )
    user_agent = models.CharField(
        max_length=250,
        blank=True,
    )

    class Meta:
        ordering = ["-id"]

    @property
    def codigo(self):
        return f"WEB{self.id:04d}" if self.id else "WEB-NUEVA"

    @property
    def total(self):
        return sum(
            (item.subtotal for item in self.items.all()),
            Decimal("0"),
        )

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"


class WebPushSubscription(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="web_push_subscriptions",
    )
    endpoint = models.CharField(
        max_length=1000,
        unique=True,
    )
    p256dh = models.TextField()
    auth = models.TextField()
    user_agent = models.CharField(
        max_length=250,
        blank=True,
    )
    activa = models.BooleanField(default=True)
    creada_en = models.DateTimeField(auto_now_add=True)
    actualizada_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-actualizada_en", "-id"]

    def __str__(self):
        return f"Push {self.user_id} · {'activa' if self.activa else 'inactiva'}"


class SolicitudWebItem(models.Model):
    TIPOS = [
        ("PRODUCTO", "Producto"),
        ("KIT", "Kit"),
    ]

    solicitud = models.ForeignKey(
        SolicitudWeb,
        on_delete=models.CASCADE,
        related_name="items",
    )
    tipo_item = models.CharField(
        max_length=20,
        choices=TIPOS,
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="solicitudes_web",
    )
    kit = models.ForeignKey(
        Kit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="solicitudes_web",
    )
    cantidad = models.PositiveIntegerField(default=1)

    nombre_snapshot = models.CharField(max_length=200)
    precio_base_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    adicional_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )
    precio_unitario = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    @property
    def precio_lista_unitario(self):
        return (
            Decimal(str(self.precio_base_unitario or 0))
            + Decimal(str(self.adicional_unitario or 0))
        )

    @property
    def ahorro_unitario(self):
        return max(
            self.precio_lista_unitario
            - Decimal(str(self.precio_unitario or 0)),
            Decimal("0"),
        )

    @property
    def descuento_porcentaje(self):
        if self.precio_lista_unitario <= 0:
            return Decimal("0")
        return (
            self.ahorro_unitario
            / self.precio_lista_unitario
            * Decimal("100")
        ).quantize(Decimal("0.1"))

    @property
    def subtotal(self):
        return self.precio_unitario * Decimal(self.cantidad)

    def __str__(self):
        return (
            f"{self.solicitud.codigo} - "
            f"{self.nombre_snapshot} x{self.cantidad}"
        )


class SolicitudWebKitProducto(models.Model):
    item = models.ForeignKey(
        SolicitudWebItem,
        on_delete=models.CASCADE,
        related_name="productos_kit",
    )
    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
    )
    cantidad = models.PositiveIntegerField(default=1)

    def __str__(self):
        return (
            f"{self.item.solicitud.codigo} - "
            f"{self.producto.nombre} x{self.cantidad}"
        )


class EstadoImpresionPedido(models.Model):
    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.CASCADE,
        related_name="estados_impresion"
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT
    )

    listo = models.BooleanField(
        default=False
    )

    stock_descontado = models.BooleanField(
        default=False
    )

    cantidad_stock_descontada = models.PositiveIntegerField(
        default=0
    )

    reservado_stock = models.BooleanField(
        default=False
    )

    cantidad_stock_reservada = models.PositiveIntegerField(
        default=0
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "pedido",
                    "producto",
                ],
                name="estado_impresion_pedido_producto_unico"
            )
        ]

    def __str__(self):
        estado = "LISTO" if self.listo else "PENDIENTE"

        return (
            f"{self.pedido.codigo} - "
            f"{self.producto.nombre} - "
            f"{estado}"
        )


class Pago(models.Model):
    MEDIOS = [
        ("EFECTIVO", "Efectivo"),
        ("TRANSFERENCIA", "Transferencia"),
        ("MERCADO_PAGO", "Mercado Pago"),
        ("OTRO", "Otro"),
    ]

    pedido = models.ForeignKey(
        Pedido,
        on_delete=models.PROTECT,
        related_name="pagos"
    )

    fecha = models.DateTimeField(auto_now_add=True)

    monto = models.DecimalField(
        max_digits=12,
        decimal_places=2
    )

    medio = models.CharField(
        max_length=30,
        choices=MEDIOS
    )

    observaciones = models.CharField(
        max_length=250,
        blank=True
    )

    class Meta:
        ordering = ["-fecha", "-id"]

    def __str__(self):
        return (
            f"{self.pedido.codigo} - "
            f"{self.get_medio_display()} - "
            f"${self.monto}"
        )

# ============================================================
# GASTOS / INVERSIONES
# ============================================================

class Gasto(models.Model):
    TIPOS = [
        ("OPERATIVO", "Gasto operativo"),
        ("INVERSION", "Inversión"),
    ]

    CATEGORIAS = [
        ("FILAMENTO", "Filamento"),
        ("INSUMOS", "Otros insumos"),
        ("EQUIPAMIENTO", "Equipamiento"),
        ("MANTENIMIENTO", "Mantenimiento"),
        ("EMBALAJE", "Embalaje"),
        ("PUBLICIDAD", "Publicidad"),
        ("SERVICIOS", "Servicios"),
        ("ENVIO", "Envíos"),
        ("SOFTWARE", "Software"),
        ("COMISIONES", "Comisiones"),
        ("OTRO", "Otro"),
    ]

    MEDIOS_PAGO = [
        ("EFECTIVO", "Efectivo"),
        ("TRANSFERENCIA", "Transferencia"),
        ("DEBITO", "Débito"),
        ("TARJETA_CREDITO", "Tarjeta de crédito"),
        ("MERCADO_PAGO", "Mercado Pago"),
        ("OTRO", "Otro"),
    ]

    fecha_compra = models.DateField()

    tipo = models.CharField(
        max_length=20,
        choices=TIPOS,
        default="OPERATIVO",
    )

    categoria = models.CharField(
        max_length=30,
        choices=CATEGORIAS,
        default="OTRO",
    )

    descripcion = models.CharField(
        max_length=200,
    )

    monto_total = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    medio_pago = models.CharField(
        max_length=30,
        choices=MEDIOS_PAGO,
        default="TRANSFERENCIA",
    )

    cantidad_cuotas = models.PositiveSmallIntegerField(
        default=1,
    )

    fecha_primera_cuota = models.DateField(
        null=True,
        blank=True,
    )

    observaciones = models.TextField(
        blank=True,
    )

    creado_en = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = [
            "-fecha_compra",
            "-id",
        ]

    @property
    def monto_pagado(self):
        return sum(
            (
                cuota.monto
                for cuota in self.cuotas.filter(
                    pagada=True
                )
            ),
            Decimal("0"),
        )

    @property
    def saldo_pendiente(self):
        return max(
            self.monto_total - self.monto_pagado,
            Decimal("0"),
        )

    def __str__(self):
        return (
            f"{self.get_tipo_display()} - "
            f"{self.descripcion} - "
            f"${self.monto_total}"
        )


class CuotaGasto(models.Model):
    gasto = models.ForeignKey(
        Gasto,
        on_delete=models.CASCADE,
        related_name="cuotas",
    )

    numero = models.PositiveSmallIntegerField()

    fecha_vencimiento = models.DateField()

    monto = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    pagada = models.BooleanField(
        default=False,
    )

    fecha_pago = models.DateField(
        null=True,
        blank=True,
    )

    # Momento real en que la salida de dinero se registró.
    # Se usa para calcular la caja desde el último corte.
    pagada_en = models.DateTimeField(
        null=True,
        blank=True,
    )

    class Meta:
        ordering = [
            "fecha_vencimiento",
            "numero",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "gasto",
                    "numero",
                ],
                name="cuota_gasto_numero_unico",
            )
        ]

    def __str__(self):
        return (
            f"{self.gasto.descripcion} - "
            f"{self.numero}/{self.gasto.cantidad_cuotas}"
        )



# ============================================================
# CAJA / MERCADO PAGO
# ============================================================

class CajaCorte(models.Model):
    """
    Punto de conciliación de caja.

    El saldo ingresado por el usuario se toma como saldo REAL
    de Mercado Pago en ese momento. Desde este corte, la app
    proyecta la caja con los cobros y egresos registrados.
    """

    fecha = models.DateTimeField(
        auto_now_add=True,
    )

    saldo_real = models.DecimalField(
        max_digits=14,
        decimal_places=2,
    )

    observaciones = models.CharField(
        max_length=250,
        blank=True,
    )

    class Meta:
        ordering = [
            "-fecha",
            "-id",
        ]

    def __str__(self):
        return (
            f"Mercado Pago - "
            f"${self.saldo_real} - "
            f"{self.fecha:%d/%m/%Y %H:%M}"
        )
