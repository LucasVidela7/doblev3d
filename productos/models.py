from decimal import Decimal, ROUND_CEILING
import re
import unicodedata

from django.core.cache import cache
from django.db import models
from django.utils import timezone

from costos.models import ConfiguracionCostos


COLORES_CATALOGO_PREDEFINIDOS = (
    ("Blanco", "#FFFFFF"),
    ("Negro", "#000000"),
    ("Rojo", "#EF1111"),
    ("Azul", "#0B66C3"),
    ("Celeste", "#67D3EA"),
    ("Acqua", "#63D8E5"),
    ("Turquesa", "#22C7C9"),
    ("Verde", "#00963F"),
    ("Amarillo", "#FFE000"),
    ("Naranja", "#FF8A00"),
    ("Rosa", "#F05CAB"),
    ("Fucsia", "#E83E8C"),
    ("Violeta", "#7C3AED"),
    ("Lila", "#B89AF3"),
    ("Gris", "#9B9B9B"),
    ("Plateado", "#B8BCC2"),
    ("Beige", "#D7B98B"),
    ("Marrón", "#A96438"),
    ("Bordó", "#7F1D1D"),
    ("Dorado", "#D4A017"),
)


def _clave_color_catalogo(valor):
    return (
        unicodedata.normalize(
            "NFD",
            str(valor or "").strip().casefold(),
        )
        .encode("ascii", "ignore")
        .decode("ascii")
    )


_COLORES_CATALOGO_POR_NOMBRE = {
    _clave_color_catalogo(nombre): (nombre, hexa)
    for nombre, hexa in COLORES_CATALOGO_PREDEFINIDOS
}


def _normalizar_hex_color(valor):
    valor = str(valor or "").strip()
    if re.fullmatch(r"#?[0-9A-Fa-f]{6}", valor):
        return "#" + valor.lstrip("#").upper()
    return ""


def _nombre_color_personalizado(valor):
    return re.sub(r"[|\\r\\n]+", " ", str(valor or "")).strip()[:60]


def normalizar_color_catalogo(valor):
    """Canoniza presets, HEX y colores personalizados con nombre + HEX."""
    valor = str(valor or "").strip()
    if not valor:
        return ""

    if "|" in valor:
        nombre, posible_hex = valor.rsplit("|", 1)
        hexa = _normalizar_hex_color(posible_hex)
        if hexa:
            nombre = _nombre_color_personalizado(nombre) or hexa
            return f"{nombre}|{hexa}"

    hexa = _normalizar_hex_color(valor)
    if hexa:
        return hexa

    predefinido = _COLORES_CATALOGO_POR_NOMBRE.get(
        _clave_color_catalogo(valor)
    )
    if predefinido:
        return predefinido[0]

    # Conserva nombres históricos que ya pudieran existir.
    return _nombre_color_personalizado(valor)


def detalle_color_catalogo(valor):
    """Devuelve valor visible, nombre y HEX de un color configurado."""
    normalizado = normalizar_color_catalogo(valor)
    if not normalizado:
        return {
            "valor": "",
            "nombre": "",
            "hex": "#D8DDE5",
            "personalizado": False,
            "predefinido": False,
            "almacenado": "",
        }

    if "|" in normalizado:
        nombre, hexa = normalizado.rsplit("|", 1)
        return {
            "valor": nombre,
            "nombre": nombre,
            "hex": hexa,
            "personalizado": True,
            "predefinido": False,
            "almacenado": normalizado,
        }

    if re.fullmatch(r"#[0-9A-F]{6}", normalizado):
        return {
            "valor": normalizado,
            "nombre": normalizado,
            "hex": normalizado,
            "personalizado": True,
            "predefinido": False,
            "almacenado": normalizado,
        }

    predefinido = _COLORES_CATALOGO_POR_NOMBRE.get(
        _clave_color_catalogo(normalizado)
    )
    if predefinido:
        nombre, hexa = predefinido
        return {
            "valor": nombre,
            "nombre": nombre,
            "hex": hexa,
            "personalizado": False,
            "predefinido": True,
            "almacenado": nombre,
        }

    return {
        "valor": normalizado,
        "nombre": normalizado,
        "hex": "#D8DDE5",
        "personalizado": False,
        "predefinido": False,
        "almacenado": normalizado,
    }


