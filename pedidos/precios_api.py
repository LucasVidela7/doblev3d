from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from calculadora.precios import MARGEN_MINIMO, fila_precio, margenes_escenario
from productos.models import Producto


def _costo_productivo(producto):
    return max(
        Decimal(str(producto.costo or 0))
        + Decimal(str(producto.seguro or 0)),
        Decimal("0"),
    )


def precio_producto(request):
    """API de precios usada por Nuevo Pedido y Editar Pedido.

    Mantiene una única estructura estable para el frontend y funciona
    igual para productos simples y compuestos. En los compuestos, el
    modelo ya tiene sincronizados tiempo y peso totales desde sus piezas.
    """
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
        Producto,
        id=producto_id,
        activo=True,
        solo_produccion=False,
    )

    costo_productivo = _costo_productivo(producto)
    margen_tope = max(
        Decimal(str(producto.margen_ganancia or 0)),
        MARGEN_MINIMO,
    )
    margen_piso = MARGEN_MINIMO
    precio_lista = Decimal(str(producto.subtotal or 0))

    margenes = margenes_escenario(cantidad, margen_tope)
    escenarios = {}

    for estrategia in ("conservador", "recomendado", "agresivo"):
        margen = Decimal(str(margenes[estrategia]))
        fila = fila_precio(
            costo_productivo,
            cantidad,
            margen,
        )

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

    producto_json = {
        "id": producto.id,
        "codigo": producto.codigo,
        "nombre": producto.nombre,
        "precio_lista": float(precio_lista),
        "margen_tope": float(margen_tope),
        "margen_piso": float(margen_piso),
        "horas": int(producto.horas or 0),
        "minutos": int(producto.minutos or 0),
        "peso_gramos": float(Decimal(str(producto.peso_gramos or 0))),
        "tipo_fabricacion": producto.tipo_fabricacion,
        "es_compuesto": producto.tipo_fabricacion == "COMPUESTO",
    }

    return JsonResponse(
        {
            "ok": True,
            "producto": producto_json,
            "cantidad": cantidad,
            "precio_lista": float(precio_lista),
            "costo_productivo": float(costo_productivo),
            "margen_tope": float(margen_tope),
            "margen_piso": float(margen_piso),
            "escenarios": escenarios,
        }
    )
