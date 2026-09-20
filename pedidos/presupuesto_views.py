from collections import defaultdict
from decimal import Decimal

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from clientes.models import Cliente
from clientes.telefonos import buscar_cliente_por_telefono
from calculadora.precios import calcular_precio_catalogo_producto
from kits.engine import KitEngine
from kits.models import Kit
from productos.models import Producto
from productos.miniaturas import asignar_miniaturas_productos

from .miniaturas import (
    asignar_miniatura_resumen,
    asignar_miniaturas_items,
)
from .models import (
    DetalleKitProducto,
    DetallePedido,
    DetallePresupuesto,
    DetallePresupuestoKitProducto,
    Pedido,
    Presupuesto,
)
from .pedido_form_views import (
    CENTAVOS,
    _decimal_positivo,
    _precio_kit_desde_post,
)
from .precios_api import _costos_producto, _precio_lista
from .views import _costo_actual_producto, _guardar_costo_kit


def _catalogos():
    productos = list(
        Producto.objects.filter(activo=True)
        .select_related("tipo")
        .order_by("nombre")
    )
    asignar_miniaturas_productos(productos)

    return {
        "clientes": Cliente.objects.filter(activo=True).order_by("nombre"),
        "productos": productos,
        "kits": (
            Kit.objects.filter(activo=True)
            .select_related("tipo_producto")
            .order_by("nombre")
        ),
    }


def _precio_lista_producto(producto):
    costo, seguro = _costos_producto(producto)
    return Decimal(str(_precio_lista(producto, costo, seguro) or 0))


def _ids_kit_libre(detalle):
    if (
        detalle.tipo_item != "KIT"
        or not detalle.kit
        or detalle.kit.modalidad == "FIJO"
        or detalle.cantidad <= 0
    ):
        return []

    ids = []
    for componente in detalle.productos_kit.all():
        total = int(componente.cantidad or 0)
        if total <= 0:
            continue

        if total % detalle.cantidad == 0:
            repeticiones = total // detalle.cantidad
        else:
            repeticiones = 1

        ids.extend([componente.producto_id] * repeticiones)

    return ids[: int(detalle.kit.cantidad_productos or 0)]


