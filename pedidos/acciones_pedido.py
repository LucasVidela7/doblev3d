from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect

from . import pedido_form_views, views
from .models import Pedido


def _volver(request):
    origen = (
        request.POST.get("origen", "").strip()
        or request.GET.get("volver", "").strip()
    )
    cliente_id = (
        request.POST.get("cliente_id", "").strip()
        or request.GET.get("cliente_id", "").strip()
    )
    pedido_id = (
        request.POST.get("pedido_id", "").strip()
        or request.GET.get("pedido_id", "").strip()
    )

    if origen == "cliente" and cliente_id:
        return redirect(
            "clientes:detalle",
            cliente_id=cliente_id,
        )

    if origen == "detalle" and pedido_id:
        return redirect(
            "pedidos:detalle",
            pedido_id=pedido_id,
        )

    return redirect("pedidos:impresiones")


def _mensaje_estado(pedido, accion):
    return (
        f"{pedido.codigo} está {pedido.get_estado_display().upper()} y "
        f"no se puede {accion}. Solo los pedidos PENDIENTES permiten esta acción."
    )


@transaction.atomic
def editar_pedido(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects.select_for_update(),
        id=pedido_id,
    )

    if pedido.estado != "PENDIENTE":
        messages.error(
            request,
            _mensaje_estado(pedido, "editar"),
        )
        return _volver(request)

    return pedido_form_views.editar_pedido(request, pedido_id)


@transaction.atomic
def cancelar_pedido(request, pedido_id):
    if request.method != "POST":
        return _volver(request)

    pedido = get_object_or_404(
        Pedido.objects.select_for_update(),
        id=pedido_id,
    )

    if pedido.estado != "PENDIENTE":
        messages.error(
            request,
            _mensaje_estado(pedido, "cancelar"),
        )
        return _volver(request)

    respuesta = views.cancelar_pedido(request, pedido_id)

    if request.POST.get("origen") in {"cliente", "detalle"}:
        return _volver(request)

    return respuesta


@transaction.atomic
def eliminar_pedido(request, pedido_id):
    if request.method != "POST":
        return _volver(request)

    pedido = get_object_or_404(
        Pedido.objects.select_for_update(),
        id=pedido_id,
    )

    if pedido.estado != "PENDIENTE":
        messages.error(
            request,
            _mensaje_estado(pedido, "eliminar"),
        )
        return _volver(request)

    respuesta = views.eliminar_pedido(request, pedido_id)

    if request.POST.get("origen") in {"cliente", "detalle"}:
        return _volver(request)

    return respuesta


@transaction.atomic
def entregar_pedido(request, pedido_id):
    if request.method != "POST":
        return _volver(request)

    pedido = get_object_or_404(
        Pedido.objects.select_for_update(),
        id=pedido_id,
    )

    if pedido.estado != "LISTO":
        messages.error(
            request,
            (
                f"{pedido.codigo} está {pedido.get_estado_display().upper()} y "
                "no se puede entregar. El pedido debe estar LISTO."
            ),
        )
        return _volver(request)

    respuesta = views.entregar_pedido(request, pedido_id)

    if request.POST.get("origen") in {"cliente", "detalle"}:
        return _volver(request)

    return respuesta
