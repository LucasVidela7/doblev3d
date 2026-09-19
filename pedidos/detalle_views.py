from collections import OrderedDict

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date

from . import acciones_impresion
from .models import EstadoImpresionPedido, Pago, Pedido


def _armar_preparacion(pedido):
    """Arma el estado operativo de los productos físicos de un pedido.

    Esta estructura es la fuente común para:
    - detalle del pedido
    - impresiones por pedido
    - detalle del cliente

    Productos normales y componentes de kits consumen stock al marcarse listos.
    Los personalizados se confirman manualmente y no descuentan stock general.
    """
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
            listo = detalle.estado == "LISTO"
            personalizados.append(
                {
                    "producto": detalle.producto,
                    "nombre": f"{detalle.producto.nombre} personalizado",
                    "cantidad": detalle.cantidad,
                    "listo": listo,
                    "puede_marcar_listo": True,
                    "es_personalizado": True,
                    "detalle_personalizado_id": detalle.id,
                    "estado_id": None,
                    "stock_actual": None,
                    "stock_descontado": 0,
                    "faltante": 0,
                    "estado_operativo": "LISTO" if listo else "MANUAL",
                    "estado_texto": "Preparado" if listo else "Preparación manual",
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
        faltante = 0 if listo else max(cantidad - stock_actual, 0)
        puede_marcar = listo or faltante == 0

        if listo:
            estado_operativo = "LISTO"
            descontado = int(estado.cantidad_stock_descontada or 0)
            estado_texto = (
                f"Preparado · {descontado} descontado"
                if descontado
                else "Preparado"
            )
        elif faltante:
            estado_operativo = "FALTANTE"
            estado_texto = f"Faltan {faltante} · stock {stock_actual}"
        else:
            estado_operativo = "DISPONIBLE"
            estado_texto = f"Disponible · stock {stock_actual}"

        preparacion.append(
            {
                "producto": producto,
                "nombre": producto.nombre,
                "cantidad": cantidad,
                "listo": listo,
                "puede_marcar_listo": puede_marcar,
                "es_personalizado": False,
                "detalle_personalizado_id": None,
                "estado_id": estado.id,
                "stock_actual": stock_actual,
                "stock_descontado": estado.cantidad_stock_descontada if listo else 0,
                "faltante": faltante,
                "estado_operativo": estado_operativo,
                "estado_texto": estado_texto,
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
    preparacion_porcentaje = (
        int(round((preparacion_listos * 100) / preparacion_total))
        if preparacion_total
        else 0
    )

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
            "preparacion_porcentaje": preparacion_porcentaje,
            "cantidad_lineas": len(detalles),
            "cantidad_unidades": cantidad_unidades,
            "preparacion_editable": pedido.estado not in {"ENTREGADO", "CANCELADO"},
            "pedido_activo": pedido.estado not in {"ENTREGADO", "CANCELADO"},
            "medios_pago": Pago.MEDIOS,
        },
    )


@transaction.atomic
def actualizar_fecha_entrega(request, pedido_id):
    if request.method != "POST":
        return redirect("pedidos:detalle", pedido_id=pedido_id)

    pedido = get_object_or_404(
        Pedido.objects.select_for_update(),
        id=pedido_id,
    )

    if pedido.estado in {"ENTREGADO", "CANCELADO"}:
        messages.error(
            request,
            "La fecha de entrega no se puede modificar en un pedido entregado o cancelado.",
        )
        return redirect("pedidos:detalle", pedido_id=pedido.id)

    valor = (request.POST.get("fecha_entrega") or "").strip()
    fecha_entrega = parse_date(valor) if valor else None

    if valor and fecha_entrega is None:
        messages.error(request, "Ingresá una fecha de entrega válida.")
        return redirect("pedidos:detalle", pedido_id=pedido.id)

    pedido.fecha_entrega = fecha_entrega
    pedido.save(update_fields=["fecha_entrega"])

    messages.success(
        request,
        (
            f"Fecha de entrega de {pedido.codigo} actualizada."
            if fecha_entrega
            else f"Fecha de entrega de {pedido.codigo} eliminada."
        ),
    )
    return redirect("pedidos:detalle", pedido_id=pedido.id)


def _volver_preparacion(request, pedido):
    if request.POST.get("origen") == "cliente":
        return redirect("clientes:detalle", cliente_id=pedido.cliente_id)
    return redirect("pedidos:detalle", pedido_id=pedido.id)


@transaction.atomic
def cambiar_preparacion(request, pedido_id):
    """Confirma o revierte un check desde pedido o cliente."""
    if request.method != "POST":
        return redirect("pedidos:detalle", pedido_id=pedido_id)

    pedido = get_object_or_404(Pedido, id=pedido_id)
    if pedido.estado in {"ENTREGADO", "CANCELADO"}:
        messages.error(request, "No se puede modificar un pedido entregado o cancelado.")
        return _volver_preparacion(request, pedido)

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
        return _volver_preparacion(request, pedido)

    # La acción estable mantiene una sola lógica para descontar/restaurar
    # stock y recalcular PENDIENTE / PREPARANDO / LISTO.
    acciones_impresion.cambiar_listo_impresion(request)
    return _volver_preparacion(request, pedido)