def nombre_color_catalogo(valor):
    return detalle_color_catalogo(valor)["nombre"]


def color_hex_catalogo(valor):
    """Devuelve un color CSS seguro para la muestra visual."""
    return detalle_color_catalogo(valor)["hex"]


class ConfiguracionCatalogo(models.Model):
    mostrar_productos_sin_foto = models.BooleanField(
        default=True,
        verbose_name="Mostrar productos sin foto",
        help_text=(
            "Si se desactiva, los productos sin imágenes en el ambiente actual "
            "se ocultan de los listados y de su detalle público. "
            "Los kits y Gestión no se modifican."
        ),
    )
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
    mensaje_plazo_entrega = models.CharField(
        max_length=300,
        blank=True,
        default=(
            "Plazo de entrega: entre 3 y 10 días hábiles desde la confirmación "
            "del presupuesto. El tiempo puede variar según stock, personalización "
            "y disponibilidad de materiales."
        ),
        verbose_name="Plazo de entrega del catálogo",
        help_text=(
            "Se muestra en la tienda, productos, kits y revisión de la solicitud."
        ),
    )
    colores_disponibles = models.TextField(
        blank=True,
        default="",
        verbose_name="Colores disponibles",
        help_text="Un color por línea. Se ofrecen en productos y kits habilitados.",
    )
    adicional_color_kit_base = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Cargo base por color en kit libre",
    )
    adicional_color_kit_por_producto = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        verbose_name="Cargo por producto por color en kit libre",
    )
    redondeo_precio_producto = models.PositiveIntegerField(
        default=100,
        verbose_name="Múltiplo de redondeo para precios",
        help_text=(
            "Los precios de lista de productos se redondean siempre hacia arriba "
            "al próximo múltiplo configurado. Ejemplo: 100."
        ),
    )
    incremento_insumos_por_defecto = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal("10.00"),
        verbose_name="Incremento general de insumos",
        help_text=(
            "Porcentaje de provisión aplicado al costo unitario de los insumos "
            "que no tengan un porcentaje particular."
        ),
    )

    @property
    def colores_disponibles_lista(self):
        return [
            color["valor"]
            for color in self.colores_disponibles_detalle
        ]

    @property
    def colores_disponibles_detalle(self):
        vistos = set()
        colores = []
        for linea in (self.colores_disponibles or "").splitlines():
            color = detalle_color_catalogo(linea)
            clave = _clave_color_catalogo(color["valor"])
            if color["valor"] and clave not in vistos:
                vistos.add(clave)
                colores.append(color)
        return colores

    def adicional_color_kit_libre(self, cantidad_productos):
        cantidad = max(int(cantidad_productos or 0), 0)
        return (
            Decimal(str(self.adicional_color_kit_base or 0))
            + Decimal(str(self.adicional_color_kit_por_producto or 0))
            * cantidad
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
    whatsapp_pago_alias = models.CharField(
        max_length=120,
        blank=True,
        default="doblev3d.mp",
        verbose_name="Alias de pago",
        help_text="Alias que se informa automáticamente cuando hay un pago pendiente.",
    )
    whatsapp_pago_titular = models.CharField(
        max_length=180,
        blank=True,
        default="Lucas Andrés Videla",
        verbose_name="Titular del medio de pago",
        help_text="Nombre del titular que se muestra junto al alias.",
    )
    whatsapp_mensaje_respuesta_solicitud = models.TextField(
        blank=True,
        default=(
            "Hola {nombre}! 👋 Gracias por tu solicitud {codigo} en Doble V 3D.\n\n"
            "Podés revisar el detalle completo acá:\n{url}\n\n"
            "Total de productos: {total}\n\n"
            "Para confirmar tu pedido solicitamos una seña del 30%: {senia}.\n\n"
            "{datos_pago}\n\n"
            "El plazo estimado de entrega es de 3 a 10 días hábiles "
            "a partir del {fecha_hoy}.\n\n"
            "Si querés avanzar, realizá la seña y enviame el comprobante "
            "por acá. Una vez acreditada, tu pedido queda confirmado. 😊"
        ),
        verbose_name="Mensaje para responder solicitudes",
        help_text=(
            "Podés usar {nombre}, {codigo}, {detalle}, {url}, {total}, {senia}, "
            "{datos_pago}, {fecha_hoy} y {observaciones}."
        ),
    )
    whatsapp_mensaje_post_solicitud = models.TextField(
        blank=True,
        default=(
            "Hola! 👋 Acabo de enviar la solicitud {codigo} desde el catálogo de "
            "Doble V 3D.\n\nDetalle de la solicitud:\n{url}\n\n"
            "Total de productos: {total}\n\n"
            "Quisiera coordinar disponibilidad y entrega."
        ),
        verbose_name="Mensaje del cliente después de solicitar",
        help_text=(
            "Se abre hacia tu WhatsApp. Podés usar {nombre}, {codigo}, "
            "{detalle}, {url}, {total} y {observaciones}."
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
    whatsapp_mensaje_cliente_pedido_aprobado = models.TextField(
        blank=True,
        default=(
            "Hola {nombre} 👋 Tu solicitud fue aprobada y ya quedó registrada "
            "como el pedido {codigo} de Doble V 3D.\n\n"
            "Podés ver el detalle y seguir su estado acá:\n{url}\n\n"
            "¡Gracias!"
        ),
        verbose_name="Mensaje de pedido aprobado",
        help_text=(
            "Podés usar {nombre}, {codigo}, {url}, {total}, {saldo} "
            "y {fecha_entrega}."
        ),
    )
    whatsapp_mensaje_cliente_pedido_listo = models.TextField(
        blank=True,
        default=(
            "Hola {nombre} 👋 Tu pedido de Doble V 3D ya está listo "
            "para entregar.\n\n"
            "{pedido}\n\n"
            "{cierre}"
        ),
        verbose_name="Mensaje de pedido listo y pagado",
        help_text=(
            "Podés usar {nombre}, {pedido}, {codigo}, {url}, {total}, "
            "{pagado}, {saldo}, {cantidad_pagos}, {fecha_entrega} y {cierre}. "
            "{pedido} incluye estado, pagos, saldo y URL pública."
        ),
    )
    whatsapp_mensaje_cliente_pedido_listo_saldo = models.TextField(
        blank=True,
        default=(
            "Hola {nombre} 👋 Tu pedido de Doble V 3D ya está listo.\n\n"
            "{pedido}\n\n"
            "{datos_pago}\n\n"
            "{cierre}"
        ),
        verbose_name="Mensaje de pedido listo con saldo",
        help_text=(
            "Se usa automáticamente cuando un pedido LISTO todavía tiene saldo. "
            "Podés usar {nombre}, {pedido}, {codigo}, {url}, {total}, {pagado}, "
            "{saldo}, {cantidad_pagos}, {datos_pago}, {fecha_entrega} y {cierre}."
        ),
    )
    whatsapp_mensaje_cliente_saldo = models.TextField(
        blank=True,
        default=(
            "Hola {nombre} 👋 Te escribo por tu pedido de Doble V 3D.\n\n"
            "{pedido}\n\n"
            "{datos_pago}\n\n"
            "{cierre}"
        ),
        verbose_name="Mensaje de saldo pendiente",
        help_text=(
            "Podés usar {nombre}, {pedido}, {codigo}, {url}, {saldo}, {total}, "
            "{pagado}, {cantidad_pagos}, {datos_pago} y {cierre}. Se usa para pedidos en "
            "preparación o entregados que todavía tienen saldo."
        ),
    )
    whatsapp_mensaje_cliente_multiples_pedidos = models.TextField(
        blank=True,
        default=(
            "Hola {nombre} 👋 Te paso el estado de tus {cantidad_pedidos} "
            "pedidos de Doble V 3D:\n\n"
            "{pedidos}\n\n"
            "{saldo_resumen}\n\n"
            "{datos_pago}\n\n"
            "{cierre}"
        ),
        verbose_name="Mensaje de múltiples pedidos",
        help_text=(
            "Podés usar {nombre}, {cantidad_pedidos}, {pedidos}, {saldo_total}, "
            "{saldo_resumen}, {datos_pago}, {cantidad_listos}, {cantidad_con_saldo} y {cierre}. "
            "{pedidos} "
            "incluye estado, cantidad de pagos, total pagado, saldo y URL "
            "individual de cada pedido."
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

    razon_social = models.CharField(
        max_length=180,
        blank=True,
        default="",
        verbose_name="Razón social / nombre del responsable",
    )
    cuit = models.CharField(
        max_length=20,
        blank=True,
        default="",
        verbose_name="CUIT",
    )
    domicilio_legal = models.CharField(
        max_length=240,
        blank=True,
        default="",
        verbose_name="Domicilio comercial / legal",
    )
    email_legal = models.EmailField(
        blank=True,
        default="",
        verbose_name="Email de contacto legal",
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
        cache.delete("dv-redondeo-precio-producto-v1")
        cache.delete("dv-incremento-insumos-v1")



def redondeo_precio_producto_actual():
    cache_key = "dv-redondeo-precio-producto-v1"
    valor = cache.get(cache_key)
    if valor is None:
        valor = (
            ConfiguracionCatalogo.objects
            .filter(pk=1)
            .values_list("redondeo_precio_producto", flat=True)
            .first()
        )
        try:
            valor = int(valor or 100)
        except (TypeError, ValueError):
            valor = 100
        valor = max(valor, 100)
        cache.set(cache_key, valor, 60)
    return Decimal(valor)


def incremento_insumos_actual():
    cache_key = "dv-incremento-insumos-v1"
    valor = cache.get(cache_key)
    if valor is None:
        valor = (
            ConfiguracionCatalogo.objects
            .filter(pk=1)
            .values_list("incremento_insumos_por_defecto", flat=True)
            .first()
        )
        try:
            valor = Decimal(str(valor if valor is not None else "10"))
        except Exception:
            valor = Decimal("10")
        valor = max(valor, Decimal("0"))
        cache.set(cache_key, valor, 60)
    return Decimal(str(valor))


class SolicitudArrepentimiento(models.Model):
    ESTADOS = [
        ("NUEVA", "Nueva"),
        ("RESUELTA", "Resuelta"),
    ]

    nombre = models.CharField(
        max_length=150,
        blank=True,
    )
    contacto = models.CharField(
        max_length=180,
        help_text="WhatsApp o email para responder la solicitud.",
    )
    referencia = models.CharField(
        max_length=80,
        blank=True,
        help_text="Pedido, presupuesto o comprobante si el cliente lo conoce.",
    )
    detalle = models.TextField(
        blank=True,
    )
    estado = models.CharField(
        max_length=20,
        choices=ESTADOS,
        default="NUEVA",
    )
    creada_en = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-creada_en", "-id"]

    @property
    def codigo(self):
        return f"ARR{self.id:04d}" if self.id else "ARR-NUEVA"

    def __str__(self):
        return f"{self.codigo} · {self.contacto}"

class Insumo(models.Model):
    TIPOS_USO = [
        ("PRODUCTO", "Producto"),
        ("EMPAQUE", "Empaque"),
        ("DESPACHO", "Despacho"),
    ]
    UNIDADES_MEDIDA = [
        ("UNIDAD", "Unidad"),
        ("METRO", "Metro"),
        ("GRAMO", "Gramo"),
        ("MILILITRO", "Mililitro"),
    ]

    nombre = models.CharField(max_length=160, unique=True)
    tipo_uso = models.CharField(
        max_length=20,
        choices=TIPOS_USO,
        default="PRODUCTO",
    )
    unidad_medida = models.CharField(
        max_length=20,
        choices=UNIDADES_MEDIDA,
        default="UNIDAD",
    )
    precio_compra = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Precio total pagado por la compra o presentación.",
    )
    cantidad_compra = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=1,
        help_text="Cantidad de unidades base incluidas en el precio de compra.",
    )
    stock = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=0,
        help_text="Stock disponible expresado en la unidad base.",
    )
    proveedor = models.CharField(
        max_length=160,
        blank=True,
        default="",
    )
    url_referencia = models.URLField(
        max_length=500,
        blank=True,
        default="",
    )
    incremento_personalizado = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text=(
            "Si se deja vacío, utiliza el incremento general configurado "
            "para todos los insumos."
        ),
    )
    precio_actualizado_en = models.DateTimeField(
        default=timezone.now,
    )
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-activo", "tipo_uso", "nombre"]

    def __str__(self):
        return f"{self.codigo} - {self.nombre}" if self.pk else self.nombre

    @property
    def codigo(self):
        return f"I{self.id:04d}" if self.id else "I-NUEVO"

    @property
    def costo_unitario(self):
        cantidad = Decimal(str(self.cantidad_compra or 0))
        if cantidad <= 0:
            return Decimal("0")
        return Decimal(str(self.precio_compra or 0)) / cantidad

    @property
    def incremento_efectivo(self):
        if self.incremento_personalizado is not None:
            return max(
                Decimal(str(self.incremento_personalizado)),
                Decimal("0"),
            )
        return incremento_insumos_actual()

    @property
    def usa_incremento_general(self):
        return self.incremento_personalizado is None

    @property
    def costo_unitario_aplicado(self):
        porcentaje = self.incremento_efectivo / Decimal("100")
        return self.costo_unitario * (Decimal("1") + porcentaje)


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
    permite_elegir_color = models.BooleanField(
        default=False,
        help_text=(
            "Permite elegir un color específico en la tienda. "
            "No agrega costo en productos individuales."
        ),
    )
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

    @property
    def descripcion_componentes_catalogo(self):
        """Resumen corto y legible de las piezas que forman un producto compuesto."""
        if not self.es_compuesto or not self.pk:
            return ""

        partes = []
        for relacion in self._relaciones_componentes():
            cantidad = max(int(relacion.cantidad or 0), 0)
            if cantidad <= 0:
                continue
            nombre = (relacion.componente.nombre or "").strip()
            if not nombre:
                continue
            partes.append(f"{cantidad}× {nombre}")

        return "Incluye: " + " + ".join(partes) if partes else ""

    def _relaciones_componentes(self):
        if not self.pk or not self.es_compuesto:
            return []

        # El catálogo precarga componentes y sus productos. Reutilizar ese
        # cache evita repetir queries cada vez que costo, seguro o subtotal
        # vuelven a recorrer la composición del mismo producto.
        prefetched = getattr(self, "_prefetched_objects_cache", {})
        if "componentes" in prefetched:
            return prefetched["componentes"]

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
        # La configuración de costos se consulta muchas veces al renderizar
        # el catálogo. Un TTL corto evita repetir la misma query por producto
        # sin dejar precios desactualizados durante más de unos segundos.
        cache_key = "dv-configuracion-costos-activa-v1"
        sentinel = object()
        config = cache.get(cache_key, sentinel)
        if config is sentinel:
            config = (
                ConfiguracionCostos.objects
                .filter(activa=True)
                .order_by("-fecha_desde")
                .first()
            )
            cache.set(cache_key, config, 15)
        return config

    def _relaciones_insumos_directos(self):
        if not self.pk:
            return []

        prefetched = getattr(self, "_prefetched_objects_cache", {})
        if "insumos_asignados" in prefetched:
            return prefetched["insumos_asignados"]

        return self.insumos_asignados.select_related("insumo").all()

    @property
    def costo_insumos_directos(self):
        total = Decimal("0")
        for relacion in self._relaciones_insumos_directos():
            total += Decimal(str(relacion.costo_total or 0))
        return total

    @property
    def costo_insumos_componentes(self):
        if not self.es_compuesto or not self.pk:
            return Decimal("0")

        total = Decimal("0")
        for relacion in self._relaciones_componentes():
            total += (
                Decimal(str(relacion.componente.costo_insumos_total or 0))
                * Decimal(int(relacion.cantidad or 0))
            )
        return total

    @property
    def costo_insumos_total(self):
        return (
            self.costo_insumos_directos
            + self.costo_insumos_componentes
        )

    @property
    def costo_productivo_total(self):
        return (
            Decimal(str(self.costo or 0))
            + Decimal(str(self.seguro or 0))
            + Decimal(str(self.costo_insumos_total or 0))
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
        if (
            not self.requiere_impresion
            and self.costo_insumos_total <= 0
        ):
            return Decimal("0")

        margen = self.margen_ganancia / Decimal("100")
        if margen >= Decimal("1"):
            return Decimal("0")

        # El margen se aplica sobre TODO el costo productivo. Antes se
        # calculaba sólo sobre self.costo y luego se sumaba self.seguro,
        # por lo que un producto configurado al 60% podía terminar con un
        # margen real inferior. Seguro, amortización y provisión por fallos
        # deben formar parte de la base sobre la que se protege el margen.
        costo_productivo = self.costo_productivo_total
        precio_sin_redondear = (
            costo_productivo
            / (Decimal("1") - margen)
        )

        # El múltiplo comercial se administra desde Configuración.
        # El redondeo siempre es hacia arriba, para no degradar el margen.
        multiplo = redondeo_precio_producto_actual()
        return (
            (precio_sin_redondear / multiplo)
            .to_integral_value(rounding=ROUND_CEILING)
            * multiplo
        )

    @property
    def ganancia(self):
        return self.subtotal - self.costo_productivo_total

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



class ProductoInsumo(models.Model):
    producto = models.ForeignKey(
        Producto,
        on_delete=models.CASCADE,
        related_name="insumos_asignados",
    )
    insumo = models.ForeignKey(
        Insumo,
        on_delete=models.PROTECT,
        related_name="productos_asignados",
    )
    cantidad = models.DecimalField(
        max_digits=12,
        decimal_places=3,
        default=1,
        help_text="Cantidad de unidad base consumida por cada unidad del producto.",
    )

    class Meta:
        ordering = ["insumo__nombre"]
        constraints = [
            models.UniqueConstraint(
                fields=["producto", "insumo"],
                name="producto_insumo_unico",
            )
        ]

    @property
    def costo_unitario_aplicado(self):
        return Decimal(str(self.insumo.costo_unitario_aplicado or 0))

    @property
    def costo_total(self):
        return (
            self.costo_unitario_aplicado
            * Decimal(str(self.cantidad or 0))
        )

    def __str__(self):
        return (
            f"{self.producto.nombre} · {self.insumo.nombre} "
            f"x{self.cantidad}"
        )

    def save(self, *args, **kwargs):
        if self.insumo.tipo_uso != "PRODUCTO":
            raise ValueError(
                "Sólo los insumos de tipo Producto pueden asignarse directamente."
            )
        if Decimal(str(self.cantidad or 0)) <= 0:
            raise ValueError("La cantidad del insumo debe ser mayor a cero.")
        super().save(*args, **kwargs)
