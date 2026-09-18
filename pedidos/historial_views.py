from collections import defaultdict
from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.shortcuts import redirect, render
from django.utils import timezone

from .models import Pago, Pedido


def _fila_historica_producto(detalle, producto, cantidad, origen=""):
    return {
        "producto": producto,
        "nombre": producto.nombre if producto else origen,
        "codigo": producto.codigo if producto else "",
        "cantidad": cantidad,
        "listo": False,
        "estado_id": None,
        "detalle_personalizado_id": None,
        "puede_marcar_listo": False,
        "es_personalizado": detalle.tipo_item == "PERSONALIZADO",
        "detalle_personalizacion": detalle.detalle_personalizacion,
        "color_personalizacion": detalle.color_personalizacion,
        "solo_lectura": True,
        "cancelado": True,
        "origen": origen,
    }


def _productos_cancelados_para_historial(pedido):
    """Reconstruye lo que contenía un pedido cancelado sin generar estados operativos."""
    filas = []

    for detalle in pedido.detalles.all():
        if detalle.tipo_item in ["PRODUCTO", "PERSONALIZADO"]:
            nombre = detalle.get_tipo_item_display()
            filas.append(
                _fila_historica_producto(
                    detalle,
                    detalle.producto,
                    detalle.cantidad,
                    origen=nombre,
                )
            )
            continue

        if detalle.tipo_item == "KIT":
            componentes = list(detalle.productos_kit.all())
            if componentes:
                for componente in componentes:
                    filas.append(
                        _fila_historica_producto(
                            detalle,
                            componente.producto,
                            componente.cantidad,
                            origen=(
                                f"Kit {detalle.kit.nombre}"
                                if detalle.kit
                                else "Kit"
                            ),
                        )
                    )
            else:
                filas.append(
                    _fila_historica_producto(
                        detalle,
                        None,
                        detalle.cantidad,
                        origen=(
                            detalle.kit.nombre
                            if detalle.kit
                            else "Kit"
                        ),
                    )
                )

    return filas


def pedidos_cancelados(request):
    """Historial de pedidos cancelados: visible, pero completamente de solo lectura."""
    pedidos = (
        Pedido.objects
        .filter(estado="CANCELADO")
        .select_related("cliente")
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
            "pagos",
        )
        .order_by("-id")
    )

    filas = []
    for pedido in pedidos:
        filas.append(
            {
                "pedido": pedido,
                "productos": _productos_cancelados_para_historial(pedido),
                "total_a_imprimir": 0,
                "total_pedido": pedido.total,
                "total_pagado": pedido.total_pagado,
                # Un pedido cancelado no forma parte de la cuenta por cobrar.
                "saldo_pendiente": Decimal("0"),
                "estado_pago": "CANCELADO",
                "estado_pago_display": "Cancelado",
                "pagos": list(pedido.pagos.all()),
                "solo_lectura": True,
            }
        )

    return render(
        request,
        "pedidos/impresiones_por_pedido.html",
        {
            "pedidos_impresion": filas,
            "filtro_pedidos": "CANCELADOS",
        },
    )


def pagos(request):
    """
    Ruta histórica de Pagos.
    El módulo fue unificado dentro de Finanzas.
    """
    return redirect("/pedidos/finanzas/#cobros")
