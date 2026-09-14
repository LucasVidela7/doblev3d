from decimal import Decimal

from django.http import JsonResponse
from django.shortcuts import get_object_or_404

from calculadora.precios import fila_precio, margenes_escenario
from productos.models import Producto


def _costo_productivo(producto):
    return max(
        Decimal(str(producto.costo or 0))
        + Decimal(str(producto.seguro or 0)),
        Decimal("0"),
    )


def precio_producto(request):
    """API compatible con el JavaScript de Nuevo/Editar Pedido."""
    if request.method != "GET":
        return JsonResponse(
            {"ok": False, "mensaje": "Método no permitido."},
            status=405,
        )

    producto_id = (request.GET.get("producto_id") or "").strip()
    try:
        cantidad = int(request.GET.get("cantidad") or 1)
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
    margen_tope = Decimal(str(producto.margen_ganancia or 0))
    margen_piso = Decimal("22.5")
    precio_lista = Decimal(str(producto.subtotal or 0))

    margenes = margenes_escenario(cantidad, margen_tope)
    escenarios = {}

    for estrategia in ("conservador", "recomendado", "agresivo"):
        margen = Decimal(str(margenes[estrategia]))
        fila = fila_precio(costo_productivo, cantidad, margen)
        total = Decimal(str(fila["total_recomendado"]))
        precio_unitario_pedido = (total / Decimal(cantidad)).quantize(
            Decimal("0.01")
        )

        escenarios[estrategia] = {
            "estrategia": estrategia,
            "margen": float(margen),
            "margen_objetivo": float(margen),
            "precio_unitario": float(Decimal(str(fila["precio_unitario"]))),
            "precio_unitario_pedido": float(precio_unitario_pedido),
            "total_recomendado": float(total),
            "total_pedido": float(total),
        }

    return JsonResponse(
        {
            "ok": True,
            "producto": {
                "id": producto.id,
                "codigo": producto.codigo,
                "nombre": producto.nombre,
                "precio_lista": float(precio_lista),
                "margen_tope": float(margen_tope),
                "margen_piso": float(margen_piso),
                "horas": producto.horas,
                "minutos": producto.minutos,
                "peso_gramos": float(producto.peso_gramos or 0),
                "tipo_fabricacion": producto.tipo_fabricacion,
            },
            # Se conservan también las claves de la API anterior.
            "cantidad": cantidad,
            "precio_lista": float(precio_lista),
            "costo_productivo": float(costo_productivo),
            "margen_tope": float(margen_tope),
            "margen_piso": float(margen_piso),
            "escenarios": escenarios,
        }
    )
