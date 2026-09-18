from collections import defaultdict
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from clientes.models import Cliente
from kits.economia import (
    analizar_opciones_kit,
    precio_automatico_kit_libre,
)
from kits.models import Kit
from productos.models import Producto

from .models import (
    DetalleKitProducto,
    DetallePedido,
    EstadoImpresionPedido,
    Pedido,
)
from .views import (
    _actualizar_estado_general_pedido,
    _costo_actual_producto,
    _firmas_normales_del_pedido,
    _guardar_costo_kit,
    _restaurar_estado_impresion_para_edicion,
)


CENTAVOS = Decimal("0.01")


def _decimal_positivo(valor):
    try:
        numero = Decimal(str(valor or "").strip().replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return numero.quantize(CENTAVOS) if numero > 0 else Decimal("0")


def _precio_kit_desde_post(
    request,
    indice,
    kit,
    productos_libres=None,
):
    """
    Devuelve (precio_unitario, es_manual).

    En kits libres el precio automático se deriva siempre en servidor desde
    la selección real. Si la protección está activa, suma los extras premium.
    Un precio acordado manualmente sigue teniendo prioridad explícita.
    """
    es_manual = request.POST.get(f"precio_kit_manual_{indice}") == "1"

    if es_manual:
        precio = _decimal_positivo(
            request.POST.get(f"precio_unitario_kit_{indice}", "")
        )
        if precio <= 0:
            raise ValueError(
                f"El precio acordado de {kit.nombre} debe ser mayor a cero."
            )
        return precio, True

    if kit.modalidad == "LIBRE_CATEGORIA":
        if productos_libres is None:
            raise ValueError(
                f"Completá los productos de {kit.nombre} antes de calcular el precio."
            )
        precio_lista = _decimal_positivo(
            precio_automatico_kit_libre(
                kit,
                productos_libres,
            )
        )
    else:
        precio_lista = _decimal_positivo(kit.precio)

    if precio_lista <= 0:
        raise ValueError(
            f"El kit {kit.nombre} no tiene un precio de venta válido."
        )

    return precio_lista, False


def _ids_kit_libre_para_edicion(detalle):
    """
    Reconstruye las posiciones originales de un kit libre.

    DetalleKitProducto guarda cantidades TOTALES del pedido. Si se vendieron
    5 kits y el cliente eligió A, A y B, se persisten A=10 y B=5. Para editar
    debemos volver a [A, A, B], no solamente [A, B].
    """
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
            # Respaldo para datos históricos inconsistentes: conservar al
            # menos una selección visible en vez de perder el producto.
            repeticiones = 1

        ids.extend([componente.producto_id] * repeticiones)

    cantidad_esperada = int(detalle.kit.cantidad_productos or 0)
    return ids[:cantidad_esperada]


def _componentes_fijos_historicos(detalle, nueva_cantidad):
    """
    Escala la composición REAL guardada en un pedido fijo existente.

    Esto evita que editar un pedido antiguo adopte silenciosamente una nueva
    receta del kit si la composición maestra cambió después de la venta.
    """
    if (
        not detalle
        or detalle.tipo_item != "KIT"
        or not detalle.kit
        or detalle.kit.modalidad != "FIJO"
        or detalle.cantidad <= 0
    ):
        return None

    componentes = defaultdict(int)
    for componente in detalle.productos_kit.all():
        total_anterior = int(componente.cantidad or 0)
        if total_anterior <= 0 or total_anterior % detalle.cantidad != 0:
            return None

        por_kit = total_anterior // detalle.cantidad
        componentes[componente.producto_id] += por_kit * nueva_cantidad

    return dict(componentes) or None


def productos_por_kit(request, kit_id):
    """API de composición de kit con su precio comercial actual."""
    kit = get_object_or_404(
        Kit.objects.prefetch_related("componentes__producto"),
        id=kit_id,
        activo=True,
    )

    precio = float(kit.precio or 0)

    if kit.modalidad == "FIJO":
        componentes = list(kit.componentes.all())
        cantidad_productos = sum(
            componente.cantidad for componente in componentes
        )

        return JsonResponse(
            {
                "kit": {
                    "id": kit.id,
                    "nombre": kit.nombre,
                    "modalidad": kit.modalidad,
                    "cantidad_productos": cantidad_productos,
                    "tipo": "",
                    "precio": precio,
                },
                "productos": [],
                "componentes": [
                    {
                        "id": componente.producto.id,
                        "codigo": componente.producto.codigo,
                        "nombre": componente.producto.nombre,
                        "cantidad": componente.cantidad,
                    }
                    for componente in componentes
                ],
            }
        )

    productos = list(
        Producto.objects.filter(
            tipo=kit.tipo_producto,
            activo=True,
            solo_produccion=False,
        ).order_by("nombre")
    )
    analisis = analizar_opciones_kit(
        kit,
        productos_categoria=productos,
    )
    opciones = {
        item["producto_id"]: item
        for item in analisis["opciones"]
    }

    return JsonResponse(
        {
            "kit": {
                "id": kit.id,
                "nombre": kit.nombre,
                "modalidad": kit.modalidad,
                "cantidad_productos": kit.cantidad_productos,
                "tipo": kit.tipo_producto.nombre if kit.tipo_producto else "",
                "precio": precio,
                "proteger_rentabilidad": bool(
                    kit.proteger_rentabilidad_libre
                ),
                "cantidad_incluidos": analisis["cantidad_incluidos"],
                "cantidad_premium": analisis["cantidad_premium"],
                "extra_minimo": float(analisis["extra_minimo"]),
            },
            "productos": [
                {
                    "id": producto.id,
                    "codigo": producto.codigo,
                    "nombre": producto.nombre,
                    "precio_lista": float(producto.subtotal or 0),
                    "incluido": bool(
                        opciones[producto.id]["incluido"]
                    ),
                    "requiere_extra": bool(
                        opciones[producto.id]["requiere_extra"]
                    ),
                    "extra": float(
                        opciones[producto.id]["extra"]
                    ),
                    "extra_sugerido": float(
                        opciones[producto.id]["extra_sugerido"]
                    ),
                    "precio_kit_con_extra": float(
                        opciones[producto.id]["precio_kit_con_extra"]
                    ),
                }
                for producto in sorted(
                    productos,
                    key=lambda p: (
                        0 if opciones[p.id]["incluido"] else 1,
                        opciones[p.id]["extra"],
                        p.nombre.casefold(),
                        p.id,
                    ),
                )
            ],
            "componentes": [],
        }
    )


@transaction.atomic
def nuevo_pedido(request):
    cliente_inicial_id = request.GET.get("cliente", "").strip()
    clientes = Cliente.objects.filter(activo=True).order_by("nombre")
    productos = (
        Producto.objects.filter(activo=True)
        .select_related("tipo")
        .order_by("nombre")
    )
    kits = (
        Kit.objects.filter(activo=True)
        .select_related("tipo_producto")
        .order_by("nombre")
    )

    if request.method != "POST":
        return render(
            request,
            "pedidos/nuevo_pedido.html",
            {
                "clientes": clientes,
                "productos": productos,
                "kits": kits,
                "cliente_inicial_id": cliente_inicial_id,
            },
        )

    cliente_id = request.POST.get("cliente")
    fecha_entrega = request.POST.get("fecha_entrega")
    observaciones = request.POST.get("observaciones", "").strip()

    if cliente_id == "NUEVO":
        nombre = request.POST.get("nuevo_cliente_nombre", "").strip()
        if not nombre:
            messages.error(request, "Debés ingresar el nombre del nuevo cliente.")
            transaction.set_rollback(True)
            return redirect("pedidos:nuevo")

        cliente = Cliente.objects.create(
            nombre=nombre,
            telefono=request.POST.get("nuevo_cliente_telefono", "").strip(),
            email=request.POST.get("nuevo_cliente_email", "").strip(),
            activo=True,
        )
    else:
        cliente = get_object_or_404(Cliente, id=cliente_id, activo=True)

    pedido = Pedido.objects.create(
        cliente=cliente,
        fecha_entrega=fecha_entrega or None,
        observaciones=observaciones,
        estado="PENDIENTE",
    )

    indices = request.POST.getlist("item_indice")
    if not indices:
        messages.error(
            request,
            "El pedido debe tener al menos un producto, kit o personalizado.",
        )
        transaction.set_rollback(True)
        return redirect("pedidos:nuevo")

    for indice in indices:
        tipo_item = request.POST.get(f"tipo_item_{indice}")
        try:
            cantidad = int(request.POST.get(f"cantidad_{indice}", "1"))
        except (TypeError, ValueError):
            cantidad = 0

        if cantidad <= 0:
            messages.error(request, "Las cantidades deben ser mayores a cero.")
            transaction.set_rollback(True)
            return redirect("pedidos:nuevo")

        if tipo_item == "PRODUCTO":
            producto = get_object_or_404(
                Producto,
                id=request.POST.get(f"producto_{indice}"),
                activo=True,
            )
            precio_unitario = _decimal_positivo(
                request.POST.get(f"precio_unitario_{indice}", "")
            )
            precio_total = _decimal_positivo(
                request.POST.get(f"precio_total_producto_{indice}", "")
            )

            if precio_total > 0:
                precio_unitario = (precio_total / Decimal(cantidad)).quantize(CENTAVOS)
            elif precio_unitario > 0:
                precio_total = (precio_unitario * Decimal(cantidad)).quantize(CENTAVOS)

            if precio_unitario <= 0 or precio_total <= 0:
                messages.error(
                    request,
                    f"El precio acordado de {producto.nombre} debe ser mayor a cero.",
                )
                transaction.set_rollback(True)
                return redirect("pedidos:nuevo")

            DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="PRODUCTO",
                producto=producto,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                costo_unitario=_costo_actual_producto(producto),
                estado="PENDIENTE",
            )
            continue

        if tipo_item == "KIT":
            kit = get_object_or_404(
                Kit.objects.prefetch_related("componentes__producto"),
                id=request.POST.get(f"kit_{indice}"),
                activo=True,
            )

            try:
                precio_unitario, precio_manual = _precio_kit_desde_post(
                    request, indice, kit
                )
            except ValueError as error:
                messages.error(request, str(error))
                transaction.set_rollback(True)
                return redirect("pedidos:nuevo")

            detalle = DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="KIT",
                kit=kit,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                precio_kit_manual=precio_manual,
                costo_unitario=None,
                estado="PENDIENTE",
            )

            if kit.modalidad == "FIJO":
                componentes = list(kit.componentes.all())
                if not componentes:
                    messages.error(
                        request,
                        f"El kit {kit.nombre} no tiene una composición fija configurada.",
                    )
                    transaction.set_rollback(True)
                    return redirect("pedidos:nuevo")

                for componente in componentes:
                    DetalleKitProducto.objects.create(
                        detalle=detalle,
                        producto=componente.producto,
                        cantidad=componente.cantidad * cantidad,
                    )
            else:
                ids = request.POST.getlist(f"productos_kit_{indice}")
                if len(ids) != kit.cantidad_productos:
                    messages.error(
                        request,
                        f"El kit {kit.nombre} necesita {kit.cantidad_productos} productos.",
                    )
                    transaction.set_rollback(True)
                    return redirect("pedidos:nuevo")

                if not kit.tipo_producto:
                    messages.error(
                        request,
                        f"El kit {kit.nombre} no tiene una categoría configurada.",
                    )
                    transaction.set_rollback(True)
                    return redirect("pedidos:nuevo")

                seleccionados = {}
                for producto_id in ids:
                    producto = get_object_or_404(
                        Producto,
                        id=producto_id,
                        activo=True,
                        tipo=kit.tipo_producto,
                    )
                    seleccionados.setdefault(
                        producto.id,
                        {"producto": producto, "cantidad": 0},
                    )
                    seleccionados[producto.id]["cantidad"] += cantidad

                for item in seleccionados.values():
                    DetalleKitProducto.objects.create(
                        detalle=detalle,
                        producto=item["producto"],
                        cantidad=item["cantidad"],
                    )

            _guardar_costo_kit(detalle)
            continue

        if tipo_item == "PERSONALIZADO":
            producto_id = request.POST.get(f"producto_personalizado_{indice}")
            detalle_personalizacion = request.POST.get(
                f"detalle_personalizacion_{indice}", ""
            ).strip()
            color = request.POST.get(f"color_personalizacion_{indice}", "").strip()
            precio_total = _decimal_positivo(
                request.POST.get(f"precio_total_personalizado_{indice}", "")
            )

            if not producto_id:
                messages.error(
                    request,
                    "Debés seleccionar un producto base para el personalizado.",
                )
                transaction.set_rollback(True)
                return redirect("pedidos:nuevo")
            if not detalle_personalizacion:
                messages.error(
                    request,
                    "Debés ingresar el detalle de la personalización.",
                )
                transaction.set_rollback(True)
                return redirect("pedidos:nuevo")
            if precio_total <= 0:
                messages.error(
                    request,
                    "El precio total del personalizado debe ser mayor a cero.",
                )
                transaction.set_rollback(True)
                return redirect("pedidos:nuevo")

            producto = get_object_or_404(Producto, id=producto_id, activo=True)
            precio_unitario = (precio_total / Decimal(cantidad)).quantize(CENTAVOS)

            DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="PERSONALIZADO",
                producto=producto,
                cantidad=cantidad,
                precio_unitario=precio_unitario,
                costo_unitario=_costo_actual_producto(producto),
                precio_total_personalizado=precio_total,
                estado="PENDIENTE",
                personalizado=True,
                detalle_personalizacion=detalle_personalizacion,
                color_personalizacion=color,
            )
            continue

        messages.error(request, "Existe un item del pedido que no es válido.")
        transaction.set_rollback(True)
        return redirect("pedidos:nuevo")

    messages.success(request, f"{pedido.codigo} creado correctamente.")
    return redirect("pedidos:nuevo")


