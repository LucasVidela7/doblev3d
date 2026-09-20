from collections import Counter
from decimal import Decimal

from productos.models import Producto

from .economia import (
    analizar_opciones_kit,
    precio_automatico_kit_libre,
    recomendacion_kit,
)


class KitEngine:
    """Punto único de entrada para reglas comerciales y operativas de Kits.

    La implementación delega en los cálculos vigentes para preservar
    exactamente el comportamiento actual mientras centraliza su consumo.
    """

    @staticmethod
    def productos_categoria(kit):
        if not kit.tipo_producto_id:
            return []

        return list(
            Producto.objects
            .filter(
                tipo_id=kit.tipo_producto_id,
                activo=True,
                solo_produccion=False,
            )
            .select_related("tipo")
            .order_by("nombre", "id")
        )

    @classmethod
    def opciones(cls, kit, productos_categoria=None):
        productos = (
            list(productos_categoria)
            if productos_categoria is not None
            else cls.productos_categoria(kit)
        )
        return analizar_opciones_kit(
            kit,
            productos_categoria=productos,
        )

    @classmethod
    def recomendacion(cls, kit, productos_categoria=None):
        productos = productos_categoria

        if (
            productos is None
            and kit.modalidad == "LIBRE_CATEGORIA"
        ):
            productos = cls.productos_categoria(kit)

        if (
            kit.modalidad == "LIBRE_CATEGORIA"
            and getattr(
                kit,
                "proteger_rentabilidad_libre",
                False,
            )
            and productos is not None
        ):
            analisis = cls.opciones(
                kit,
                productos_categoria=productos,
            )
            incluidos = [
                item["producto"]
                for item in analisis["incluidos"]
            ]
            if incluidos:
                productos = incluidos

        return recomendacion_kit(
            kit,
            productos_categoria=productos,
        )

    @classmethod
    def validar_configuracion(cls, kit):
        errores = []

        if not str(getattr(kit, "nombre", "") or "").strip():
            errores.append("El kit no tiene nombre.")

        if Decimal(str(getattr(kit, "precio", 0) or 0)) <= 0:
            errores.append("El kit no tiene un precio válido.")

        if kit.modalidad == "FIJO":
            componentes = list(kit.componentes.all()) if kit.pk else []
            if not componentes:
                errores.append(
                    "El kit fijo no tiene componentes configurados."
                )
            elif any(int(item.cantidad or 0) <= 0 for item in componentes):
                errores.append(
                    "Hay componentes con cantidades inválidas."
                )
        else:
            if not kit.tipo_producto_id:
                errores.append(
                    "El kit libre no tiene categoría configurada."
                )
            if int(kit.cantidad_productos or 0) <= 0:
                errores.append(
                    "La cantidad a elegir debe ser mayor a cero."
                )
            if kit.tipo_producto_id:
                productos = cls.productos_categoria(kit)
                if not productos:
                    errores.append(
                        "La categoría no tiene productos comerciales activos."
                    )

        return {
            "valido": not errores,
            "errores": errores,
        }

    @classmethod
    def estado_salud(cls, kit, productos_categoria=None):
        configuracion = cls.validar_configuracion(kit)

        if not configuracion["valido"]:
            return {
                "codigo": "CONFIGURACION",
                "etiqueta": "CONFIGURACIÓN",
                "nivel": "danger",
                "detalle": configuracion["errores"][0],
                "errores": configuracion["errores"],
            }

        recomendacion = cls.recomendacion(
            kit,
            productos_categoria=productos_categoria,
        )

        if not recomendacion["disponible"]:
            return {
                "codigo": "CONFIGURACION",
                "etiqueta": "CONFIGURACIÓN",
                "nivel": "danger",
                "detalle": recomendacion["motivo"],
                "errores": [recomendacion["motivo"]],
            }

        if (
            recomendacion["margen_peor_caso"] is not None
            and recomendacion["margen_peor_caso"] < 0
        ):
            return {
                "codigo": "RIESGO",
                "etiqueta": "MARGEN NEGATIVO",
                "nivel": "danger",
                "detalle": recomendacion["motivo"],
                "errores": [],
            }

        if recomendacion["estado"] == "REVISAR":
            return {
                "codigo": "PRECIO",
                "etiqueta": "REVISAR PRECIO",
                "nivel": "danger",
                "detalle": recomendacion["motivo"],
                "errores": [],
            }

        if recomendacion["estado"] == "ADVERTENCIA":
            return {
                "codigo": "PRECIO",
                "etiqueta": "PRECIO",
                "nivel": "warning",
                "detalle": recomendacion["motivo"],
                "errores": [],
            }

        if kit.modalidad == "LIBRE_CATEGORIA":
            opciones = cls.opciones(
                kit,
                productos_categoria=productos_categoria,
            )
            if (
                kit.proteger_rentabilidad_libre
                and opciones["disponible"]
                and opciones["cantidad_incluidos"] == 0
            ):
                return {
                    "codigo": "OPCIONES",
                    "etiqueta": "REVISAR OPCIONES",
                    "nivel": "warning",
                    "detalle": (
                        "La protección está activa pero todas las opciones "
                        "requieren adicional."
                    ),
                    "errores": [],
                }

        return {
            "codigo": "SALUDABLE",
            "etiqueta": "SALUDABLE",
            "nivel": "ok",
            "detalle": recomendacion["motivo"],
            "errores": [],
        }

    @classmethod
    def validar_seleccion(cls, kit, productos):
        seleccion = list(productos or [])

        if kit.modalidad == "FIJO":
            if seleccion:
                raise ValueError(
                    "Un kit fijo no admite una selección libre."
                )
            return []

        cantidad = int(kit.cantidad_productos or 0)
        if len(seleccion) != cantidad:
            raise ValueError(
                f"El kit {kit.nombre} necesita {cantidad} productos."
            )

        ids_validos = {
            producto.id
            for producto in cls.productos_categoria(kit)
        }

        invalidos = [
            producto
            for producto in seleccion
            if producto.id not in ids_validos
        ]
        if invalidos:
            raise ValueError(
                f"Hay productos que no están disponibles para {kit.nombre}."
            )

        return seleccion

    @classmethod
    def precio_unitario(cls, kit, productos=None):
        if kit.modalidad == "FIJO":
            return Decimal(str(kit.precio or 0))

        seleccion = cls.validar_seleccion(
            kit,
            productos,
        )
        return Decimal(
            str(
                precio_automatico_kit_libre(
                    kit,
                    seleccion,
                )
            )
        )

    @classmethod
    def componentes(cls, kit, productos=None, cantidad_kits=1):
        cantidad_kits = max(int(cantidad_kits or 0), 0)

        if kit.modalidad == "FIJO":
            return [
                {
                    "producto": componente.producto,
                    "cantidad": (
                        int(componente.cantidad or 0)
                        * cantidad_kits
                    ),
                }
                for componente in kit.componentes.all()
                if int(componente.cantidad or 0) > 0
            ]

        seleccion = cls.validar_seleccion(
            kit,
            productos,
        )
        conteo = Counter(
            producto.id
            for producto in seleccion
        )
        por_id = {
            producto.id: producto
            for producto in seleccion
        }

        return [
            {
                "producto": por_id[producto_id],
                "cantidad": veces * cantidad_kits,
            }
            for producto_id, veces in conteo.items()
        ]

    @staticmethod
    def _decimal_json(valor):
        if valor is None:
            return None
        return format(
            Decimal(str(valor)).normalize(),
            "f",
        )

    @classmethod
    def snapshot(
        cls,
        kit,
        *,
        cantidad_kits=1,
        precio_unitario=None,
        precio_manual=False,
        productos=None,
        componentes=None,
        costo_unitario=None,
    ):
        cantidad_kits = max(int(cantidad_kits or 1), 1)

        if componentes is None:
            componentes = cls.componentes(
                kit,
                productos=productos,
                cantidad_kits=cantidad_kits,
            )

        componentes_snapshot = []
        for item in componentes:
            producto = item["producto"]
            cantidad_total = int(item.get("cantidad") or 0)
            if cantidad_total <= 0:
                continue

            cantidad_por_kit = (
                Decimal(cantidad_total)
                / Decimal(cantidad_kits)
            )

            componentes_snapshot.append(
                {
                    "producto_id": producto.id,
                    "codigo": producto.codigo,
                    "nombre": producto.nombre,
                    "cantidad_total": cantidad_total,
                    "cantidad_por_kit": format(
                        cantidad_por_kit.normalize(),
                        "f",
                    ),
                }
            )

        recomendacion = cls.recomendacion(kit)
        salud = cls.estado_salud(kit)

        if precio_unitario is None:
            precio_unitario = (
                cls.precio_unitario(
                    kit,
                    productos=productos,
                )
                if kit.modalidad == "LIBRE_CATEGORIA"
                else Decimal(str(kit.precio or 0))
            )

        return {
            "version": 1,
            "kit_id": kit.id,
            "codigo": kit.codigo,
            "nombre": kit.nombre,
            "modalidad": kit.modalidad,
            "modalidad_display": kit.get_modalidad_display(),
            "tipo_producto_id": kit.tipo_producto_id,
            "tipo_producto": (
                kit.tipo_producto.nombre
                if kit.tipo_producto_id and kit.tipo_producto
                else ""
            ),
            "cantidad_configurada": int(
                kit.cantidad_productos or 0
            ),
            "proteger_rentabilidad": bool(
                getattr(
                    kit,
                    "proteger_rentabilidad_libre",
                    False,
                )
            ),
            "precio_base": cls._decimal_json(kit.precio),
            "precio_unitario_vendido": cls._decimal_json(
                precio_unitario
            ),
            "precio_manual": bool(precio_manual),
            "costo_unitario": cls._decimal_json(costo_unitario),
            "salud_al_vender": salud["codigo"],
            "precio_recomendado_al_vender": cls._decimal_json(
                recomendacion.get("precio_recomendado")
            ),
            "componentes": componentes_snapshot,
        }

    @staticmethod
    def volumen(items):
        # Import local para evitar dependencia circular al inicializar apps.
        from pedidos.kits_volumen import calcular_precio_volumen_kits

        return calcular_precio_volumen_kits(items)
