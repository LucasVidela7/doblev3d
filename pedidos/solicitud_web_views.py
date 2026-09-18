from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from clientes.models import Cliente

from .models import (
    DetallePresupuesto,
    DetallePresupuestoKitProducto,
    Presupuesto,
    SolicitudWeb,
)


def lista_solicitudes_web(request):
    solicitudes = list(
        SolicitudWeb.objects
        .select_related("presupuesto_generado")
        .prefetch_related("items")
        .order_by("-id")
    )

    return render(
        request,
        "pedidos/solicitudes_web_lista.html",
        {
            "solicitudes": solicitudes,
            "nuevas": sum(1 for s in solicitudes if s.estado == "NUEVA"),
            "contactadas": sum(
                1 for s in solicitudes if s.estado == "CONTACTADA"
            ),
            "convertidas": sum(
                1 for s in solicitudes if s.estado == "CONVERTIDA"
            ),
        },
    )


def detalle_solicitud_web(request, solicitud_id):
    solicitud = get_object_or_404(
        SolicitudWeb.objects
        .select_related("presupuesto_generado")
        .prefetch_related(
            "items__producto",
            "items__kit",
            "items__productos_kit__producto",
        ),
        id=solicitud_id,
    )

    return render(
        request,
        "pedidos/solicitud_web_detalle.html",
        {
            "solicitud": solicitud,
            "items": list(solicitud.items.all()),
            "whatsapp_numero": solicitud.telefono_normalizado,
        },
    )


@transaction.atomic
def marcar_contactada(request, solicitud_id):
    if request.method != "POST":
        return redirect(
            "pedidos:solicitud_web_detalle",
            solicitud_id=solicitud_id,
        )

    solicitud = get_object_or_404(
        SolicitudWeb.objects.select_for_update(),
        id=solicitud_id,
    )

    if solicitud.estado == "NUEVA":
        solicitud.estado = "CONTACTADA"
        solicitud.save(
            update_fields=[
                "estado",
                "actualizada_en",
            ]
        )
        messages.success(
            request,
            f"{solicitud.codigo} marcada como contactada.",
        )

    return redirect(
        "pedidos:solicitud_web_detalle",
        solicitud_id=solicitud.id,
    )


@transaction.atomic
def rechazar_solicitud_web(request, solicitud_id):
    if request.method != "POST":
        return redirect(
            "pedidos:solicitud_web_detalle",
            solicitud_id=solicitud_id,
        )

    solicitud = get_object_or_404(
        SolicitudWeb.objects.select_for_update(),
        id=solicitud_id,
    )

    if solicitud.estado == "CONVERTIDA":
        messages.error(
            request,
            "La solicitud ya fue convertida en presupuesto.",
        )
    elif solicitud.estado != "RECHAZADA":
        solicitud.estado = "RECHAZADA"
        solicitud.save(
            update_fields=[
                "estado",
                "actualizada_en",
            ]
        )
        messages.success(
            request,
            f"{solicitud.codigo} marcada como rechazada.",
        )

    return redirect(
        "pedidos:solicitud_web_detalle",
        solicitud_id=solicitud.id,
    )


def _buscar_cliente(solicitud):
    filtros = Q()

    if solicitud.telefono:
        filtros |= Q(telefono=solicitud.telefono)

    if solicitud.email:
        filtros |= Q(email__iexact=solicitud.email)

    if filtros:
        cliente = (
            Cliente.objects
            .filter(filtros, activo=True)
            .order_by("id")
            .first()
        )
        if cliente:
            return cliente

    return Cliente.objects.create(
        nombre=solicitud.nombre,
        telefono=solicitud.telefono,
        email=solicitud.email,
        activo=True,
    )


@transaction.atomic
def convertir_solicitud_web(request, solicitud_id):
    if request.method != "POST":
        return redirect(
            "pedidos:solicitud_web_detalle",
            solicitud_id=solicitud_id,
        )

    solicitud = get_object_or_404(
        SolicitudWeb.objects
        .select_for_update()
        .prefetch_related(
            "items__producto",
            "items__kit",
            "items__productos_kit__producto",
        ),
        id=solicitud_id,
    )

    if solicitud.presupuesto_generado_id:
        return redirect(
            "pedidos:presupuesto_detalle",
            presupuesto_id=solicitud.presupuesto_generado_id,
        )

    if solicitud.estado not in {"NUEVA", "CONTACTADA"}:
        messages.error(
            request,
            "Esta solicitud ya no puede convertirse.",
        )
        return redirect(
            "pedidos:solicitud_web_detalle",
            solicitud_id=solicitud.id,
        )

    cliente = _buscar_cliente(solicitud)

    observaciones = solicitud.observaciones.strip()
    if observaciones:
        observaciones = (
            f"Origen {solicitud.codigo}\n\n"
            f"{observaciones}"
        )
    else:
        observaciones = f"Origen {solicitud.codigo}"

    presupuesto = Presupuesto.objects.create(
        cliente=cliente,
        observaciones=observaciones,
        estado="PENDIENTE",
    )

    for item in solicitud.items.all():
        if item.tipo_item == "PRODUCTO":
            DetallePresupuesto.objects.create(
                presupuesto=presupuesto,
                tipo_item="PRODUCTO",
                producto=item.producto,
                cantidad=item.cantidad,
                precio_lista_unitario=item.precio_unitario,
                precio_unitario=item.precio_unitario,
            )
            continue

        detalle = DetallePresupuesto.objects.create(
            presupuesto=presupuesto,
            tipo_item="KIT",
            kit=item.kit,
            cantidad=item.cantidad,
            precio_lista_unitario=item.precio_unitario,
            precio_unitario=item.precio_unitario,
            # El servidor ya validó el precio al recibir la solicitud.
            # Al convertirlo congelamos ese valor para respetar lo visto
            # por el cliente.
            precio_kit_manual=True,
        )

        for componente in item.productos_kit.all():
            DetallePresupuestoKitProducto.objects.create(
                detalle=detalle,
                producto=componente.producto,
                cantidad=componente.cantidad,
            )

    solicitud.estado = "CONVERTIDA"
    solicitud.presupuesto_generado = presupuesto
    solicitud.save(
        update_fields=[
            "estado",
            "presupuesto_generado",
            "actualizada_en",
        ]
    )

    messages.success(
        request,
        (
            f"{solicitud.codigo} convertida en "
            f"{presupuesto.codigo}."
        ),
    )
    return redirect(
        "pedidos:presupuesto_detalle",
        presupuesto_id=presupuesto.id,
    )