def _parsear_items(request):
    indices = request.POST.getlist("item_indice")
    if not indices:
        raise ValueError(
            "El presupuesto debe tener al menos un producto, kit o personalizado."
        )

    items = []

    for indice in indices:
        tipo_item = request.POST.get(f"tipo_item_{indice}")
        try:
            cantidad = int(request.POST.get(f"cantidad_{indice}", "1"))
        except (TypeError, ValueError):
            cantidad = 0

        if cantidad <= 0:
            raise ValueError("Las cantidades deben ser mayores a cero.")

        if tipo_item == "PRODUCTO":
            producto = get_object_or_404(
                Producto,
                id=request.POST.get(f"producto_{indice}"),
                activo=True,
                solo_produccion=False,
            )
            precio_manual = (
                request.POST.get(f"precio_producto_manual_{indice}")
                == "1"
            )

            if precio_manual:
                precio_unitario = _decimal_positivo(
                    request.POST.get(f"precio_unitario_{indice}", "")
                )
                precio_total = _decimal_positivo(
                    request.POST.get(f"precio_total_producto_{indice}", "")
                )

                if precio_total > 0:
                    precio_unitario = (
                        precio_total / Decimal(cantidad)
                    ).quantize(CENTAVOS)
                elif precio_unitario > 0:
                    precio_total = (
                        precio_unitario * Decimal(cantidad)
                    ).quantize(CENTAVOS)

                if precio_unitario <= 0 or precio_total <= 0:
                    raise ValueError(
                        f"El precio acordado de {producto.nombre} debe ser mayor a cero."
                    )
            else:
                calculo_catalogo = calcular_precio_catalogo_producto(
                    producto,
                    cantidad,
                )
                precio_unitario = Decimal(
                    str(calculo_catalogo["precio_unitario"])
                ).quantize(CENTAVOS)
                precio_total = Decimal(
                    str(calculo_catalogo["precio_final_total"])
                ).quantize(CENTAVOS)

            items.append(
                {
                    "key": str(indice),
                    "tipo_item": "PRODUCTO",
                    "cantidad": cantidad,
                    "producto": producto,
                    "precio_lista_unitario": _precio_lista_producto(producto),
                    "precio_unitario": precio_unitario,
                }
            )
            continue

        if tipo_item == "KIT":
            kit = get_object_or_404(
                Kit.objects.prefetch_related("componentes__producto"),
                id=request.POST.get(f"kit_{indice}"),
                activo=True,
            )

            productos_libres = None
            componentes = defaultdict(int)

            if kit.modalidad == "FIJO":
                detalle_id = request.POST.get(
                    f"detalle_id_{indice}",
                    "",
                ).strip()
                detalle_snapshot = None

                if detalle_id:
                    detalle_snapshot = (
                        DetallePresupuesto.objects
                        .filter(
                            id=detalle_id,
                            kit=kit,
                            tipo_item="KIT",
                        )
                        .prefetch_related(
                            "productos_kit__producto"
                        )
                        .first()
                    )

                if (
                    detalle_snapshot
                    and detalle_snapshot.productos_kit.exists()
                ):
                    # Mantiene la receta histórica mientras el usuario
                    # no cambie explícitamente de kit.
                    factor = (
                        Decimal(cantidad)
                        / Decimal(
                            max(
                                int(
                                    detalle_snapshot.cantidad
                                    or 1
                                ),
                                1,
                            )
                        )
                    )
                    for componente in (
                        detalle_snapshot.productos_kit.all()
                    ):
                        cantidad_snapshot = Decimal(
                            int(componente.cantidad or 0)
                        )
                        cantidad_nueva = int(
                            (
                                cantidad_snapshot
                                * factor
                            ).quantize(
                                Decimal("1")
                            )
                        )
                        componentes[
                            componente.producto_id
                        ] += max(
                            cantidad_nueva,
                            0,
                        )
                else:
                    componentes_fijos = list(
                        kit.componentes.all()
                    )
                    if not componentes_fijos:
                        raise ValueError(
                            f"El kit {kit.nombre} no tiene una composición fija configurada."
                        )

                    for componente in componentes_fijos:
                        componentes[
                            componente.producto_id
                        ] += (
                            componente.cantidad
                            * cantidad
                        )
            else:
                ids = request.POST.getlist(f"productos_kit_{indice}")
                if len(ids) != kit.cantidad_productos:
                    raise ValueError(
                        f"El kit {kit.nombre} necesita {kit.cantidad_productos} productos."
                    )
                if not kit.tipo_producto:
                    raise ValueError(
                        f"El kit {kit.nombre} no tiene una categoría configurada."
                    )

                productos_libres = []
                for producto_id in ids:
                    producto = get_object_or_404(
                        Producto,
                        id=producto_id,
                        activo=True,
                        solo_produccion=False,
                        tipo=kit.tipo_producto,
                    )
                    productos_libres.append(producto)
                    componentes[producto.id] += cantidad

            precio_lista_unitario = Decimal(str(kit.precio or 0))
            if kit.modalidad == "LIBRE_CATEGORIA":
                precio_lista_unitario = KitEngine.precio_unitario(
                    kit,
                    productos=productos_libres,
                )

            precio_unitario, precio_manual = _precio_kit_desde_post(
                request,
                indice,
                kit,
                productos_libres=productos_libres,
            )

            items.append(
                {
                    "key": str(indice),
                    "tipo_item": "KIT",
                    "cantidad": cantidad,
                    "kit": kit,
                    "componentes": dict(componentes),
                    "precio_lista_unitario": precio_lista_unitario,
                    "precio_unitario": precio_unitario,
                    "precio_kit_manual": precio_manual,
                }
            )
            continue

        if tipo_item == "PERSONALIZADO":
            producto_id = request.POST.get(
                f"producto_personalizado_{indice}"
            )
            detalle_personalizacion = request.POST.get(
                f"detalle_personalizacion_{indice}",
                "",
            ).strip()
            color = request.POST.get(
                f"color_personalizacion_{indice}",
                "",
            ).strip()
            precio_total = _decimal_positivo(
                request.POST.get(
                    f"precio_total_personalizado_{indice}",
                    "",
                )
            )

            if not producto_id:
                raise ValueError(
                    "Debés seleccionar un producto base para el personalizado."
                )
            if not detalle_personalizacion:
                raise ValueError(
                    "Debés ingresar el detalle de la personalización."
                )
            if precio_total <= 0:
                raise ValueError(
                    "El precio total del personalizado debe ser mayor a cero."
                )

            producto = get_object_or_404(
                Producto,
                id=producto_id,
                activo=True,
            )
            precio_unitario = (
                precio_total / Decimal(cantidad)
            ).quantize(CENTAVOS)

            items.append(
                {
                    "key": str(indice),
                    "tipo_item": "PERSONALIZADO",
                    "cantidad": cantidad,
                    "producto": producto,
                    "precio_lista_unitario": precio_unitario,
                    "precio_unitario": precio_unitario,
                    "precio_total_personalizado": precio_total,
                    "detalle_personalizacion": detalle_personalizacion,
                    "color": color,
                }
            )
            continue

        raise ValueError(
            "Existe un item del presupuesto que no es válido."
        )

    items_kits = []
    for item in items:
        if item["tipo_item"] != "KIT":
            continue

        componentes = [
            {
                "producto": Producto.objects.get(id=producto_id),
                "cantidad": cantidad,
            }
            for producto_id, cantidad in item["componentes"].items()
        ]
        items_kits.append(
            {
                "key": item["key"],
                "kit": item["kit"],
                "cantidad": item["cantidad"],
                "precio_unitario_lista": item["precio_lista_unitario"],
                "componentes": componentes,
            }
        )

    if items_kits:
        resumen = KitEngine.volumen(items_kits)
        por_key = {
            str(linea["key"]): linea
            for linea in resumen["lineas"]
        }

        for item in items:
            if (
                item["tipo_item"] == "KIT"
                and not item["precio_kit_manual"]
            ):
                linea = por_key.get(str(item["key"]))
                if linea:
                    item["precio_unitario"] = Decimal(
                        str(linea["precio_unitario_final"])
                    ).quantize(CENTAVOS)

    return items


