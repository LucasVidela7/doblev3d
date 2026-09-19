import json
from decimal import Decimal, ROUND_CEILING

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from calculadora.precios import (
    MARGEN_MINIMO,
    calcular_precio_catalogo_producto,
    fila_precio,
    margenes_escenario,
)
from productos.models import Producto

from .kits_volumen import (
    calcular_precio_volumen_kits,
    items_desde_payload,
    resumen_json,
)


def _componentes_producto(producto):
    if producto.tipo_fabricacion != "COMPUESTO":
        return []
    return producto.componentes.select_related("componente").all()


def _costos_producto(producto):
    """Devuelve costo de fabricación y seguro de forma robusta.

    En productos compuestos calcula directamente desde las piezas reales y
    sus cantidades. Así Nuevo Pedido y Editar Pedido no dependen de que los
    campos agregados del producto padre hayan quedado sincronizados.
    """
    if not producto.requiere_impresion:
        return Decimal("0"), Decimal("0")

    if producto.tipo_fabricacion == "COMPUESTO":
        costo = Decimal("0")
        seguro = Decimal("0")

        for relacion in _componentes_producto(producto):
            cantidad = Decimal(int(relacion.cantidad or 0))
            pieza = relacion.componente
            costo += Decimal(str(pieza.costo or 0)) * cantidad
            seguro += Decimal(str(pieza.seguro or 0)) * cantidad

        return max(costo, Decimal("0")), max(seguro, Decimal("0"))

    return (
        max(Decimal(str(producto.costo or 0)), Decimal("0")),
        max(Decimal(str(producto.seguro or 0)), Decimal("0")),
    )


def _precio_lista(producto, costo, seguro):
    """Calcula el precio de lista sin depender del resumen cacheado padre."""
    if not producto.requiere_impresion:
        return Decimal("0")

    if producto.tipo_fabricacion != "COMPUESTO":
        return Decimal(str(producto.subtotal or 0))

    margen = Decimal(str(producto.margen_ganancia or 0)) / Decimal("100")
    if margen >= Decimal("1"):
        return Decimal("0")

    ganancia_teorica = costo / (Decimal("1") - margen) - costo
    precio_sin_redondear = costo + seguro + ganancia_teorica
    multiplo = Decimal("500")

    return (
        (precio_sin_redondear / multiplo)
        .to_integral_value(rounding=ROUND_CEILING)
        * multiplo
    )


def _resumen_compuesto(producto):
    horas = Decimal("0")
    peso = Decimal("0")

    for relacion in _componentes_producto(producto):
        cantidad = Decimal(int(relacion.cantidad or 0))
        pieza = relacion.componente
        horas += pieza.horas_totales * cantidad
        peso += Decimal(str(pieza.peso_gramos or 0)) * cantidad

    horas_enteras = int(horas)
    minutos = int((horas - Decimal(horas_enteras)) * Decimal("60"))
    return horas_enteras, minutos, peso


