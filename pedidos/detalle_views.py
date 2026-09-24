from productos.miniaturas import asignar_miniaturas_productos
from collections import OrderedDict

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date

from clientes.models import ContactoCliente
from clientes.whatsapp import numero_whatsapp, url_contacto

from . import acciones_impresion
from .miniaturas import asignar_miniaturas_items
from .adicionales import enriquecer_detalles_pedido
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
                    "reservado_stock": False,
                    "stock_reservado": 0,
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
        reservado = bool(estado.reservado_stock)
        reservado_cantidad = int(
            estado.cantidad_stock_reservada or 0
        )
        stock_actual = max(int(producto.stock or 0), 0)
        faltante = (
            0
            if listo or reservado
            else max(cantidad - stock_actual, 0)
        )
        puede_marcar = listo or reservado or faltante == 0

        if listo:
            estado_operativo = "LISTO"
            descontado = int(estado.cantidad_stock_descontada or 0)
            estado_texto = (
                f"Preparado · {descontado} descontado"
                if descontado
                else "Preparado"
            )
        elif reservado:
            estado_operativo = "RESERVADO"
            estado_texto = (
                f"Reservado · {reservado_cantidad} "
                f"unidad{'es' if reservado_cantidad != 1 else ''}"
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
                "reservado_stock": reservado,
                "stock_reservado": reservado_cantidad,
                "faltante": faltante,
                "estado_operativo": estado_operativo,
                "estado_texto": estado_texto,
                "detalle_personalizacion": "",
                "color_personalizacion": "",
            }
        )

    preparacion.extend(personalizados)
    return preparacion


def _armar_paquetes_detalle(pedido, preparacion):
    """Reconstruye cada kit físico del pedido para usarlo como guía de armado."""
    estado_por_producto = {
        item["producto"].id: item
        for item in preparacion
        if item.get("producto")
    }

    paquetes = []
    sueltos = []

    for detalle in pedido.detalles.all():
        if detalle.estado == "CANCELADO":
            continue

        if detalle.tipo_item != "KIT" or not detalle.kit:
            if detalle.producto:
                estado = estado_por_producto.get(
                    detalle.producto_id,
                    {},
                )
                sueltos.append(
                    {
                        "producto": detalle.producto,
                        "nombre": (
                            f"{detalle.producto.nombre} personalizado"
                            if detalle.tipo_item == "PERSONALIZADO"
                            else detalle.producto.nombre
                        ),
                        "cantidad": int(detalle.cantidad or 0),
                        "estado_operativo": estado.get(
                            "estado_operativo",
                            (
                                "MANUAL"
                                if detalle.tipo_item == "PERSONALIZADO"
                                else ""
                            ),
                        ),
                        "estado_texto": estado.get(
                            "estado_texto",
                            "",
                        ),
                    }
                )
            continue

        cantidad_kits = max(
            int(detalle.cantidad or 0),
            1,
        )
        nombre_kit = (
            (detalle.kit_snapshot or {}).get("nombre")
            or detalle.kit.nombre
        )

        paquetes_linea = [
            {
                "numero": 0,
                "nombre_kit": nombre_kit,
                "unidad_linea": unidad + 1,
                "cantidad_linea": cantidad_kits,
                "productos": [],
                "distribucion_aproximada": False,
            }
            for unidad in range(cantidad_kits)
        ]

        componentes = list(
            detalle.productos_kit.all()
        )

        if not componentes and detalle.kit.modalidad == "FIJO":
            componentes = []
            for componente in detalle.kit.componentes.all():
                componentes.append(
                    {
                        "producto": componente.producto,
                        "cantidad": (
                            int(componente.cantidad or 0)
                            * cantidad_kits
                        ),
                    }
                )

        for componente in componentes:
            if isinstance(componente, dict):
                producto = componente["producto"]
                total = int(componente["cantidad"] or 0)
            else:
                producto = componente.producto
                total = int(componente.cantidad or 0)

            if total <= 0:
                continue

            base, resto = divmod(
                total,
                cantidad_kits,
            )
            if resto:
                for paquete in paquetes_linea:
                    paquete["distribucion_aproximada"] = True

            for indice, paquete in enumerate(paquetes_linea):
                cantidad_paquete = (
                    base
                    + (1 if indice < resto else 0)
                )
                if cantidad_paquete <= 0:
                    continue

                estado = estado_por_producto.get(
                    producto.id,
                    {},
                )
                paquete["productos"].append(
                    {
                        "producto": producto,
                        "nombre": producto.nombre,
                        "cantidad": cantidad_paquete,
                        "estado_operativo": estado.get(
                            "estado_operativo",
                            "",
                        ),
                        "estado_texto": estado.get(
                            "estado_texto",
                            "",
                        ),
                    }
                )

        paquetes.extend(paquetes_linea)

    total_paquetes = len(paquetes)
    for numero, paquete in enumerate(
        paquetes,
        start=1,
    ):
        paquete["numero"] = numero
        paquete["total_paquetes"] = total_paquetes

    return paquetes, sueltos


