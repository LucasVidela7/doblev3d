import json
from decimal import Decimal

from django.core.management.base import BaseCommand

from calculadora.precios import MARGEN_MINIMO
from costos.models import ConfiguracionCostos
from kits.engine import KitEngine
from kits.models import Kit
from pedidos.kits_volumen import _costo_unitario_volumen


CANTIDADES = (1, 2, 3, 4, 5, 6, 8, 10)


def d(value):
    return Decimal(str(value or 0))


def j(value):
    if isinstance(value, Decimal):
        return float(value)
    return value


class Command(BaseCommand):
    help = "Auditoría READ-ONLY de rentabilidad real para kits x2/x4/x6."

    def _emit(self, marker, payload):
        self.stdout.write(
            f"{marker} "
            + json.dumps(
                payload,
                ensure_ascii=False,
                default=j,
                sort_keys=True,
            )
        )

    def _costo_producto(self, producto):
        return max(
            d(_costo_unitario_volumen(producto, 1)),
            Decimal("0"),
        )

    def _peor_con_limite(
        self,
        productos,
        extras,
        costos,
        n,
        base,
        max_repeticiones,
    ):
        max_repeticiones = max(int(max_repeticiones or 1), 1)
        slots = [
            producto
            for producto in productos
            for _ in range(max_repeticiones)
        ]
        if len(slots) < n:
            return None

        lam = Decimal("0")
        seleccion = slots[:n]
        ids_previos = None

        for _ in range(40):
            ordenados = sorted(
                slots,
                key=lambda p: (
                    costos[p.id] - lam * extras[p.id],
                    costos[p.id],
                    -p.id,
                ),
                reverse=True,
            )
            seleccion = ordenados[:n]
            costo = sum(
                (costos[p.id] for p in seleccion),
                Decimal("0"),
            )
            precio = base + sum(
                (extras[p.id] for p in seleccion),
                Decimal("0"),
            )
            if precio <= 0:
                break
            nueva = costo / precio
            ids = tuple(sorted(p.id for p in seleccion))
            if (
                ids == ids_previos
                and abs(nueva - lam) < Decimal("0.0000001")
            ):
                break
            ids_previos = ids
            lam = nueva

        return seleccion

    def _escenarios_libres(self, kit, productos):
        n = int(kit.cantidad_productos or 0)
        opciones = KitEngine.opciones(
            kit,
            productos_categoria=productos,
        )
        por_id = {
            item["producto_id"]: item
            for item in opciones.get("opciones", [])
        }
        extras = {
            p.id: d(por_id.get(p.id, {}).get("extra"))
            for p in productos
        }
        costos = {
            p.id: self._costo_producto(p)
            for p in productos
        }

        escenarios = {}
        max_repeticiones = max(
            int(
                getattr(
                    kit,
                    "max_repeticiones_producto",
                    1,
                )
                or 1
            ),
            1,
        )

        if len(productos) >= n and n > 0:
            baratos = sorted(
                productos,
                key=lambda p: (costos[p.id], p.id),
            )[:n]
            caros = sorted(
                productos,
                key=lambda p: (costos[p.id], -p.id),
                reverse=True,
            )[:n]
            escenarios["mas_barato_distinto"] = baratos
            escenarios["mas_caro_distinto"] = caros

        peor_permitido = self._peor_con_limite(
            productos,
            extras,
            costos,
            n,
            d(kit.precio),
            max_repeticiones,
        )
        if peor_permitido:
            escenarios["peor_margen_permitido"] = peor_permitido

        return escenarios, costos, extras, opciones

    def _evaluar(self, kit, nombre_escenario, seleccion, cantidad):
        precio_lista_unitario = (
            d(KitEngine.precio_unitario(kit, productos=seleccion))
            if kit.modalidad == "LIBRE_CATEGORIA"
            else d(kit.precio)
        )
        componentes = KitEngine.componentes(
            kit,
            productos=seleccion,
            cantidad_kits=cantidad,
        )
        resumen = KitEngine.volumen(
            [
                {
                    "key": f"{kit.id}-{nombre_escenario}-{cantidad}",
                    "kit": kit,
                    "cantidad": cantidad,
                    "precio_unitario_lista": precio_lista_unitario,
                    "componentes": componentes,
                }
            ]
        )
        linea = resumen["lineas"][0]
        costo_total = d(linea["costo_total"])
        final_total = d(linea["precio_final_total"])
        lista_total = d(linea["precio_lista_total"])
        ganancia_total = final_total - costo_total
        margen = (
            ganancia_total / final_total * Decimal("100")
            if final_total > 0
            else Decimal("-999")
        ).quantize(Decimal("0.1"))
        cantidad_d = Decimal(cantidad)

        return {
            "kit_id": kit.id,
            "kit": kit.nombre,
            "x": int(kit.cantidad_productos or 0),
            "escenario": nombre_escenario,
            "cantidad_kits": cantidad,
            "seleccion": (
                [p.nombre for p in seleccion]
                if seleccion is not None
                else [
                    f"{c.producto.nombre} x{c.cantidad}"
                    for c in kit.componentes.all()
                ]
            ),
            "precio_lista_unitario": (lista_total / cantidad_d).quantize(Decimal("0.01")),
            "descuento_pct": d(linea["descuento_porcentaje"]),
            "precio_final_unitario": (final_total / cantidad_d).quantize(Decimal("0.01")),
            "costo_unitario": (costo_total / cantidad_d).quantize(Decimal("0.01")),
            "ganancia_unitaria": (ganancia_total / cantidad_d).quantize(Decimal("0.01")),
            "margen_real_pct": margen,
            "precio_total": final_total.quantize(Decimal("0.01")),
            "costo_total": costo_total.quantize(Decimal("0.01")),
            "ganancia_total": ganancia_total.quantize(Decimal("0.01")),
            "debajo_piso": margen < MARGEN_MINIMO,
        }

    def _equivalencia_x4(self, kit, selecciones):
        if not selecciones:
            return None

        base = selecciones[0]
        agrupado = self._evaluar(
            kit,
            "equivalencia_agrupado",
            base if kit.modalidad == "LIBRE_CATEGORIA" else None,
            4,
        )

        items = []
        usadas = []
        for indice in range(4):
            seleccion = (
                selecciones[indice % len(selecciones)]
                if kit.modalidad == "LIBRE_CATEGORIA"
                else None
            )
            precio = (
                d(KitEngine.precio_unitario(kit, productos=seleccion))
                if kit.modalidad == "LIBRE_CATEGORIA"
                else d(kit.precio)
            )
            items.append(
                {
                    "key": f"sep-{kit.id}-{indice}",
                    "kit": kit,
                    "cantidad": 1,
                    "precio_unitario_lista": precio,
                    "componentes": KitEngine.componentes(
                        kit,
                        productos=seleccion,
                        cantidad_kits=1,
                    ),
                }
            )
            usadas.append(
                [p.nombre for p in seleccion]
                if seleccion is not None
                else ["composición fija"]
            )

        separado = KitEngine.volumen(items)
        descuentos = sorted(
            {
                str(d(linea["descuento_porcentaje"]).quantize(Decimal("0.1")))
                for linea in separado["lineas"]
            }
        )
        esperado = str(d(agrupado["descuento_pct"]).quantize(Decimal("0.1")))

        return {
            "kit_id": kit.id,
            "kit": kit.nombre,
            "descuento_agrupado_pct": esperado,
            "descuentos_separados_pct": descuentos,
            "coincide": descuentos == [esperado],
            "selecciones_separadas": usadas,
        }

    def handle(self, *args, **options):
        self.stdout.write("AUDIT_KITS_START")

        config = (
            ConfiguracionCostos.objects
            .filter(activa=True)
            .order_by("-fecha_desde")
            .first()
        )
        self._emit(
            "AUDIT_CONFIG",
            {
                "config_costos_id": getattr(config, "id", None),
                "config_costos_nombre": getattr(config, "nombre", None),
                "fecha_desde": str(getattr(config, "fecha_desde", "") or ""),
                "margen_minimo_pct": MARGEN_MINIMO,
                "cantidades": CANTIDADES,
                "solo_lectura": True,
            },
        )

        kits = list(
            Kit.objects
            .filter(
                activo=True,
                cantidad_productos__in=(2, 4, 6),
            )
            .select_related("tipo_producto")
            .prefetch_related("componentes__producto")
            .order_by("cantidad_productos", "nombre")
        )

        peor_global = None
        issues = []

        for kit in kits:
            self._emit(
                "AUDIT_KIT",
                {
                    "id": kit.id,
                    "codigo": kit.codigo,
                    "nombre": kit.nombre,
                    "x": kit.cantidad_productos,
                    "modalidad": kit.modalidad,
                    "precio_base": kit.precio,
                    "tipo": (
                        kit.tipo_producto.nombre
                        if kit.tipo_producto_id
                        else None
                    ),
                    "proteger_rentabilidad": kit.proteger_rentabilidad_libre,
                    "max_repeticiones_producto": (
                        kit.max_repeticiones_producto
                    ),
                },
            )

            escenarios = {}
            selecciones_equivalencia = []

            if kit.modalidad == "LIBRE_CATEGORIA":
                productos = KitEngine.productos_categoria(kit)
                if not productos:
                    issues.append(
                        f"{kit.nombre}: sin productos activos elegibles."
                    )
                    continue

                escenarios, costos, extras, opciones = self._escenarios_libres(
                    kit,
                    productos,
                )

                for producto in productos:
                    self._emit(
                        "AUDIT_PRODUCT",
                        {
                            "kit_id": kit.id,
                            "producto_id": producto.id,
                            "codigo": producto.codigo,
                            "producto": producto.nombre,
                            "costo_productivo": costos[producto.id],
                            "margen_configurado_pct": producto.margen_ganancia,
                            "extra_kit": extras[producto.id],
                            "peso_g": producto.peso_gramos,
                            "horas": producto.horas,
                            "minutos": producto.minutos,
                        },
                    )
                    if costos[producto.id] <= 0 and producto.requiere_impresion:
                        issues.append(
                            f"{kit.nombre} / {producto.nombre}: costo productivo 0."
                        )

                if len(productos) < int(kit.cantidad_productos or 0):
                    issues.append(
                        f"{kit.nombre}: sólo {len(productos)} productos activos "
                        f"para {kit.cantidad_productos} lugares distintos."
                    )

                selecciones_equivalencia = list(escenarios.values())
            else:
                if not list(kit.componentes.all()):
                    issues.append(f"{kit.nombre}: kit fijo sin componentes.")
                    continue
                escenarios = {"composicion_fija": None}
                selecciones_equivalencia = [None]

            for nombre_escenario, seleccion in escenarios.items():
                for cantidad in CANTIDADES:
                    fila = self._evaluar(
                        kit,
                        nombre_escenario,
                        seleccion,
                        cantidad,
                    )
                    self._emit("AUDIT_SCENARIO", fila)
                    if (
                        peor_global is None
                        or d(fila["margen_real_pct"])
                        < d(peor_global["margen_real_pct"])
                    ):
                        peor_global = fila

            equivalencia = self._equivalencia_x4(
                kit,
                selecciones_equivalencia,
            )
            if equivalencia:
                self._emit("AUDIT_EQUIV_X4", equivalencia)
                if not equivalencia["coincide"]:
                    issues.append(
                        f"{kit.nombre}: x4 separado no coincide con qty=4."
                    )

        for issue in issues:
            self._emit("AUDIT_ISSUE", {"detalle": issue})

        if peor_global:
            self._emit("AUDIT_WORST", peor_global)

        self._emit(
            "AUDIT_SUMMARY",
            {
                "kits_evaluados": len(kits),
                "issues": len(issues),
                "peor_margen_pct": (
                    peor_global["margen_real_pct"]
                    if peor_global
                    else None
                ),
                "peor_debajo_piso": (
                    peor_global["debajo_piso"]
                    if peor_global
                    else None
                ),
            },
        )
        self.stdout.write("AUDIT_KITS_END")
