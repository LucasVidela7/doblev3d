from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from clientes.models import Cliente
from clientes.telefonos import buscar_cliente_por_telefono
from productos.models import ConfiguracionCatalogo
from productos.whatsapp import (
    renderizar_mensaje_solicitud,
    whatsapp_url,
)

from .miniaturas import asignar_miniatura_resumen, asignar_miniaturas_items
from .models import (
    DetallePresupuesto,
    DetallePresupuestoKitProducto,
    Presupuesto,
    SolicitudWeb,
)


def lista_solicitudes_web(request):
    estado = request.GET.get("estado", "").strip().upper()

    base = list(
        SolicitudWeb.objects
        .select_related("presupuesto_generado")
        .prefetch_related(
            "items__producto",
            "items__kit__componentes__producto",
            "items__productos_kit__producto",
        )
        .order_by("-id")
    )

    asignar_miniatura_resumen(base, "items")

    estados_validos = {
        "NUEVA",
        "CONTACTADA",
        "CONVERTIDA",
        "RECHAZADA",
    }
    solicitudes = (
        [item for item in base if item.estado == estado]
        if estado in estados_validos
        else base
    )

    return render(
        request,
        "pedidos/solicitudes_web_lista.html",
        {
            "solicitudes": solicitudes,
            "solicitudes_nuevas": [
                item for item in base
                if item.estado == "NUEVA"
            ],
            "solicitudes_contactadas": [
                item for item in base
                if item.estado == "CONTACTADA"
            ],
            "solicitudes_convertidas": [
                item for item in base
                if item.estado == "CONVERTIDA"
            ],
            "solicitudes_rechazadas": [
                item for item in base
                if item.estado == "RECHAZADA"
            ],
            "estado_seleccionado": (
                estado if estado in estados_validos else ""
            ),
            "nuevas": sum(1 for s in base if s.estado == "NUEVA"),
            "contactadas": sum(
                1 for s in base if s.estado == "CONTACTADA"
            ),
            "convertidas": sum(
                1 for s in base if s.estado == "CONVERTIDA"
            ),
            "rechazadas": sum(
                1 for s in base if s.estado == "RECHAZADA"
            ),
        },
    )


def _normalizar_texto(valor):
    return " ".join(str(valor or "").split())