def _guardar_snapshot_presupuesto_kit(detalle):
    if (
        not detalle
        or detalle.tipo_item != "KIT"
        or not detalle.kit_id
    ):
        return

    componentes = [
        {
            "producto": item.producto,
            "cantidad": item.cantidad,
        }
        for item in detalle.productos_kit
        .select_related("producto")
        .all()
    ]

    detalle.kit_snapshot = KitEngine.snapshot(
        detalle.kit,
        cantidad_kits=detalle.cantidad,
        precio_unitario=detalle.precio_unitario,
        precio_manual=detalle.precio_kit_manual,
        componentes=componentes,
        costo_unitario=detalle.costo_unitario,
    )
    detalle.save(update_fields=["kit_snapshot"])


def _guardar_items(presupuesto, items):
    for item in items:
        tipo = item["tipo_item"]

        if tipo == "PRODUCTO":
            DetallePresupuesto.objects.create(
                presupuesto=presupuesto,
                tipo_item="PRODUCTO",
                producto=item["producto"],
                cantidad=item["cantidad"],
                precio_lista_unitario=item["precio_lista_unitario"],
                precio_unitario=item["precio_unitario"],
            )
            continue

        if tipo == "KIT":
            detalle = DetallePresupuesto.objects.create(
                presupuesto=presupuesto,
                tipo_item="KIT",
                kit=item["kit"],
                cantidad=item["cantidad"],
                precio_lista_unitario=item["precio_lista_unitario"],
                precio_unitario=item["precio_unitario"],
                precio_kit_manual=item["precio_kit_manual"],
            )

            for producto_id, cantidad in item["componentes"].items():
                DetallePresupuestoKitProducto.objects.create(
                    detalle=detalle,
                    producto_id=producto_id,
                    cantidad=cantidad,
                )

            _guardar_snapshot_presupuesto_kit(detalle)
            continue

        DetallePresupuesto.objects.create(
            presupuesto=presupuesto,
            tipo_item="PERSONALIZADO",
            producto=item["producto"],
            cantidad=item["cantidad"],
            precio_lista_unitario=item["precio_lista_unitario"],
            precio_unitario=item["precio_unitario"],
            precio_total_personalizado=item[
                "precio_total_personalizado"
            ],
            personalizado=True,
            detalle_personalizacion=item[
                "detalle_personalizacion"
            ],
            color_personalizacion=item["color"],
        )


