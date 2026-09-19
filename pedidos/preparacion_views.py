from datetime import date

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from productos.models import Producto

from .detalle_views import _armar_preparacion
from .models import EstadoImpresionPedido, Pedido
from .personalizados_produccion import actualizar_estado_general_pedido


def _orden_entrega(fila):
    pedido = fila["pedido"]
    return (
        pedido.fecha_entrega is None,
        pedido.fecha_entrega or date.max,
        pedido.id,
    )


def _armar_fila(pedido):
    preparacion = _armar_preparacion(pedido)
    if not preparacion:
        return None

    listos = 0
    reservados = 0
    faltantes_stock = 0
    total_a_imprimir = 0
    total_piezas = 0

    for item in preparacion:
        cantidad = int(item.get("cantidad") or 0)
        total_piezas += cantidad

        if item["listo"]:
            listos += 1

        if item["es_personalizado"]:
            item["faltante"] = 0
            item["a_imprimir"] = 0 if item["listo"] else cantidad
            item["disponibilidad"] = (
                "Preparado"
                if item["listo"]
                else "Preparación manual"
            )
            continue

        reservado = bool(item.get("reservado_stock"))
        if reservado and not item["listo"]:
            reservados += 1

        stock_actual = int(item.get("stock_actual") or 0)

        if item["listo"] or reservado:
            faltante = 0
        else:
            faltante = max(cantidad - stock_actual, 0)

        item["faltante"] = faltante
        item["a_imprimir"] = faltante

        if item["listo"]:
            descontado = int(item.get("stock_descontado") or 0)
            item["disponibilidad"] = (
                f"Preparado · {descontado} descontado"
                if descontado
                else "Preparado"
            )
        elif reservado:
            reservado_cantidad = int(item.get("stock_reservado") or 0)
            item["disponibilidad"] = (
                f"Reservado · {reservado_cantidad} "
                f"unidad{'es' if reservado_cantidad != 1 else ''}"
            )
        elif faltante:
            faltantes_stock += 1
            item["disponibilidad"] = (
                f"Stock {stock_actual} · faltan {faltante}"
            )
        else:
            item["disponibilidad"] = (
                f"Stock {stock_actual} · disponible"
            )

        total_a_imprimir += faltante

    total = len(preparacion)
    porcentaje = int(round((listos * 100) / total)) if total else 0

    if pedido.estado == "LISTO":
        grupo = "listos"
        estado_operativo = "LISTO"
        estado_texto = "Paquete listo"
    elif (
        pedido.estado == "PREPARANDO"
        or reservados > 0
        or listos > 0
    ):
        grupo = "en_preparacion"
        estado_operativo = "PREPARANDO"
        estado_texto = "Armando paquete"
    elif faltantes_stock > 0:
        grupo = "falta_stock"
        estado_operativo = "FALTA"
        estado_texto = "Falta stock"
    else:
        grupo = "para_preparar"
        estado_operativo = "DISPONIBLE"
        estado_texto = "Todo disponible"

    hoy = timezone.localdate()
    if pedido.fecha_entrega is None:
        entrega_clase = "sin-fecha"
        entrega_texto = "Sin fecha"
    elif pedido.fecha_entrega < hoy:
        entrega_clase = "atrasado"
        entrega_texto = "Atrasado"
    elif pedido.fecha_entrega == hoy:
        entrega_clase = "hoy"
        entrega_texto = "Hoy"
    else:
        entrega_clase = "proxima"
        entrega_texto = pedido.fecha_entrega.strftime("%d/%m")

    return {
        "pedido": pedido,
        "productos": preparacion,
        "preparacion_total": total,
        "preparacion_listos": listos,
        "preparacion_porcentaje": porcentaje,
        "reservados": reservados,
        "faltantes_stock": faltantes_stock,
        "total_a_imprimir": total_a_imprimir,
        "total_piezas": total_piezas,
        "total_pedido": pedido.total,
        "total_pagado": pedido.total_pagado,
        "saldo_pendiente": pedido.saldo_pendiente,
        "estado_pago": pedido.estado_pago,
        "estado_pago_display": pedido.estado_pago_display,
        "pagos": list(pedido.pagos.all()),
        "solo_lectura": False,
        "grupo": grupo,
        "estado_operativo": estado_operativo,
        "estado_texto": estado_texto,
        "puede_iniciar": grupo == "para_preparar",
        "entrega_clase": entrega_clase,
        "entrega_texto": entrega_texto,
    }