def _cliente_existente_y_diferencias(solicitud):
    cliente = buscar_cliente_por_telefono(solicitud.telefono)
    if not cliente:
        return None, {
            "nombre": False,
            "email": False,
            "hay_diferencias": False,
            "email_se_completa": False,
        }

    nombre_solicitud = _normalizar_texto(solicitud.nombre)
    nombre_cliente = _normalizar_texto(cliente.nombre)
    email_solicitud = (solicitud.email or "").strip()
    email_cliente = (cliente.email or "").strip()

    diferencia_nombre = bool(
        nombre_solicitud
        and nombre_cliente
        and nombre_solicitud.casefold() != nombre_cliente.casefold()
    )
    diferencia_email = bool(
        email_solicitud
        and email_cliente
        and email_solicitud.casefold() != email_cliente.casefold()
    )

    return cliente, {
        "nombre": diferencia_nombre,
        "email": diferencia_email,
        "hay_diferencias": diferencia_nombre or diferencia_email,
        "email_se_completa": bool(email_solicitud and not email_cliente),
    }


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

    config = ConfiguracionCatalogo.objects.first() or ConfiguracionCatalogo()
    mensaje_whatsapp = renderizar_mensaje_solicitud(
        config.whatsapp_mensaje_respuesta_solicitud,
        solicitud,
        request=request,
    )
    whatsapp_url_cliente = whatsapp_url(
        solicitud.telefono_normalizado,
        mensaje_whatsapp,
    )

    items = list(solicitud.items.all())
    asignar_miniaturas_items(items)
    cliente_existente, diferencias_cliente = (
        _cliente_existente_y_diferencias(solicitud)
    )

    return render(
        request,
        "pedidos/solicitud_web_detalle.html",
        {
            "solicitud": solicitud,
            "items": items,
            "whatsapp_numero": solicitud.telefono_normalizado,
            "whatsapp_url_cliente": whatsapp_url_cliente,
            "cliente_existente": cliente_existente,
            "diferencias_cliente": diferencias_cliente,
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


def _buscar_cliente(solicitud, actualizar_datos=False):
    # El teléfono es la identidad del cliente. Una nueva solicitud nunca
    # debe sobrescribir silenciosamente la ficha maestra.
    cliente = buscar_cliente_por_telefono(solicitud.telefono)

    if cliente:
        campos_actualizados = []
        nombre_nuevo = _normalizar_texto(solicitud.nombre)
        email_nuevo = (solicitud.email or "").strip()

        # Completar email faltante es seguro; reemplazar uno existente solo
        # se hace con una decisión explícita desde la solicitud.
        if email_nuevo and not (cliente.email or "").strip():
            cliente.email = email_nuevo
            campos_actualizados.append("email")

        if actualizar_datos:
            if nombre_nuevo and cliente.nombre != nombre_nuevo:
                cliente.nombre = nombre_nuevo
                campos_actualizados.append("nombre")

            email_actual = (cliente.email or "").strip()
            if (
                email_nuevo
                and email_actual
                and email_actual.casefold() != email_nuevo.casefold()
            ):
                cliente.email = email_nuevo
                campos_actualizados.append("email")

        if campos_actualizados:
            cliente.save(
                update_fields=list(dict.fromkeys(campos_actualizados))
            )
        return cliente

    return Cliente.objects.create(
        nombre=_normalizar_texto(solicitud.nombre),
        telefono=(solicitud.telefono or "").strip(),
        email=(solicitud.email or "").strip(),
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

    cliente_existente, diferencias_cliente = (
        _cliente_existente_y_diferencias(solicitud)
    )
    decision_datos = str(
        request.POST.get("datos_cliente") or ""
    ).strip().upper()

    if (
        cliente_existente
        and diferencias_cliente["hay_diferencias"]
        and decision_datos not in {"MANTENER", "ACTUALIZAR"}
    ):
        messages.error(
            request,
            "Elegí si querés mantener o actualizar los datos del cliente.",
        )
        return redirect(
            "pedidos:solicitud_web_detalle",
            solicitud_id=solicitud.id,
        )

    cliente = _buscar_cliente(
        solicitud,
        actualizar_datos=(decision_datos == "ACTUALIZAR"),
    )

    observaciones = solicitud.observaciones.strip()
    if observaciones:
        observaciones = (
            f"Origen {solicitud.codigo}\n\n"
            f"{observaciones}"
        )
    else:
        observaciones = f"Origen {solicitud.codigo}"

    resumen_colores = []
    for item_color in solicitud.items.all():
        if item_color.modo_color == "ESPECIFICO" and item_color.color_elegido:
            resumen_colores.append(
                f"- {item_color.nombre_snapshot}: {item_color.color_elegido}"
            )
        elif item_color.modo_color == "SURTIDO":
            resumen_colores.append(
                f"- {item_color.nombre_snapshot}: colores surtidos según stock"
            )
    if resumen_colores:
        observaciones += (
            "\n\nSelección de color:\n"
            + "\n".join(resumen_colores)
        )

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
                precio_lista_unitario=(
                    item.precio_base_unitario
                    + item.adicional_unitario
                ),
                precio_unitario=item.precio_unitario,
                personalizado=bool(item.color_elegido),
                detalle_personalizacion=(
                    "Color elegido desde la tienda"
                    if item.color_elegido
                    else ""
                ),
                color_personalizacion=item.color_elegido,
            )
            continue

        kit_snapshot = dict(item.kit_snapshot or {})
        if item.modo_color:
            kit_snapshot["seleccion_color"] = {
                "modo": item.modo_color,
                "color": item.color_elegido,
                "adicional_unitario": str(
                    item.adicional_color_unitario or 0
                ),
            }

        detalle = DetallePresupuesto.objects.create(
            presupuesto=presupuesto,
            tipo_item="KIT",
            kit=item.kit,
            cantidad=item.cantidad,
            precio_lista_unitario=(
                item.precio_base_unitario
                + item.adicional_unitario
            ),
            precio_unitario=item.precio_unitario,
            # El servidor ya validó el precio al recibir la solicitud.
            # Al convertirlo congelamos ese valor para respetar lo visto
            # por el cliente.
            precio_kit_manual=True,
            kit_snapshot=kit_snapshot,
            personalizado=bool(item.color_elegido),
            detalle_personalizacion=(
                "Color elegido desde la tienda"
                if item.color_elegido
                else ""
            ),
            color_personalizacion=item.color_elegido,
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