@transaction.atomic
def nuevo_presupuesto(request):
    catalogos = _catalogos()
    cliente_inicial_id = request.GET.get("cliente", "").strip()

    if request.method != "POST":
        return render(
            request,
            "pedidos/nuevo_pedido.html",
            {
                **catalogos,
                "cliente_inicial_id": cliente_inicial_id,
                "es_presupuesto": True,
            },
        )

    cliente_id = request.POST.get("cliente")
    fecha_entrega = request.POST.get("fecha_entrega")
    observaciones = request.POST.get("observaciones", "").strip()

    if cliente_id == "NUEVO":
        nombre = request.POST.get(
            "nuevo_cliente_nombre",
            "",
        ).strip()
        if not nombre:
            messages.error(
                request,
                "Debés ingresar el nombre del nuevo cliente.",
            )
            transaction.set_rollback(True)
            return redirect("pedidos:nuevo")

        telefono = request.POST.get(
            "nuevo_cliente_telefono",
            "",
        ).strip()
        existente = buscar_cliente_por_telefono(telefono)
        if existente:
            estado = "" if existente.activo else " (inactivo)"
            messages.error(
                request,
                (
                    f"Ese teléfono ya pertenece a {existente.nombre} "
                    f"({existente.codigo}){estado}. Seleccioná el cliente existente."
                ),
            )
            transaction.set_rollback(True)
            return redirect(
                f"{reverse('pedidos:nuevo')}?cliente={existente.id}"
            )

        cliente = Cliente.objects.create(
            nombre=nombre,
            telefono=telefono,
            email=request.POST.get(
                "nuevo_cliente_email",
                "",
            ).strip(),
            activo=True,
        )
    else:
        cliente = get_object_or_404(
            Cliente,
            id=cliente_id,
            activo=True,
        )

    try:
        items = _parsear_items(request)
    except ValueError as error:
        messages.error(request, str(error))
        transaction.set_rollback(True)
        return redirect("pedidos:nuevo")

    presupuesto = Presupuesto.objects.create(
        cliente=cliente,
        fecha_entrega=fecha_entrega or None,
        observaciones=observaciones,
        estado="PENDIENTE",
    )
    _guardar_items(presupuesto, items)

    messages.success(
        request,
        f"{presupuesto.codigo} creado correctamente.",
    )
    return redirect(
        "pedidos:presupuesto_detalle",
        presupuesto_id=presupuesto.id,
    )


def lista_presupuestos(request):
    estado = request.GET.get("estado", "").strip().upper()

    base = list(
        Presupuesto.objects
        .select_related("cliente", "pedido_generado")
        .prefetch_related(
            "detalles__producto",
            "detalles__kit__componentes__producto",
            "detalles__productos_kit__producto",
        )
        .order_by("-id")
    )

    asignar_miniatura_resumen(base, "detalles")

    estados_validos = {"PENDIENTE", "APROBADO", "RECHAZADO"}
    presupuestos = (
        [item for item in base if item.estado == estado]
        if estado in estados_validos
        else base
    )

    return render(
        request,
        "pedidos/presupuestos_lista.html",
        {
            "presupuestos": presupuestos,
            "estado_seleccionado": (
                estado if estado in estados_validos else ""
            ),
            "pendientes": sum(
                1 for item in base
                if item.estado == "PENDIENTE"
            ),
            "aprobados": sum(
                1 for item in base
                if item.estado == "APROBADO"
            ),
            "rechazados": sum(
                1 for item in base
                if item.estado == "RECHAZADO"
            ),
        },
    )