def impresiones_por_pedido(request):
    """Centro operativo posterior a Producción.

    Mantiene activos y cancelados dentro del mismo módulo para que
    el cambio de filtro no dependa de una plantilla/contexto distinto.
    """
    filtro = request.GET.get("estado", "ACTIVOS").strip().upper()

    if filtro == "CANCELADOS":
        from .historial_views import _productos_cancelados_para_historial

        pedidos_cancelados = (
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

        cancelados = []
        for pedido in pedidos_cancelados:
            cancelados.append(
                {
                    "pedido": pedido,
                    "productos": _productos_cancelados_para_historial(
                        pedido
                    ),
                    "total_pedido": pedido.total,
                    "total_pagado": pedido.total_pagado,
                }
            )

        return render(
            request,
            "pedidos/impresiones_por_pedido.html",
            {
                "cancelados": cancelados,
                "total_cancelados": len(cancelados),
                "filtro_pedidos": "CANCELADOS",
                "para_preparar": [],
                "en_preparacion": [],
                "falta_stock": [],
                "listos": [],
                "total_para_preparar": 0,
                "total_en_preparacion": 0,
                "total_falta_stock": 0,
                "total_listos": 0,
                "total_activos": 0,
            },
        )

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
        .order_by("id")
    )

    grupos = {
        "para_preparar": [],
        "en_preparacion": [],
        "falta_stock": [],
        "listos": [],
    }

    for pedido in pedidos:
        fila = _armar_fila(pedido)
        if not fila:
            continue
        grupos[fila["grupo"]].append(fila)

    for filas in grupos.values():
        filas.sort(key=_orden_entrega)

    total_activos = sum(len(filas) for filas in grupos.values())

    return render(
        request,
        "pedidos/impresiones_por_pedido.html",
        {
            "para_preparar": grupos["para_preparar"],
            "en_preparacion": grupos["en_preparacion"],
            "falta_stock": grupos["falta_stock"],
            "listos": grupos["listos"],
            "total_para_preparar": len(grupos["para_preparar"]),
            "total_en_preparacion": len(grupos["en_preparacion"]),
            "total_falta_stock": len(grupos["falta_stock"]),
            "total_listos": len(grupos["listos"]),
            "total_activos": total_activos,
            "total_cancelados": Pedido.objects.filter(
                estado="CANCELADO"
            ).count(),
            "filtro_pedidos": "ACTIVOS",
        },
    )


@transaction.atomic
def iniciar_preparacion(request, pedido_id):
    if request.method != "POST":
        return redirect("pedidos:impresiones")

    pedido = get_object_or_404(
        Pedido.objects.select_for_update(),
        id=pedido_id,
    )

    if pedido.estado in {"ENTREGADO", "CANCELADO"}:
        messages.error(
            request,
            "Ese pedido ya no puede iniciar preparación.",
        )
        return redirect("pedidos:impresiones")

    preparacion = _armar_preparacion(pedido)
    if not preparacion:
        messages.error(
            request,
            "El pedido no tiene productos para preparar.",
        )
        return redirect("pedidos:impresiones")

    pendientes = [
        item
        for item in preparacion
        if (
            not item["es_personalizado"]
            and not item["listo"]
            and not item.get("reservado_stock")
        )
    ]
    pendientes.sort(key=lambda item: item["producto"].id)

    reservas = []

    for item in pendientes:
        estado = EstadoImpresionPedido.objects.select_for_update().get(
            id=item["estado_id"],
        )
        producto = Producto.objects.select_for_update().get(
            id=item["producto"].id,
        )
        cantidad = int(item.get("cantidad") or 0)

        if cantidad <= 0:
            continue

        if producto.stock < cantidad:
            messages.error(
                request,
                (
                    f"No se pudo iniciar {pedido.codigo}: "
                    f"{producto.nombre} necesita {cantidad} y "
                    f"hay {producto.stock} disponible."
                ),
            )
            return redirect("pedidos:impresiones")

        reservas.append((estado, producto, cantidad))

    for estado, producto, cantidad in reservas:
        producto.stock -= cantidad
        producto.save(update_fields=["stock"])

        estado.reservado_stock = True
        estado.cantidad_stock_reservada = cantidad
        estado.save(
            update_fields=[
                "reservado_stock",
                "cantidad_stock_reservada",
            ]
        )

    if pedido.estado != "LISTO":
        pedido.estado = "PREPARANDO"
        pedido.save(update_fields=["estado"])

    if reservas:
        unidades = sum(cantidad for _, _, cantidad in reservas)
        messages.success(
            request,
            (
                f"{pedido.codigo} en preparación. "
                f"Se reservaron {unidades} unidades de stock."
            ),
        )
    else:
        messages.success(
            request,
            f"{pedido.codigo} en preparación.",
        )

    return redirect(
        reverse("pedidos:impresiones") + "#en-preparacion"
    )


@transaction.atomic
def liberar_preparacion(request, pedido_id):
    if request.method != "POST":
        return redirect("pedidos:impresiones")

    pedido = get_object_or_404(
        Pedido.objects.select_for_update(),
        id=pedido_id,
    )

    if pedido.estado in {"ENTREGADO", "CANCELADO"}:
        messages.error(
            request,
            "Ese pedido ya no puede modificarse.",
        )
        return redirect("pedidos:impresiones")

    estados = list(
        EstadoImpresionPedido.objects
        .select_for_update()
        .filter(
            pedido=pedido,
            reservado_stock=True,
            listo=False,
        )
        .order_by("producto_id")
    )

    unidades = 0
    for estado in estados:
        cantidad = int(estado.cantidad_stock_reservada or 0)
        if cantidad:
            producto = Producto.objects.select_for_update().get(
                id=estado.producto_id,
            )
            producto.stock += cantidad
            producto.save(update_fields=["stock"])
            unidades += cantidad

        estado.reservado_stock = False
        estado.cantidad_stock_reservada = 0
        estado.save(
            update_fields=[
                "reservado_stock",
                "cantidad_stock_reservada",
            ]
        )

    actualizar_estado_general_pedido(pedido)

    if unidades:
        messages.success(
            request,
            (
                f"Se liberaron {unidades} unidades reservadas "
                f"de {pedido.codigo}."
            ),
        )
    else:
        messages.info(
            request,
            f"{pedido.codigo} no tenía stock reservado.",
        )

    return redirect("pedidos:impresiones")
