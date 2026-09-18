from decimal import Decimal, ROUND_CEILING

from django.db import models

from calculadora.precios import MARGEN_MINIMO
from productos.models import Producto, TipoProducto


MARGEN_MINIMO_KIT = MARGEN_MINIMO
MULTIPLO_PRECIO_KIT = Decimal("500")


class Kit(models.Model):

    MODALIDADES = [
        (
            "LIBRE_CATEGORIA",
            "Libre por categoría",
        ),
        (
            "FIJO",
            "Composición fija",
        ),
    ]

    nombre = models.CharField(
        max_length=150,
        unique=True,
    )

    modalidad = models.CharField(
        max_length=30,
        choices=MODALIDADES,
        default="LIBRE_CATEGORIA",
    )

    # Para los kits LIBRE_CATEGORIA define qué productos
    # puede elegir el usuario.
    #
    # Para los kits FIJO puede quedar vacío porque la receta
    # se define en KitComponente.
    tipo_producto = models.ForeignKey(
        TipoProducto,
        on_delete=models.PROTECT,
        related_name="kits",
        null=True,
        blank=True,
    )

    # Se conserva por compatibilidad con los kits actuales.
    # En LIBRE_CATEGORIA indica cuántos productos elige el usuario.
    # En FIJO se sincroniza desde la suma de los componentes.
    cantidad_productos = models.PositiveIntegerField(
        default=1,
    )

    precio = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    proteger_rentabilidad_libre = models.BooleanField(
        default=False,
        help_text=(
            "En kits libres, separa opciones incluidas de opciones premium "
            "con extra según la calculadora de costos."
        ),
    )

    activo = models.BooleanField(
        default=True,
    )

    @property
    def codigo(self):
        return f"K{self.id:04d}" if self.id else "NUEVO"

    @property
    def cantidad_componentes_fijos(self):
        if not self.id:
            return 0

        return sum(
            componente.cantidad
            for componente in self.componentes.all()
        )

    @staticmethod
    def _costo_operativo_producto(producto):
        """Costo actual + cobertura productiva del producto."""
        costo = Decimal(str(producto.costo or 0))
        seguro = Decimal(str(producto.seguro or 0))
        return max(costo + seguro, Decimal("0"))

    def _componentes_para_analisis(self):
        if not self.pk:
            return []

        cache = getattr(
            self,
            "_prefetched_objects_cache",
            {},
        )

        if "componentes" in cache:
            return list(cache["componentes"])

        return list(
            self.componentes
            .select_related("producto")
            .all()
        )

    def _margen_sobre_precio(self, costo):
        precio = Decimal(str(self.precio or 0))
        if precio <= 0:
            return None

        return (
            (precio - Decimal(str(costo or 0)))
            / precio
            * Decimal("100")
        ).quantize(Decimal("0.1"))

    @staticmethod
    def _redondear_precio(valor):
        valor = Decimal(str(valor or 0))
        if valor <= 0:
            return Decimal("0")

        return (
            (valor / MULTIPLO_PRECIO_KIT)
            .to_integral_value(rounding=ROUND_CEILING)
            * MULTIPLO_PRECIO_KIT
        )

    @classmethod
    def _precio_para_margen_minimo(cls, costo):
        costo = Decimal(str(costo or 0))
        if costo <= 0:
            return Decimal("0")

        proporcion = Decimal("1") - (
            MARGEN_MINIMO_KIT / Decimal("100")
        )

        if proporcion <= 0:
            return Decimal("0")

        return cls._redondear_precio(
            costo / proporcion
        )

    @property
    def analisis_economico(self):
        """
        Calcula la rentabilidad del kit con costos actuales.

        - FIJO: el costo y margen son exactos según la receta.
        - LIBRE_CATEGORIA: usa el promedio de la categoría como estimación
          y el producto más costoso como escenario conservador.

        El precio queda marcado para revisión cuando el peor escenario
        cae por debajo del piso operativo definido en MARGEN_MINIMO_KIT.
        """
        precio = Decimal(str(self.precio or 0))

        resultado = {
            "tipo_calculo": (
                "EXACTO"
                if self.modalidad == "FIJO"
                else "ESTIMADO"
            ),
            "costo_estimado": Decimal("0"),
            "costo_peor_caso": Decimal("0"),
            "margen_estimado": None,
            "margen_peor_caso": None,
            "precio_sugerido_minimo": Decimal("0"),
            "margen_minimo": MARGEN_MINIMO_KIT,
            "alerta": False,
            "motivo": "",
        }

        if precio <= 0:
            resultado["alerta"] = True
            resultado["motivo"] = (
                "El kit no tiene un precio de venta válido."
            )
            return resultado

        if self.modalidad == "FIJO":
            componentes = self._componentes_para_analisis()

            if not componentes:
                resultado["alerta"] = True
                resultado["motivo"] = (
                    "El kit no tiene componentes configurados."
                )
                return resultado

            costo = Decimal("0")

            for componente in componentes:
                cantidad = Decimal(
                    int(componente.cantidad or 0)
                )
                costo += (
                    self._costo_operativo_producto(
                        componente.producto
                    )
                    * cantidad
                )

            resultado["costo_estimado"] = costo
            resultado["costo_peor_caso"] = costo

        else:
            if (
                not self.tipo_producto_id
                or self.cantidad_productos <= 0
            ):
                resultado["alerta"] = True
                resultado["motivo"] = (
                    "El kit libre no tiene categoría o cantidad válida."
                )
                return resultado

            productos = list(
                Producto.objects
                .filter(
                    tipo_id=self.tipo_producto_id,
                    activo=True,
                    solo_produccion=False,
                )
                .order_by("id")
            )

            if not productos:
                resultado["alerta"] = True
                resultado["motivo"] = (
                    "No hay productos activos disponibles en la categoría."
                )
                return resultado

            costos = [
                self._costo_operativo_producto(producto)
                for producto in productos
            ]

            cantidad = Decimal(
                int(self.cantidad_productos or 0)
            )
            costo_promedio = (
                sum(costos, Decimal("0"))
                / Decimal(len(costos))
            ) * cantidad
            costo_peor = max(costos) * cantidad

            resultado["costo_estimado"] = costo_promedio
            resultado["costo_peor_caso"] = costo_peor

        resultado["margen_estimado"] = (
            self._margen_sobre_precio(
                resultado["costo_estimado"]
            )
        )
        resultado["margen_peor_caso"] = (
            self._margen_sobre_precio(
                resultado["costo_peor_caso"]
            )
        )
        resultado["precio_sugerido_minimo"] = (
            self._precio_para_margen_minimo(
                resultado["costo_peor_caso"]
            )
        )

        margen_referencia = resultado[
            "margen_peor_caso"
        ]

        if (
            margen_referencia is not None
            and margen_referencia < MARGEN_MINIMO_KIT
        ):
            resultado["alerta"] = True

            if margen_referencia < 0:
                resultado["motivo"] = (
                    "El precio actual no cubre el costo operativo del kit."
                )
            else:
                resultado["motivo"] = (
                    f"El margen cae a {margen_referencia}% y está por debajo "
                    f"del piso de {MARGEN_MINIMO_KIT}%."
                )

        return resultado

    def __str__(self):
        return self.nombre

    class Meta:
        ordering = ["nombre"]


class KitComponente(models.Model):

    kit = models.ForeignKey(
        Kit,
        on_delete=models.CASCADE,
        related_name="componentes",
    )

    producto = models.ForeignKey(
        Producto,
        on_delete=models.PROTECT,
        related_name="kits_fijos",
    )

    cantidad = models.PositiveIntegerField(
        default=1,
    )

    def __str__(self):
        return (
            f"{self.kit.nombre} · "
            f"{self.producto.nombre} x{self.cantidad}"
        )

    class Meta:
        ordering = [
            "producto__nombre",
        ]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "kit",
                    "producto",
                ],
                name="kit_producto_fijo_unico",
            )
        ]