def detalle_presupuesto(request, presupuesto_id):
    presupuesto = get_object_or_404(
        Presupuesto.objects
        .select_related("cliente", "pedido_generado")
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
        ),
        id=presupuesto_id,
    )

    detalles = list(presupuesto.detalles.all())
    asignar_miniaturas_items(detalles)

    return render(
        request,
        "pedidos/presupuesto_detalle.html",
        {
            "presupuesto": presupuesto,
            "detalles": detalles,
        },
    )


@transaction.atomic
def editar_presupuesto(request, presupuesto_id):
    presupuesto = get_object_or_404(
        Presupuesto.objects
        .select_for_update()
        .select_related("cliente"),
        id=presupuesto_id,
    )

    if presupuesto.estado != "PENDIENTE":
        messages.error(
            request,
            "Sólo se pueden editar presupuestos pendientes.",
        )
        return redirect(
            "pedidos:presupuesto_detalle",
            presupuesto_id=presupuesto.id,
        )

    catalogos = _catalogos()

    if request.method == "GET":
        detalles = list(
            presupuesto.detalles
            .select_related("producto", "kit")
            .prefetch_related("productos_kit__producto")
            .all()
        )

        items_iniciales = [
            {
                "id": detalle.id,
                "tipo_item": detalle.tipo_item,
                "cantidad": detalle.cantidad,
                "producto_id": detalle.producto_id,
                "kit_id": detalle.kit_id,
                "precio_unitario": str(detalle.precio_unitario),
                "precio_kit_manual": bool(
                    detalle.precio_kit_manual
                ),
                "productos_kit_ids": _ids_kit_libre(detalle),
                "detalle_personalizacion": (
                    detalle.detalle_personalizacion
                ),
                "color_personalizacion": (
                    detalle.color_personalizacion
                ),
                "precio_total_personalizado": (
                    str(detalle.precio_total_personalizado)
                    if detalle.precio_total_personalizado is not None
                    else ""
                ),
            }
            for detalle in detalles
        ]

        return render(
            request,
            "pedidos/editar_pedido.html",
            {
                **catalogos,
                "pedido": presupuesto,
                "items_iniciales": items_iniciales,
                "es_presupuesto": True,
                "volver_cliente": False,
                "volver_cliente_id": "",
            },
        )

    cliente = get_object_or_404(
        Cliente,
        id=request.POST.get("cliente"),
        activo=True,
    )

    try:
        items = _parsear_items(request)
    except ValueError as error:
        messages.error(request, str(error))
        transaction.set_rollback(True)
        return redirect(
            "pedidos:presupuesto_editar",
            presupuesto_id=presupuesto.id,
        )

    presupuesto.cliente = cliente
    presupuesto.fecha_entrega = (
        request.POST.get("fecha_entrega") or None
    )
    presupuesto.observaciones = request.POST.get(
        "observaciones",
        "",
    ).strip()
    presupuesto.save(
        update_fields=[
            "cliente",
            "fecha_entrega",
            "observaciones",
            "actualizado_en",
        ]
    )

    presupuesto.detalles.all().delete()
    _guardar_items(presupuesto, items)

    messages.success(
        request,
        f"{presupuesto.codigo} actualizado correctamente.",
    )
    return redirect(
        "pedidos:presupuesto_detalle",
        presupuesto_id=presupuesto.id,
    )


