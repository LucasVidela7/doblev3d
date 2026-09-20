from decimal import Decimal, ROUND_CEILING
import re

from django.db import models

from costos.models import ConfiguracionCostos


class ConfiguracionCatalogo(models.Model):
    catalogo_activo = models.BooleanField(
        default=True,
        verbose_name="Catálogo público activo",
        help_text=(
            "Si se desactiva, toda la tienda pública muestra una página de mantenimiento."
        ),
    )
    mensaje_mantenimiento = models.CharField(
        max_length=240,
        blank=True,
        default=(
            "Estamos haciendo unos ajustes en la tienda. Volvé a visitarnos en unos minutos."
        ),
        verbose_name="Mensaje de mantenimiento",
    )
    notificaciones_pedidos_web_activas = models.BooleanField(
        default=True,
        verbose_name="Notificaciones de pedidos web",
        help_text=(
            "Activa o desactiva globalmente los avisos push cuando entra una solicitud web."
        ),
    )
    instagram_usuario = models.CharField(
        max_length=100,
        blank=True,
        default="doblev3d",
        verbose_name="Instagram",
        help_text="Usuario sin @. Ejemplo: doblev3d",
    )
    mostrar_instagram = models.BooleanField(
        default=True,
        verbose_name="Mostrar Instagram",
    )
    whatsapp_numero = models.CharField(
        max_length=30,
        blank=True,
        default="5491164760709",
        verbose_name="WhatsApp",
        help_text="Número con código de país. Ejemplo: 5491164760709",
    )
    mostrar_whatsapp = models.BooleanField(
        default=True,
        verbose_name="Mostrar WhatsApp",
    )
    whatsapp_mensaje = models.CharField(
        max_length=240,
        blank=True,
        default="Hola! Te escribo desde el catálogo de Doble V 3D.",
        verbose_name="Mensaje inicial de WhatsApp",
    )
    whatsapp_mensaje_respuesta_solicitud = models.TextField(
        blank=True,
        default=(
            "Hola {nombre}! 👋 Gracias por tu solicitud {codigo} en Doble V 3D.\n\n"
            "Este es el detalle que recibimos:\n{detalle}\n\n"
            "Total de productos: {total}\n\n"
            "Te escribo para confirmar disponibilidad y coordinar la entrega."
        ),
        verbose_name="Mensaje para responder solicitudes",
        help_text=(
            "Podés usar {nombre}, {codigo}, {detalle}, {total} y {observaciones}."
        ),
    )
    whatsapp_mensaje_post_solicitud = models.TextField(
        blank=True,
        default=(
            "Hola! 👋 Acabo de enviar la solicitud {codigo} desde el catálogo de "
            "Doble V 3D.\n\nDetalle:\n{detalle}\n\n"
            "Total de productos: {total}\n\n"
            "Quisiera coordinar disponibilidad y entrega."
        ),
        verbose_name="Mensaje del cliente después de solicitar",
        help_text=(
            "Se abre hacia tu WhatsApp. Podés usar {nombre}, {codigo}, "
            "{detalle}, {total} y {observaciones}."
        ),
    )

    whatsapp_mensaje_cliente_generico = models.TextField(
        blank=True,
        default=(
            "Hola {nombre} 👋 ¿Cómo estás? Te escribo de Doble V 3D."
        ),
        verbose_name="Mensaje general a clientes",
        help_text="Podés usar {nombre}.",
    )
    whatsapp_mensaje_cliente_pedido_listo = models.TextField(
        blank=True,
        default=(
            "Hola {nombre} 👋 Tu pedido {codigo} de Doble V 3D ya está listo "
            "para entregar. Cuando quieras coordinamos la entrega. ¡Gracias!"
        ),
        verbose_name="Mensaje de pedido listo",
        help_text=(
            "Podés usar {nombre}, {codigo}, {total} y {fecha_entrega}."
        ),
    )
    whatsapp_mensaje_cliente_saldo = models.TextField(
        blank=True,
        default=(
            "Hola {nombre} 👋 Te escribo por el pedido {codigo}. "
            "Quedó un saldo pendiente de $ {saldo}. "
            "Cuando puedas coordinamos el pago. ¡Gracias!"
        ),
        verbose_name="Mensaje de saldo pendiente",
        help_text=(
            "Podés usar {nombre}, {codigo}, {saldo}, {total} y {pagado}."
        ),
    )
    whatsapp_mensaje_cliente_presupuesto = models.TextField(
        blank=True,
        default=(
            "Hola {nombre} 👋 ¿Cómo estás? Te escribo por el presupuesto "
            "{codigo} de Doble V 3D. Si querés hacer algún cambio o avanzar "
            "con el pedido, avisame y lo revisamos."
        ),
        verbose_name="Mensaje de presupuesto pendiente",
        help_text=(
            "Podés usar {nombre}, {codigo}, {total} y {fecha}."
        ),
    )
    whatsapp_mensaje_cliente_reactivacion = models.TextField(
        blank=True,
        default=(
            "Hola {nombre} 👋 ¿Cómo estás? Hace un tiempo que no hablamos y "
            "quería consultarte si necesitabas volver a pedir alguno de "
            "nuestros productos de Doble V 3D."
        ),
        verbose_name="Mensaje de reactivación",
        help_text=(
            "Podés usar {nombre}, {dias_sin_actividad} y {ultima_actividad}."
        ),
    )

    class Meta:
        verbose_name = "Configuración del catálogo"
        verbose_name_plural = "Configuración del catálogo"

    def __str__(self):
        return "Contacto y redes del catálogo"

    def save(self, *args, **kwargs):
        # Es una configuración global: mantenemos una única fila estable.
        self.pk = 1
        self.instagram_usuario = (self.instagram_usuario or "").strip().lstrip("@")
        self.whatsapp_numero = re.sub(r"\D+", "", self.whatsapp_numero or "")
        super().save(*args, **kwargs)