@transaction.atomic
def editar_pedido(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects.select_for_update().select_related("cliente"),
        id=pedido_id,
    )

    if pedido.estado in ["ENTREGADO", "CANCELADO"]:
        messages.error(request, "No se puede editar un pedido entregado o cancelado.")
        return redirect("pedidos:impresiones")

    clientes = Cliente.objects.filter(activo=True).order_by("nombre")
    productos = (
        Producto.objects.filter(activo=True)
        .select_related("tipo")
        .order_by("nombre")
    )
    kits = (
        Kit.objects.filter(activo=True)
        .select_related("tipo_producto")
        .order_by("nombre")
    )

    detalles_actuales = list(
        pedido.detalles.select_related("producto", "kit")
        .prefetch_related("productos_kit__producto")
        .all()
    )
    detalles_por_id = {detalle.id: detalle for detalle in detalles_actuales}

    if request.method == "GET":
        items_iniciales = []
        for detalle in detalles_actuales:
            items_iniciales.append(
                {
                    "id": detalle.id,
                    "tipo_item": detalle.tipo_item,
                    "cantidad": detalle.cantidad,
                    "producto_id": detalle.producto_id,
                    "kit_id": detalle.kit_id,
                    "precio_unitario": (
                        str(detalle.precio_unitario)
                        if detalle.precio_unitario is not None
                        else ""
                    ),
                    "precio_kit_manual": bool(detalle.precio_kit_manual),
                    "productos_kit_ids": _ids_kit_libre_para_edicion(detalle),
                    "detalle_personalizacion": detalle.detalle_personalizacion,
                    "color_personalizacion": detalle.color_personalizacion,
                    "precio_total_personalizado": (
                        str(detalle.precio_total_personalizado)
                        if detalle.precio_total_personalizado is not None
                        else ""
                    ),
                }
            )

        return render(
            request,
            "pedidos/editar_pedido.html",
            {
                "pedido": pedido,
                "clientes": clientes,
                "productos": productos,
                "kits": kits,
                "items_iniciales": items_iniciales,
                "volver_cliente": request.GET.get("volver") == "cliente",
                "volver_cliente_id": request.GET.get("cliente_id", "").strip(),
            },
        )

    cliente = get_object_or_404(
        Cliente,
        id=request.POST.get("cliente"),
        activo=True,
    )
    fecha_entrega = request.POST.get("fecha_entrega")
    observaciones = request.POST.get("observaciones", "").strip()
    volver_cliente = request.POST.get("volver") == "cliente"
    volver_cliente_id = request.POST.get("volver_cliente_id", "").strip()

    indices = request.POST.getlist("item_indice")
    if not indices:
        messages.error(
            request,
            "El pedido debe tener al menos un producto, kit o personalizado.",
        )
        transaction.set_rollback(True)
        return redirect("pedidos:editar", pedido_id=pedido.id)

    pedido_prefetch = (
        Pedido.objects.prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
        ).get(id=pedido.id)
    )
    firma_anterior = _firmas_normales_del_pedido(pedido_prefetch)

    personalizados_anteriores = {
        detalle.id: {
            "producto_id": detalle.producto_id,
            "cantidad": detalle.cantidad,
            "detalle": detalle.detalle_personalizacion,
            "color": detalle.color_personalizacion,
            "precio_total": detalle.precio_total_personalizado,
            "estado": detalle.estado,
        }
        for detalle in detalles_actuales
        if detalle.tipo_item == "PERSONALIZADO"
    }

    nuevos_items = []

    for indice in indices:
        detalle_id_texto = request.POST.get(f"detalle_id_{indice}", "").strip()
        try:
            detalle_id = int(detalle_id_texto) if detalle_id_texto else None
        except (TypeError, ValueError):
            detalle_id = None

        tipo_item = request.POST.get(f"tipo_item_{indice}")
        try:
            cantidad = int(request.POST.get(f"cantidad_{indice}", "1"))
        except (TypeError, ValueError):
            cantidad = 0

        if cantidad <= 0:
            messages.error(request, "Las cantidades deben ser mayores a cero.")
            transaction.set_rollback(True)
            return redirect("pedidos:editar", pedido_id=pedido.id)

        if tipo_item == "PRODUCTO":
            producto = get_object_or_404(
                Producto,
                id=request.POST.get(f"producto_{indice}"),
                activo=True,
            )
            precio_unitario = _decimal_positivo(
                request.POST.get(f"precio_unitario_{indice}", "")
            )
            precio_total = _decimal_positivo(
                request.POST.get(f"precio_total_producto_{indice}", "")
            )

            if precio_total > 0:
                precio_unitario = (precio_total / Decimal(cantidad)).quantize(CENTAVOS)
            elif precio_unitario > 0:
                precio_total = (precio_unitario * Decimal(cantidad)).quantize(CENTAVOS)

            if precio_unitario <= 0 or precio_total <= 0:
                messages.error(
                    request,
                    f"El precio acordado de {producto.nombre} debe ser mayor a cero.",
                )
                transaction.set_rollback(True)
                return redirect("pedidos:editar", pedido_id=pedido.id)

            nuevos_items.append(
                {
                    "detalle_id": detalle_id,
                    "tipo_item": "PRODUCTO",
                    "cantidad": cantidad,
                    "producto": producto,
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

            try:
                precio_unitario, precio_manual = _precio_kit_desde_post(
                    request, indice, kit
                )
            except ValueError as error:
                messages.error(request, str(error))
                transaction.set_rollback(True)
                return redirect("pedidos:editar", pedido_id=pedido.id)

            componentes = None
            anterior = detalles_por_id.get(detalle_id)

            if kit.modalidad == "FIJO":
                if anterior and anterior.kit_id == kit.id:
                    componentes = _componentes_fijos_historicos(
                        anterior, cantidad
                    )

                if not componentes:
                    componentes_fijos = list(kit.componentes.all())
                    if not componentes_fijos:
                        messages.error(
                            request,
                            f"El kit {kit.nombre} no tiene una composición fija configurada.",
                        )
                        transaction.set_rollback(True)
                        return redirect("pedidos:editar", pedido_id=pedido.id)

                    componentes = defaultdict(int)
                    for componente in componentes_fijos:
                        componentes[componente.producto_id] += (
                            componente.cantidad * cantidad
                        )
                    componentes = dict(componentes)
            else:
                ids = request.POST.getlist(f"productos_kit_{indice}")
                if len(ids) != kit.cantidad_productos:
                    messages.error(
                        request,
                        f"El kit {kit.nombre} necesita {kit.cantidad_productos} productos.",
                    )
                    transaction.set_rollback(True)
                    return redirect("pedidos:editar", pedido_id=pedido.id)

                if not kit.tipo_producto:
                    messages.error(
                        request,
                        f"El kit {kit.nombre} no tiene una categoría configurada.",
                    )
                    transaction.set_rollback(True)
                    return redirect("pedidos:editar", pedido_id=pedido.id)

                agrupados = defaultdict(int)
                for producto_id in ids:
                    producto = get_object_or_404(
                        Producto,
                        id=producto_id,
                        activo=True,
                        tipo=kit.tipo_producto,
                    )
                    agrupados[producto.id] += cantidad
                componentes = dict(agrupados)

            nuevos_items.append(
                {
                    "detalle_id": detalle_id,
                    "tipo_item": "KIT",
                    "cantidad": cantidad,
                    "kit": kit,
                    "componentes": componentes,
                    "precio_unitario": precio_unitario,
                    "precio_kit_manual": precio_manual,
                }
            )
            continue

        if tipo_item == "PERSONALIZADO":
            producto = get_object_or_404(
                Producto,
                id=request.POST.get(f"producto_personalizado_{indice}"),
                activo=True,
            )
            detalle_personalizacion = request.POST.get(
                f"detalle_personalizacion_{indice}", ""
            ).strip()
            color = request.POST.get(f"color_personalizacion_{indice}", "").strip()
            precio_total = _decimal_positivo(
                request.POST.get(f"precio_total_personalizado_{indice}", "")
            )

            if not detalle_personalizacion:
                messages.error(
                    request,
                    "Debés ingresar el detalle de la personalización.",
                )
                transaction.set_rollback(True)
                return redirect("pedidos:editar", pedido_id=pedido.id)
            if precio_total <= 0:
                messages.error(
                    request,
                    "El precio total del personalizado debe ser mayor a cero.",
                )
                transaction.set_rollback(True)
                return redirect("pedidos:editar", pedido_id=pedido.id)

            nuevos_items.append(
                {
                    "detalle_id": detalle_id,
                    "tipo_item": "PERSONALIZADO",
                    "cantidad": cantidad,
                    "producto": producto,
                    "detalle_personalizacion": detalle_personalizacion,
                    "color": color,
                    "precio_total": precio_total,
                }
            )
            continue

        messages.error(request, "Existe un item del pedido que no es válido.")
        transaction.set_rollback(True)
        return redirect("pedidos:editar", pedido_id=pedido.id)

    firma_nueva = defaultdict(int)
    for item in nuevos_items:
        if item["tipo_item"] == "PRODUCTO":
            firma_nueva[item["producto"].id] += item["cantidad"]
        elif item["tipo_item"] == "KIT":
            for producto_id, cantidad in item["componentes"].items():
                firma_nueva[producto_id] += cantidad

    productos_afectados = {
        producto_id
        for producto_id in set(firma_anterior) | set(firma_nueva)
        if firma_anterior.get(producto_id, 0) != firma_nueva.get(producto_id, 0)
    }

    for producto_id in productos_afectados:
        _restaurar_estado_impresion_para_edicion(pedido, producto_id)

    pedido.cliente = cliente
    pedido.fecha_entrega = fecha_entrega or None
    pedido.observaciones = observaciones
    pedido.save(update_fields=["cliente", "fecha_entrega", "observaciones"])

    pedido.detalles.all().delete()

    for item in nuevos_items:
        if item["tipo_item"] == "PRODUCTO":
            producto = item["producto"]
            DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="PRODUCTO",
                producto=producto,
                cantidad=item["cantidad"],
                precio_unitario=item["precio_unitario"],
                costo_unitario=_costo_actual_producto(producto),
                estado="PENDIENTE",
            )
            continue

        if item["tipo_item"] == "KIT":
            detalle = DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="KIT",
                kit=item["kit"],
                cantidad=item["cantidad"],
                precio_unitario=item["precio_unitario"],
                precio_kit_manual=item["precio_kit_manual"],
                costo_unitario=None,
                estado="PENDIENTE",
            )

            for producto_id, cantidad in item["componentes"].items():
                DetalleKitProducto.objects.create(
                    detalle=detalle,
                    producto_id=producto_id,
                    cantidad=cantidad,
                )

            _guardar_costo_kit(detalle)
            continue

        anterior = personalizados_anteriores.get(item["detalle_id"])
        conservar_listo = bool(
            anterior
            and anterior["estado"] == "LISTO"
            and anterior["producto_id"] == item["producto"].id
            and anterior["cantidad"] == item["cantidad"]
            and anterior["detalle"] == item["detalle_personalizacion"]
            and anterior["color"] == item["color"]
            and anterior["precio_total"] == item["precio_total"]
        )

        precio_unitario = (
            item["precio_total"] / Decimal(item["cantidad"])
        ).quantize(CENTAVOS)

        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PERSONALIZADO",
            producto=item["producto"],
            cantidad=item["cantidad"],
            precio_unitario=precio_unitario,
            costo_unitario=_costo_actual_producto(item["producto"]),
            precio_total_personalizado=item["precio_total"],
            estado="LISTO" if conservar_listo else "PENDIENTE",
            personalizado=True,
            detalle_personalizacion=item["detalle_personalizacion"],
            color_personalizacion=item["color"],
        )

    EstadoImpresionPedido.objects.filter(pedido=pedido).exclude(
        producto_id__in=list(firma_nueva.keys())
    ).delete()

    _actualizar_estado_general_pedido(pedido)

    messages.success(request, f"{pedido.codigo} actualizado correctamente.")

    if volver_cliente and volver_cliente_id:
        return redirect("clientes:detalle", cliente_id=volver_cliente_id)
    return redirect("pedidos:impresiones")