@transaction.atomic
def aprobar_presupuesto(request, presupuesto_id):
    if request.method != "POST":
        return redirect(
            "pedidos:presupuesto_detalle",
            presupuesto_id=presupuesto_id,
        )

    presupuesto = get_object_or_404(
        Presupuesto.objects
        .select_for_update()
        .select_related("cliente")
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
        ),
        id=presupuesto_id,
    )

    if presupuesto.estado != "PENDIENTE":
        messages.error(
            request,
            "El presupuesto ya fue resuelto.",
        )
        return redirect(
            "pedidos:presupuesto_detalle",
            presupuesto_id=presupuesto.id,
        )

    pedido = Pedido.objects.create(
        cliente=presupuesto.cliente,
        fecha_entrega=presupuesto.fecha_entrega,
        observaciones=presupuesto.observaciones,
        estado="PENDIENTE",
    )

    for detalle in presupuesto.detalles.all():
        if detalle.tipo_item == "PRODUCTO":
            DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="PRODUCTO",
                producto=detalle.producto,
                cantidad=detalle.cantidad,
                precio_unitario=detalle.precio_unitario,
                costo_unitario=_costo_actual_producto(
                    detalle.producto
                ),
                estado="PENDIENTE",
            )
            continue

        if detalle.tipo_item == "KIT":
            detalle_pedido = DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="KIT",
                kit=detalle.kit,
                cantidad=detalle.cantidad,
                precio_unitario=detalle.precio_unitario,
                # Un presupuesto aprobado congela el valor aceptado.
                precio_kit_manual=True,
                costo_unitario=None,
                estado="PENDIENTE",
            )

            for componente in detalle.productos_kit.all():
                DetalleKitProducto.objects.create(
                    detalle=detalle_pedido,
                    producto=componente.producto,
                    cantidad=componente.cantidad,
                )

            _guardar_costo_kit(detalle_pedido)
            continue

        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PERSONALIZADO",
            producto=detalle.producto,
            cantidad=detalle.cantidad,
            precio_unitario=detalle.precio_unitario,
            costo_unitario=_costo_actual_producto(
                detalle.producto
            ),
            precio_total_personalizado=(
                detalle.precio_total_personalizado
            ),
            estado="PENDIENTE",
            personalizado=True,
            detalle_personalizacion=(
                detalle.detalle_personalizacion
            ),
            color_personalizacion=(
                detalle.color_personalizacion
            ),
        )

    presupuesto.estado = "APROBADO"
    presupuesto.pedido_generado = pedido
    presupuesto.save(
        update_fields=[
            "estado",
            "pedido_generado",
            "actualizado_en",
        ]
    )

    messages.success(
        request,
        (
            f"{presupuesto.codigo} aprobado. "
            f"Se creó {pedido.codigo}."
        ),
    )
    return redirect(
        "pedidos:detalle",
        pedido_id=pedido.id,
    )


@transaction.atomic
def rechazar_presupuesto(request, presupuesto_id):
    if request.method != "POST":
        return redirect(
            "pedidos:presupuesto_detalle",
            presupuesto_id=presupuesto_id,
        )

    presupuesto = get_object_or_404(
        Presupuesto.objects.select_for_update(),
        id=presupuesto_id,
    )

    if presupuesto.estado != "PENDIENTE":
        messages.error(
            request,
            "El presupuesto ya fue resuelto.",
        )
    else:
        presupuesto.estado = "RECHAZADO"
        presupuesto.save(
            update_fields=[
                "estado",
                "actualizado_en",
            ]
        )
        messages.success(
            request,
            f"{presupuesto.codigo} marcado como rechazado.",
        )

    return redirect(
        "pedidos:presupuesto_detalle",
        presupuesto_id=presupuesto.id,
    )

