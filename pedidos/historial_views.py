from collections import defaultdict
from decimal import Decimal

from django.db import models
from django.db.models import Sum
from django.shortcuts import render
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
    """Listado de cobros incluyendo cancelados como historial, sin saldo exigible."""
    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)

    filtro_estado = request.GET.get("estado", "TODOS").upper()
    estados_validos = {
        "TODOS",
        "SIN_PAGAR",
        "PARCIAL",
        "PAGADO",
        "CANCELADOS",
    }
    if filtro_estado not in estados_validos:
        filtro_estado = "TODOS"

    busqueda = request.GET.get("q", "").strip()

    pedidos = (
        Pedido.objects
        .select_related("cliente")
        .prefetch_related("detalles", "pagos")
        .order_by("-id")
    )

    if busqueda:
        filtros = models.Q(cliente__nombre__icontains=busqueda)
        if busqueda.upper().startswith("PED"):
            try:
                filtros |= models.Q(id=int(busqueda[3:]))
            except (TypeError, ValueError):
                pass
        elif busqueda.isdigit():
            filtros |= models.Q(id=int(busqueda))
        pedidos = pedidos.filter(filtros)

    filas = []
    saldo_total = Decimal("0")
    pedidos_con_saldo = 0

    for pedido in pedidos:
        cancelado = pedido.estado == "CANCELADO"
        total = pedido.total
        pagado = pedido.total_pagado
        saldo_modelo = pedido.saldo_pendiente

        if not cancelado and saldo_modelo > 0:
            saldo_total += saldo_modelo
            pedidos_con_saldo += 1

        if filtro_estado == "CANCELADOS":
            if not cancelado:
                continue
        elif filtro_estado != "TODOS":
            if cancelado or pedido.estado_pago != filtro_estado:
                continue

        filas.append(
            {
                "pedido": pedido,
                "total": total,
                "pagado": pagado,
                "saldo": Decimal("0") if cancelado else saldo_modelo,
                "saldo_historico": saldo_modelo,
                "estado_pago": "CANCELADO" if cancelado else pedido.estado_pago,
                "estado_pago_display": (
                    "Cancelado" if cancelado else pedido.estado_pago_display
                ),
                "pagos": list(pedido.pagos.all()),
                "cancelado": cancelado,
            }
        )

    cobrado_hoy = (
        Pago.objects
        .filter(fecha__date=hoy)
        .aggregate(total=Sum("monto"))
        .get("total")
        or Decimal("0")
    )

    cobrado_mes = (
        Pago.objects
        .filter(fecha__date__gte=inicio_mes)
        .aggregate(total=Sum("monto"))
        .get("total")
        or Decimal("0")
    )

    ultimos_pagos = (
        Pago.objects
        .select_related("pedido", "pedido__cliente")
        .order_by("-fecha", "-id")[:8]
    )

    return render(
        request,
        "pedidos/pagos.html",
        {
            "filas": filas,
            "filtro_estado": filtro_estado,
            "busqueda": busqueda,
            "cobrado_hoy": cobrado_hoy,
            "cobrado_mes": cobrado_mes,
            "saldo_total": saldo_total,
            "pedidos_con_saldo": pedidos_con_saldo,
            "ultimos_pagos": ultimos_pagos,
        },
    )