def precio_producto(request):
    """API de precios usada por Nuevo Pedido y Editar Pedido."""
    if request.method != "GET":
        return JsonResponse(
            {"ok": False, "mensaje": "Método no permitido."},
            status=405,
        )

    producto_id = request.GET.get("producto_id", "").strip()
    cantidad_texto = request.GET.get("cantidad", "1").strip()

    try:
        cantidad = int(cantidad_texto)
    except (TypeError, ValueError):
        cantidad = 0

    if not producto_id or cantidad <= 0:
        return JsonResponse(
            {"ok": False, "mensaje": "Producto o cantidad no válidos."},
            status=400,
        )

    producto = get_object_or_404(
        Producto.objects.prefetch_related("componentes__componente"),
        id=producto_id,
        activo=True,
        solo_produccion=False,
    )

    costo, seguro = _costos_producto(producto)
    costo_productivo = max(costo + seguro, Decimal("0"))

    margen_tope = max(
        Decimal(str(producto.margen_ganancia or 0)),
        MARGEN_MINIMO,
    )
    margen_piso = MARGEN_MINIMO
    precio_lista = _precio_lista(producto, costo, seguro)

    margenes = margenes_escenario(cantidad, margen_tope)
    escenarios = {}

    for estrategia in ("conservador", "recomendado", "agresivo"):
        margen = Decimal(str(margenes[estrategia]))
        fila = fila_precio(costo_productivo, cantidad, margen)

        total_recomendado = Decimal(str(fila["total_recomendado"]))
        precio_unitario = Decimal(str(fila["precio_unitario"]))
        precio_unitario_pedido = (
            total_recomendado / Decimal(cantidad)
        ).quantize(Decimal("0.01"))

        escenarios[estrategia] = {
            "estrategia": estrategia,
            "margen": float(margen),
            "margen_objetivo": float(margen),
            "precio_unitario": float(precio_unitario),
            "total_recomendado": float(total_recomendado),
            "precio_unitario_pedido": float(precio_unitario_pedido),
            "total_pedido": float(total_recomendado),
        }

    if producto.tipo_fabricacion == "COMPUESTO":
        horas, minutos, peso_gramos = _resumen_compuesto(producto)
    else:
        horas = int(producto.horas or 0)
        minutos = int(producto.minutos or 0)
        peso_gramos = Decimal(str(producto.peso_gramos or 0))

    calculo_catalogo = calcular_precio_catalogo_producto(
        producto,
        cantidad,
    )
    catalogo_json = {
        "cantidad": calculo_catalogo["cantidad"],
        "precio_lista_unitario": float(
            calculo_catalogo["precio_lista_unitario"]
        ),
        "precio_lista_total": float(
            calculo_catalogo["precio_lista_total"]
        ),
        "precio_unitario": float(
            calculo_catalogo["precio_unitario"]
        ),
        "precio_final_total": float(
            calculo_catalogo["precio_final_total"]
        ),
        "ahorro": float(calculo_catalogo["ahorro"]),
        "descuento_porcentaje": float(
            calculo_catalogo["descuento_porcentaje"]
        ),
        "margen_real": float(
            calculo_catalogo["margen_real"]
        ),
        "ganancia": float(
            calculo_catalogo["ganancia"]
        ),
        "filamento_economico": bool(
            calculo_catalogo["filamento_economico"]
        ),
    }

    producto_json = {
        "id": producto.id,
        "codigo": producto.codigo,
        "nombre": producto.nombre,
        "precio_lista": float(precio_lista),
        "margen_tope": float(margen_tope),
        "margen_piso": float(margen_piso),
        "horas": horas,
        "minutos": minutos,
        "peso_gramos": float(peso_gramos),
        "tipo_fabricacion": producto.tipo_fabricacion,
        "es_compuesto": producto.tipo_fabricacion == "COMPUESTO",
    }

    return JsonResponse(
        {
            "ok": True,
            "producto": producto_json,
            "cantidad": cantidad,
            "precio_lista": float(precio_lista),
            "costo": float(costo),
            "seguro": float(seguro),
            "costo_productivo": float(costo_productivo),
            "margen_tope": float(margen_tope),
            "margen_piso": float(margen_piso),
            "catalogo": catalogo_json,
            # Se conservan temporalmente para compatibilidad con pantallas
            # históricas, pero la recomendación comercial vigente es catalogo.
            "escenarios": escenarios,
        }
    )


def precio_kits_volumen(request):
    """Vista previa del precio automático por volumen de kits del pedido."""
    if request.method != "POST":
        return JsonResponse(
            {"ok": False, "mensaje": "Método no permitido."},
            status=405,
        )

    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse(
            {"ok": False, "mensaje": "No se pudo leer la selección de kits."},
            status=400,
        )

    try:
        items = items_desde_payload(payload)
        resumen = calcular_precio_volumen_kits(items)
    except ValueError as exc:
        return JsonResponse(
            {"ok": False, "mensaje": str(exc)},
            status=400,
        )

    return JsonResponse(
        {
            "ok": True,
            **resumen_json(resumen),
        }
    )