@transaction.atomic
def repetir_pedido_como_presupuesto(request, pedido_id):
    """
    Crea un presupuesto nuevo a partir de un pedido histórico.

    Se conserva exactamente:
    - cliente
    - productos / kits / personalizados
    - cantidades
    - composición real de cada kit
    - precio acordado histórico
    - personalizaciones y observaciones

    La fecha de entrega se deja vacía porque corresponde a una nueva venta.
    El precio de lista se recalcula con valores actuales para que la edición
    muestre la diferencia sin alterar el precio acordado que se copió.
    """
    if request.method != "POST":
        return redirect(
            "pedidos:detalle",
            pedido_id=pedido_id,
        )

    pedido = get_object_or_404(
        Pedido.objects
        .select_related("cliente")
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
        ),
        id=pedido_id,
    )

    detalles = list(pedido.detalles.all())
    if not detalles:
        messages.error(
            request,
            f"{pedido.codigo} no tiene ítems para repetir.",
        )
        return redirect(
            "pedidos:detalle",
            pedido_id=pedido.id,
        )

    presupuesto = Presupuesto.objects.create(
        cliente=pedido.cliente,
        fecha_entrega=None,
        observaciones=pedido.observaciones,
        estado="PENDIENTE",
    )

    for detalle in detalles:
        if detalle.tipo_item == "PRODUCTO":
            precio_lista = (
                _precio_lista_producto(detalle.producto)
                if detalle.producto
                else detalle.precio_unitario
            )
            DetallePresupuesto.objects.create(
                presupuesto=presupuesto,
                tipo_item="PRODUCTO",
                producto=detalle.producto,
                cantidad=detalle.cantidad,
                precio_lista_unitario=precio_lista,
                precio_unitario=detalle.precio_unitario,
                costo_unitario=detalle.costo_unitario,
            )
            continue

        if detalle.tipo_item == "KIT":
            kit = detalle.kit
            precio_lista = Decimal(str(
                kit.precio
                if kit and kit.precio is not None
                else detalle.precio_unitario
            ))

            if (
                kit
                and kit.modalidad == "LIBRE_CATEGORIA"
                and detalle.cantidad > 0
            ):
                productos_libres = []
                for componente in detalle.productos_kit.all():
                    total = int(componente.cantidad or 0)
                    repeticiones = max(
                        total // int(detalle.cantidad or 1),
                        1,
                    )
                    productos_libres.extend(
                        [componente.producto] * repeticiones
                    )
                productos_libres = productos_libres[
                    : int(kit.cantidad_productos or 0)
                ]
                if productos_libres:
                    precio_lista = Decimal(str(
                        KitEngine.precio_unitario(
                            kit,
                            productos_libres,
                        )
                    ))

            nuevo_detalle = DetallePresupuesto.objects.create(
                presupuesto=presupuesto,
                tipo_item="KIT",
                kit=kit,
                cantidad=detalle.cantidad,
                precio_lista_unitario=precio_lista,
                precio_unitario=detalle.precio_unitario,
                precio_kit_manual=True,
                costo_unitario=detalle.costo_unitario,
                kit_snapshot=detalle.kit_snapshot or {},
            )

            for componente in detalle.productos_kit.all():
                DetallePresupuestoKitProducto.objects.create(
                    detalle=nuevo_detalle,
                    producto=componente.producto,
                    cantidad=componente.cantidad,
                )
            continue

        precio_lista = (
            _precio_lista_producto(detalle.producto)
            if detalle.producto
            else detalle.precio_unitario
        )
        DetallePresupuesto.objects.create(
            presupuesto=presupuesto,
            tipo_item="PERSONALIZADO",
            producto=detalle.producto,
            cantidad=detalle.cantidad,
            precio_lista_unitario=precio_lista,
            precio_unitario=detalle.precio_unitario,
            costo_unitario=detalle.costo_unitario,
            personalizado=True,
            detalle_personalizacion=detalle.detalle_personalizacion,
            color_personalizacion=detalle.color_personalizacion,
            precio_total_personalizado=detalle.precio_total_personalizado,
        )

    messages.success(
        request,
        (
            f"{presupuesto.codigo} creado desde {pedido.codigo}. "
            "Se copiaron composición, cantidades y precios acordados. "
            "Revisá los valores actuales antes de enviarlo."
        ),
    )
    return redirect(
        "pedidos:presupuesto_editar",
        presupuesto_id=presupuesto.id,
    )

