from django.shortcuts import render

from .detalle_views import _armar_preparacion
from .models import Pedido


def impresiones_por_pedido(request):
    """Vista operativa compacta para preparar varios pedidos rápidamente.

    Comparte exactamente la misma preparación que la ficha de detalle. La
    acción que confirma cada check continúa siendo pedidos:cambiar_listo, de
    modo que el descuento/restauración de stock y el estado general del pedido
    siguen teniendo una única fuente de verdad.
    """
    pedidos = (
        Pedido.objects
        .exclude(estado__in=["ENTREGADO", "CANCELADO"])
        .select_related("cliente")
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
            "pagos",
        )
        .order_by("fecha_entrega", "id")
    )

    filas = []

    for pedido in pedidos:
        preparacion = _armar_preparacion(pedido)
        if not preparacion:
            continue

        listos = 0
        total_a_imprimir = 0
        faltantes_stock = 0

        for item in preparacion:
            if item["listo"]:
                listos += 1

            if item["es_personalizado"]:
                item["faltante"] = 0
                item["a_imprimir"] = 0 if item["listo"] else item["cantidad"]
                item["disponibilidad"] = "Preparación manual"
                continue

            stock_actual = int(item.get("stock_actual") or 0)
            cantidad = int(item.get("cantidad") or 0)
            faltante = 0 if item["listo"] else max(cantidad - stock_actual, 0)

            item["faltante"] = faltante
            item["a_imprimir"] = faltante

            if item["listo"]:
                descontado = int(item.get("stock_descontado") or 0)
                item["disponibilidad"] = (
                    f"Preparado · {descontado} descontado"
                    if descontado
                    else "Preparado"
                )
            elif faltante:
                faltantes_stock += 1
                item["disponibilidad"] = f"Stock {stock_actual} · faltan {faltante}"
            else:
                item["disponibilidad"] = f"Stock {stock_actual} · disponible"

            total_a_imprimir += faltante

        total = len(preparacion)
        porcentaje = int(round((listos * 100) / total)) if total else 0

        filas.append(
            {
                "pedido": pedido,
                "productos": preparacion,
                "preparacion_total": total,
                "preparacion_listos": listos,
                "preparacion_porcentaje": porcentaje,
                "faltantes_stock": faltantes_stock,
                "total_a_imprimir": total_a_imprimir,
                "total_pedido": pedido.total,
                "total_pagado": pedido.total_pagado,
                "saldo_pendiente": pedido.saldo_pendiente,
                "estado_pago": pedido.estado_pago,
                "estado_pago_display": pedido.estado_pago_display,
                "pagos": list(pedido.pagos.all()),
                "solo_lectura": False,
            }
        )

    return render(
        request,
        "pedidos/impresiones_por_pedido.html",
        {
            "pedidos_impresion": filas,
            "filtro_pedidos": "ACTIVOS",
        },
    )
