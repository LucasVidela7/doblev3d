from collections import OrderedDict

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from . import acciones_impresion
from .models import EstadoImpresionPedido, Pedido


def _armar_preparacion(pedido):
    """Replica el criterio operativo de Preparar pedidos dentro del detalle."""
    agrupados = OrderedDict()
    personalizados = []

    for detalle in pedido.detalles.all():
        if detalle.estado == "CANCELADO":
            continue

        if (
            detalle.tipo_item == "PERSONALIZADO"
            and detalle.producto
            and detalle.producto.requiere_impresion
            and detalle.estado in {"PENDIENTE", "LISTO"}
        ):
            personalizados.append(
                {
                    "producto": detalle.producto,
                    "nombre": f"{detalle.producto.nombre} personalizado",
                    "cantidad": detalle.cantidad,
                    "listo": detalle.estado == "LISTO",
                    "puede_marcar_listo": True,
                    "es_personalizado": True,
                    "detalle_personalizado_id": detalle.id,
                    "estado_id": None,
                    "stock_actual": None,
                    "stock_descontado": 0,
                    "detalle_personalizacion": detalle.detalle_personalizacion,
                    "color_personalizacion": detalle.color_personalizacion,
                }
            )
            continue

        if detalle.estado != "PENDIENTE":
            continue

        if (
            detalle.tipo_item == "PRODUCTO"
            and detalle.producto
            and detalle.producto.requiere_impresion
        ):
            producto = detalle.producto
            item = agrupados.setdefault(
                producto.id,
                {"producto": producto, "cantidad": 0},
            )
            item["cantidad"] += detalle.cantidad

        elif detalle.tipo_item == "KIT" and detalle.kit:
            for componente in detalle.productos_kit.all():
                producto = componente.producto
                if not producto.requiere_impresion:
                    continue
                item = agrupados.setdefault(
                    producto.id,
                    {"producto": producto, "cantidad": 0},
                )
                item["cantidad"] += componente.cantidad

    preparacion = []

    for item in agrupados.values():
        producto = item["producto"]
        cantidad = item["cantidad"]
        estado, _ = EstadoImpresionPedido.objects.get_or_create(
            pedido=pedido,
            producto=producto,
            defaults={"listo": False},
        )

        listo = estado.listo
        stock_actual = max(int(producto.stock or 0), 0)
        preparacion.append(
            {
                "producto": producto,
                "nombre": producto.nombre,
                "cantidad": cantidad,
                "listo": listo,
                "puede_marcar_listo": listo or stock_actual >= cantidad,
                "es_personalizado": False,
                "detalle_personalizado_id": None,
                "estado_id": estado.id,
                "stock_actual": stock_actual,
                "stock_descontado": estado.cantidad_stock_descontada if listo else 0,
                "detalle_personalizacion": "",
                "color_personalizacion": "",
            }
        )

    preparacion.extend(personalizados)
    return preparacion


def detalle_pedido(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects
        .select_related("cliente")
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
            "pagos",
        ),
        id=pedido_id,
    )

    detalles = list(pedido.detalles.all())
    pagos = list(pedido.pagos.all())
    preparacion = _armar_preparacion(pedido)

    cantidad_unidades = sum(
        detalle.cantidad
        for detalle in detalles
        if detalle.estado != "CANCELADO"
    )
    preparacion_total = len(preparacion)
    preparacion_listos = sum(1 for item in preparacion if item["listo"])

    return render(
        request,
        "pedidos/detalle.html",
        {
            "pedido": pedido,
            "detalles": detalles,
            "pagos": pagos,
            "preparacion": preparacion,
            "preparacion_total": preparacion_total,
            "preparacion_listos": preparacion_listos,
            "cantidad_lineas": len(detalles),
            "cantidad_unidades": cantidad_unidades,
            "preparacion_editable": pedido.estado not in {"ENTREGADO", "CANCELADO"},
        },
    )


@transaction.atomic
def cambiar_preparacion(request, pedido_id):
    """Confirma o revierte un check desde la ficha del pedido."""
    if request.method != "POST":
        return redirect("pedidos:detalle", pedido_id=pedido_id)

    pedido = get_object_or_404(Pedido, id=pedido_id)
    if pedido.estado in {"ENTREGADO", "CANCELADO"}:
        messages.error(request, "No se puede modificar un pedido entregado o cancelado.")
        return redirect("pedidos:detalle", pedido_id=pedido_id)

    estado_id = (request.POST.get("estado_id") or "").strip()
    detalle_id = (request.POST.get("detalle_personalizado_id") or "").strip()

    if estado_id:
        get_object_or_404(
            EstadoImpresionPedido,
            id=estado_id,
            pedido_id=pedido_id,
        )
    elif detalle_id:
        get_object_or_404(
            pedido.detalles,
            id=detalle_id,
            tipo_item="PERSONALIZADO",
        )
    else:
        messages.error(request, "No se pudo identificar el producto a preparar.")
        return redirect("pedidos:detalle", pedido_id=pedido_id)

    # Se reutiliza la acción estable que ya descuenta/restaura stock y
    # recalcula PENDIENTE / PREPARANDO / LISTO. Ignoramos su redirect porque
    # esta pantalla debe permanecer en el detalle del pedido.
    acciones_impresion.cambiar_listo_impresion(request)
    return redirect("pedidos:detalle", pedido_id=pedido_id)