def detalle_pedido(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects
        .select_related(
            "cliente",
            "presupuesto_origen",
            "presupuesto_origen__solicitud_web_origen",
        )
        .prefetch_related(
            "detalles__producto",
            "detalles__kit__componentes__producto",
            "detalles__productos_kit__producto",
            "presupuesto_origen__solicitud_web_origen__items",
            "pagos",
        ),
        id=pedido_id,
    )

    detalles = enriquecer_detalles_pedido(
        pedido,
        list(pedido.detalles.all()),
    )
    asignar_miniaturas_items(detalles)

    pagos = list(pedido.pagos.all())
    preparacion = _armar_preparacion(pedido)
    paquetes, productos_sueltos = _armar_paquetes_detalle(
        pedido,
        preparacion,
    )
    productos_preparacion = [
        item["producto"]
        for item in preparacion
        if item.get("producto")
    ]
    productos_paquetes = [
        item["producto"]
        for paquete in paquetes
        for item in paquete["productos"]
        if item.get("producto")
    ]
    productos_paquetes.extend(
        item["producto"]
        for item in productos_sueltos
        if item.get("producto")
    )
    asignar_miniaturas_productos(
        productos_preparacion
        + productos_paquetes
    )

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

    presupuesto_origen = getattr(
        pedido,
        "presupuesto_origen",
        None,
    )
    tiene_origen_aprobado = bool(
        presupuesto_origen
        and presupuesto_origen.estado == "APROBADO"
    )
    aprobacion_contactada = False
    aprobacion_whatsapp_url = ""
    entrega_contactada = False
    entrega_whatsapp_url = ""

    if tiene_origen_aprobado:
        aprobacion_contactada = (
            ContactoCliente.objects
            .filter(
                cliente=pedido.cliente,
                motivo="PEDIDO_APROBADO",
                referencia=pedido.codigo,
            )
            .exists()
        )
        if numero_whatsapp(pedido.cliente):
            aprobacion_whatsapp_url = url_contacto(
                pedido.cliente,
                "PEDIDO_APROBADO",
                pedido=pedido,
            )

    if pedido.estado == "LISTO":
        entrega_contactada = (
            ContactoCliente.objects
            .filter(
                cliente=pedido.cliente,
                motivo="PEDIDO_LISTO",
                referencia=pedido.codigo,
            )
            .exists()
        )
        if numero_whatsapp(pedido.cliente):
            entrega_whatsapp_url = url_contacto(
                pedido.cliente,
                "PEDIDO_LISTO",
                pedido=pedido,
            )

    return render(
        request,
        "pedidos/detalle.html",
        {
            "pedido": pedido,
            "detalles": detalles,
            "pagos": pagos,
            "preparacion": preparacion,
            "paquetes": paquetes,
            "total_paquetes": len(paquetes),
            "productos_sueltos": productos_sueltos,
            "preparacion_total": preparacion_total,
            "preparacion_listos": preparacion_listos,
            "preparacion_porcentaje": preparacion_porcentaje,
            "cantidad_lineas": len(detalles),
            "cantidad_unidades": cantidad_unidades,
            "preparacion_editable": pedido.estado not in {"ENTREGADO", "CANCELADO"},
            "pedido_activo": pedido.estado not in {"ENTREGADO", "CANCELADO"},
            "medios_pago": Pago.MEDIOS,
            "tiene_origen_aprobado": tiene_origen_aprobado,
            "aprobacion_contactada": aprobacion_contactada,
            "aprobacion_whatsapp_url": aprobacion_whatsapp_url,
            "entrega_contactada": entrega_contactada,
            "entrega_whatsapp_url": entrega_whatsapp_url,
            "entrega_con_saldo": (
                pedido.estado == "LISTO"
                and pedido.saldo_pendiente > 0
            ),
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