class TipoProducto(models.Model):
    nombre = models.CharField(max_length=100, unique=True)
    activo = models.BooleanField(default=True)

    def __str__(self):
        return self.nombre


class Producto(models.Model):
    CATEGORIAS = [
        ("PRODUCTO", "Producto"),
        ("PERSONALIZADO", "Personalizado"),
        ("DESCARGADO", "Descargado"),
        ("OTRO", "Otro"),
    ]

    TIPOS_FABRICACION = [
        ("SIMPLE", "Impresión simple"),
        ("COMPUESTO", "Producto compuesto"),
    ]

    nombre = models.CharField(max_length=150)
    categoria = models.CharField(max_length=50, choices=CATEGORIAS)
    tipo = models.ForeignKey(
        TipoProducto,
        on_delete=models.PROTECT,
        related_name="productos",
    )
    horas = models.PositiveIntegerField(default=0)
    minutos = models.PositiveIntegerField(default=0)
    peso_gramos = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
    )
    margen_ganancia = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=0,
        help_text="Ejemplo: 60 para 60%",
    )
    requiere_impresion = models.BooleanField(default=True)
    personalizable = models.BooleanField(default=False)
    stock = models.IntegerField(default=0)
    activo = models.BooleanField(default=True)

    tipo_fabricacion = models.CharField(
        max_length=20,
        choices=TIPOS_FABRICACION,
        default="SIMPLE",
    )
    solo_produccion = models.BooleanField(
        default=False,
        help_text="Pieza interna de fabricación. No se ofrece como producto comercial.",
    )

    def __str__(self):
        if self.id:
            return f"{self.codigo} - {self.nombre}"
        return self.nombre

    @property
    def es_compuesto(self):
        return self.tipo_fabricacion == "COMPUESTO"

    def _relaciones_componentes(self):
        if not self.pk or not self.es_compuesto:
            return []
        return self.componentes.select_related("componente").all()

    @property
    def unidades_armables(self):
        """Unidades terminadas posibles con el stock actual de piezas."""
        if not self.es_compuesto or not self.pk:
            return 0

        disponibles = []
        for relacion in self._relaciones_componentes():
            cantidad = int(relacion.cantidad or 0)
            if cantidad <= 0:
                continue
            disponibles.append(
                max(int(relacion.componente.stock or 0), 0)
                // cantidad
            )

        return min(disponibles) if disponibles else 0

    @property
    def horas_totales(self):
        if self.es_compuesto and self.pk:
            total = Decimal("0")
            for relacion in self._relaciones_componentes():
                total += (
                    relacion.componente.horas_totales
                    * Decimal(int(relacion.cantidad or 0))
                )
            return total

        return Decimal(self.horas) + Decimal(self.minutos) / Decimal("60")

    @property
    def tiempo_formateado(self):
        if self.horas and self.minutos:
            return f"{self.horas} h {self.minutos} min"
        if self.horas:
            return f"{self.horas} h"
        if self.minutos:
            return f"{self.minutos} min"
        return "0 min"

    def recalcular_desde_componentes(self, guardar=True):
        """Sincroniza horas, minutos y peso del compuesto desde sus piezas."""
        if not self.pk or self.tipo_fabricacion != "COMPUESTO":
            return

        minutos_totales = 0
        peso_total = Decimal("0")

        for relacion in self.componentes.select_related("componente").all():
            pieza = relacion.componente
            cantidad = int(relacion.cantidad or 0)
            minutos_totales += (
                int(pieza.horas or 0) * 60 + int(pieza.minutos or 0)
            ) * cantidad
            peso_total += Decimal(pieza.peso_gramos or 0) * Decimal(cantidad)

        self.horas = minutos_totales // 60
        self.minutos = minutos_totales % 60
        self.peso_gramos = peso_total

        if guardar:
            Producto.objects.filter(pk=self.pk).update(
                horas=self.horas,
                minutos=self.minutos,
                peso_gramos=self.peso_gramos,
            )

    def sincronizar_productos_padre(self):
        if not self.pk:
            return
        padres = Producto.objects.filter(
            componentes__componente=self,
            tipo_fabricacion="COMPUESTO",
        ).distinct()
        for padre in padres:
            padre.recalcular_desde_componentes()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Si cambia una pieza simple, todos los productos que la usan
        # vuelven a calcular automáticamente tiempo y peso.
        if self.tipo_fabricacion == "SIMPLE":
            self.sincronizar_productos_padre()

    def obtener_configuracion(self):
        return (
            ConfiguracionCostos.objects
            .filter(activa=True)
            .order_by("-fecha_desde")
            .first()
        )

    @property
    def costo(self):
        if not self.requiere_impresion:
            return Decimal("0")

        # Un compuesto se valoriza desde sus piezas reales. Así el precio
        # no depende de que horas/peso agregados hayan quedado sincronizados.
        if self.es_compuesto and self.pk:
            total = Decimal("0")
            for relacion in self._relaciones_componentes():
                total += (
                    Decimal(str(relacion.componente.costo or 0))
                    * Decimal(int(relacion.cantidad or 0))
                )
            return total

        config = self.obtener_configuracion()
        if not config:
            return Decimal("0")
        costo_luz = self.horas_totales * config.coste_luz_hora
        costo_material = (
            Decimal(self.peso_gramos)
            * config.coste_plastico_kg
            / Decimal("1000")
        )
        return costo_luz + costo_material

    @property
    def seguro(self):
        if not self.requiere_impresion:
            return Decimal("0")

        # Igual que el costo, la cobertura productiva del compuesto se suma
        # desde cada pieza y su cantidad.
        if self.es_compuesto and self.pk:
            total = Decimal("0")
            for relacion in self._relaciones_componentes():
                total += (
                    Decimal(str(relacion.componente.seguro or 0))
                    * Decimal(int(relacion.cantidad or 0))
                )
            return total

        config = self.obtener_configuracion()
        if not config:
            return Decimal("0")
        amortizacion = self.horas_totales * config.coste_amortizacion_hora
        tasa_fallos = config.tasa_fallos / Decimal("100")
        return (amortizacion + self.costo) * tasa_fallos + amortizacion

    @property
    def subtotal(self):
        if not self.requiere_impresion:
            return Decimal("0")
        margen = self.margen_ganancia / Decimal("100")
        if margen >= Decimal("1"):
            return Decimal("0")
        ganancia_teorica = self.costo / (Decimal("1") - margen) - self.costo
        precio_sin_redondear = self.costo + self.seguro + ganancia_teorica
        multiplo = Decimal("500")
        return (
            (precio_sin_redondear / multiplo)
            .to_integral_value(rounding=ROUND_CEILING)
            * multiplo
        )

    @property
    def ganancia(self):
        return self.subtotal - self.costo - self.seguro

    @property
    def codigo(self):
        return f"P{self.id:04d}" if self.id else "NUEVO"


class ProductoComponente(models.Model):
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="componentes",
    )
    componente = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="usado_como_componente",
    )
    cantidad = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["componente__nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["producto", "componente"],
                name="producto_componente_unico",
            )
        ]

    def __str__(self):
        return f"{self.producto.nombre} · {self.componente.nombre} x{self.cantidad}"

    def save(self, *args, **kwargs):
        if self.producto_id == self.componente_id:
            raise ValueError("Un producto no puede contenerse a sí mismo.")
        super().save(*args, **kwargs)
        self.producto.recalcular_desde_componentes()

    def delete(self, *args, **kwargs):
        producto = self.producto
        resultado = super().delete(*args, **kwargs)
        producto.recalcular_desde_componentes()
        return resultado
