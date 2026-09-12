from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from clientes.models import Cliente
from kits.models import Kit
from productos.models import Producto

from .models import (
    Pedido,
    DetallePedido,
    DetalleKitProducto,
    EstadoImpresionPedido,
)
from collections import defaultdict

from django.shortcuts import render

from .models import Pedido


def impresiones_por_pedido(request):
    pedidos = (
        Pedido.objects
        .exclude(
            estado__in=[
                "ENTREGADO",
                "CANCELADO",
            ]
        )
        .select_related(
            "cliente"
        )
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
        )
        .order_by(
            "fecha_entrega",
            "id",
        )
    )

    pedidos_impresion = []

    # Stock disponible global.
    # Se va consumiendo según el orden
    # de fecha de entrega.
    stock_disponible = {}

    for pedido in pedidos:

        productos = defaultdict(
            lambda: {
                "producto": None,
                "cantidad_pedido": 0,
                "stock_usado": 0,
                "a_imprimir": 0,
                "estado": "PENDIENTE",
            }
        )

        # ==================================================
        # 1. AGRUPAR PRODUCTOS DEL PEDIDO
        # ==================================================

        for detalle in pedido.detalles.all():

            if detalle.estado != "PENDIENTE":
                continue

            # PRODUCTO INDIVIDUAL
            if (
                    detalle.tipo_item == "PRODUCTO"
                    and detalle.producto
                    and detalle.producto.requiere_impresion
            ):

                producto = detalle.producto

                productos[producto.id]["producto"] = producto

                productos[producto.id]["cantidad_pedido"] += (
                    detalle.cantidad
                )

            # PRODUCTOS DE KIT
            elif (
                    detalle.tipo_item == "KIT"
                    and detalle.kit
            ):

                for componente in detalle.productos_kit.all():

                    producto = componente.producto

                    if not producto.requiere_impresion:
                        continue

                    productos[producto.id]["producto"] = producto

                    productos[producto.id]["cantidad_pedido"] += (
                        componente.cantidad
                    )

        # ==================================================
        # 2. ASIGNAR STOCK Y CALCULAR A IMPRIMIR
        # ==================================================

        for item in productos.values():

            producto = item["producto"]

            if producto.id not in stock_disponible:
                stock_disponible[producto.id] = (
                    producto.stock
                )

            disponible = stock_disponible[
                producto.id
            ]

            cantidad = item[
                "cantidad_pedido"
            ]

            stock_usado = min(
                cantidad,
                disponible
            )

            a_imprimir = max(
                cantidad - stock_usado,
                0
            )

            item["stock_usado"] = stock_usado
            item["cantidad"] = cantidad
            item["a_imprimir"] = a_imprimir

            stock_disponible[producto.id] = (
                    disponible - stock_usado
            )

        # ==================================================
        # 3. SOLO PRODUCTOS QUE REALMENTE
        #    NECESITAN IMPRESIÓN
        # ==================================================

        lista_productos = []

        for item in productos.values():
            producto = item["producto"]

            estado_impresion, _ = (
                EstadoImpresionPedido.objects
                .get_or_create(
                    pedido=pedido,
                    producto=producto,
                    defaults={
                        "estado": "PENDIENTE"
                    }
                )
            )

            item["listo"] = estado_impresion.listo
            item["estado_id"] = estado_impresion.id

            lista_productos.append(item)

        if lista_productos:
            pedidos_impresion.append({

                "pedido":
                    pedido,

                "productos":
                    lista_productos,

                "total_a_imprimir":
                    sum(
                        item["a_imprimir"]
                        for item
                        in lista_productos
                    ),
            })

    return render(
        request,
        "pedidos/impresiones_por_pedido.html",
        {
            "pedidos_impresion":
                pedidos_impresion,
        }
    )


@transaction.atomic
def cambiar_estado_impresion(request):
    if request.method != "POST":
        return redirect(
            "pedidos:impresiones"
        )

    estado_id = request.POST.get(
        "estado_id"
    )

    nuevo_estado = request.POST.get(
        "estado"
    )

    estados_validos = [
        "PENDIENTE",
        "IMPRIMIENDO",
        "LISTO",
    ]

    if nuevo_estado not in estados_validos:
        return redirect(
            "pedidos:impresiones"
        )

    estado_impresion = get_object_or_404(
        EstadoImpresionPedido,
        id=estado_id
    )

    estado_impresion.estado = (
        nuevo_estado
    )

    estado_impresion.save(
        update_fields=["estado"]
    )

    return redirect(
        "pedidos:impresiones"
    )


def productos_por_kit(request, kit_id):
    kit = get_object_or_404(Kit, id=kit_id, activo=True)

    productos = (
        Producto.objects
        .filter(
            tipo=kit.tipo_producto,
            activo=True
        )
        .order_by("nombre")
    )

    return JsonResponse({
        "kit": {
            "id": kit.id,
            "nombre": kit.nombre,
            "cantidad_productos": kit.cantidad_productos,
            "tipo": kit.tipo_producto.nombre,
        },
        "productos": [
            {
                "id": producto.id,
                "codigo": producto.codigo,
                "nombre": producto.nombre,
            }
            for producto in productos
        ]
    })


@transaction.atomic
def nuevo_pedido(request):
    clientes = Cliente.objects.filter(
        activo=True
    ).order_by("nombre")

    productos = Producto.objects.filter(
        activo=True
    ).order_by("nombre")

    kits = Kit.objects.filter(
        activo=True
    ).order_by("nombre")

    if request.method == "POST":

        cliente_id = request.POST.get("cliente")
        fecha_entrega = request.POST.get("fecha_entrega")
        observaciones = request.POST.get("observaciones", "")

        if not cliente_id:
            messages.error(
                request,
                "Debés seleccionar un cliente."
            )

            return render(
                request,
                "pedidos/nuevo_pedido.html",
                {
                    "clientes": clientes,
                    "productos": productos,
                    "kits": kits,
                }
            )

        cliente = get_object_or_404(
            Cliente,
            id=cliente_id,
            activo=True
        )

        pedido = Pedido.objects.create(
            cliente=cliente,
            fecha_entrega=fecha_entrega or None,
            observaciones=observaciones,
        )

        indices = request.POST.getlist("item_indice")

        if not indices:
            messages.error(
                request,
                "El pedido debe contener al menos un ítem."
            )
            transaction.set_rollback(True)

            return redirect("pedidos:nuevo")

        for indice in indices:

            tipo_item = request.POST.get(
                f"tipo_item_{indice}"
            )

            cantidad = int(
                request.POST.get(
                    f"cantidad_{indice}",
                    1
                )
            )

            if tipo_item == "PRODUCTO":

                producto_id = request.POST.get(
                    f"producto_{indice}"
                )

                if not producto_id:
                    continue

                producto = get_object_or_404(
                    Producto,
                    id=producto_id,
                    activo=True
                )

                DetallePedido.objects.create(
                    pedido=pedido,
                    tipo_item="PRODUCTO",
                    producto=producto,
                    cantidad=cantidad,
                    precio_unitario=0,
                )

            elif tipo_item == "KIT":

                kit_id = request.POST.get(
                    f"kit_{indice}"
                )

                if not kit_id:
                    continue

                kit = get_object_or_404(
                    Kit,
                    id=kit_id,
                    activo=True
                )

                detalle = DetallePedido.objects.create(
                    pedido=pedido,
                    tipo_item="KIT",
                    kit=kit,
                    cantidad=cantidad,
                    precio_unitario=0,
                )

                componentes = request.POST.getlist(
                    f"componentes_{indice}"
                )

                cantidad_esperada = (
                        kit.cantidad_productos
                        * cantidad
                )

                if len(componentes) != cantidad_esperada:
                    transaction.set_rollback(True)

                    messages.error(
                        request,
                        f"El kit {kit.nombre} necesita "
                        f"{cantidad_esperada} productos."
                    )

                    return redirect("pedidos:nuevo")

                for producto_id in componentes:
                    producto = get_object_or_404(
                        Producto,
                        id=producto_id,
                        tipo=kit.tipo_producto,
                        activo=True
                    )

                    DetalleKitProducto.objects.create(
                        detalle=detalle,
                        producto=producto,
                        cantidad=1
                    )

        if not pedido.detalles.exists():
            transaction.set_rollback(True)

            messages.error(
                request,
                "No se agregó ningún producto al pedido."
            )

            return redirect("pedidos:nuevo")

        messages.success(
            request,
            f"Pedido {pedido.codigo} creado correctamente."
        )

        return redirect("pedidos:nuevo")

    return render(
        request,
        "pedidos/nuevo_pedido.html",
        {
            "clientes": clientes,
            "productos": productos,
            "kits": kits,
        }
    )


@transaction.atomic
def cambiar_listo_impresion(request):
    if request.method != "POST":
        return redirect("pedidos:impresiones")

    estado_id = request.POST.get("estado_id")

    estado_impresion = get_object_or_404(
        EstadoImpresionPedido.objects.select_for_update(),
        id=estado_id
    )

    pedido = Pedido.objects.select_for_update().get(
        id=estado_impresion.pedido_id
    )

    producto = Producto.objects.select_for_update().get(
        id=estado_impresion.producto_id
    )

    marcar_listo = request.POST.get("listo") == "1"

    # ==================================================
    # MARCAR COMO LISTO
    # ==================================================

    if marcar_listo and not estado_impresion.listo:

        cantidad_stock = int(
            request.POST.get(
                "stock_usado",
                0
            )
        )

        cantidad_stock = min(
            cantidad_stock,
            producto.stock
        )

        if cantidad_stock > 0:
            producto.stock -= cantidad_stock

            producto.save(
                update_fields=["stock"]
            )

        estado_impresion.cantidad_stock_descontada = (
            cantidad_stock
        )

        estado_impresion.stock_descontado = (
                cantidad_stock > 0
        )

        estado_impresion.listo = True

        estado_impresion.save()

    # ==================================================
    # VOLVER A PENDIENTE
    # ==================================================

    elif not marcar_listo and estado_impresion.listo:

        if estado_impresion.stock_descontado:
            producto.stock += (
                estado_impresion.cantidad_stock_descontada
            )

            producto.save(
                update_fields=["stock"]
            )

        estado_impresion.listo = False
        estado_impresion.stock_descontado = False
        estado_impresion.cantidad_stock_descontada = 0

        estado_impresion.save()

    # ==================================================
    # ACTUALIZAR ESTADO GENERAL DEL PEDIDO
    # ==================================================

    estados = (
        EstadoImpresionPedido.objects
        .filter(pedido=pedido)
    )

    cantidad_total = estados.count()

    cantidad_listos = estados.filter(
        listo=True
    ).count()

    # Si todas las filas están listas
    if (
            cantidad_total > 0
            and cantidad_total == cantidad_listos
    ):

        if pedido.estado not in [
            "ENTREGADO",
            "CANCELADO",
        ]:
            pedido.estado = "LISTO"

    # Si hay alguna lista, pero no todas
    elif cantidad_listos > 0:

        if pedido.estado not in [
            "ENTREGADO",
            "CANCELADO",
        ]:
            pedido.estado = "PREPARANDO"

    # Si ninguna está lista
    else:

        if pedido.estado not in [
            "ENTREGADO",
            "CANCELADO",
        ]:
            pedido.estado = "PENDIENTE"

    pedido.save(
        update_fields=["estado"]
    )

    return redirect(
        "pedidos:impresiones"
    )


def impresiones_por_producto(request):
    pedidos = (
        Pedido.objects
        .exclude(
            estado__in=[
                "ENTREGADO",
                "CANCELADO",
            ]
        )
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
        )
        .order_by(
            "fecha_entrega",
            "id",
        )
    )

    productos_agrupados = defaultdict(
        lambda: {
            "producto": None,
            "cantidad_pedida": 0,
            "stock": 0,
            "a_imprimir": 0,
        }
    )

    # ==========================================
    # 1. AGRUPAR TODA LA DEMANDA
    # ==========================================

    for pedido in pedidos:

        for detalle in pedido.detalles.all():

            if detalle.estado == "CANCELADO":
                continue

            # PRODUCTO INDIVIDUAL
            if (
                    detalle.tipo_item == "PRODUCTO"
                    and detalle.producto
                    and detalle.producto.requiere_impresion
            ):

                producto = detalle.producto

                productos_agrupados[
                    producto.id
                ]["producto"] = producto

                productos_agrupados[
                    producto.id
                ]["cantidad_pedida"] += (
                    detalle.cantidad
                )

            # PRODUCTOS DE KIT
            elif (
                    detalle.tipo_item == "KIT"
                    and detalle.kit
            ):

                for componente in detalle.productos_kit.all():

                    producto = componente.producto

                    if not producto.requiere_impresion:
                        continue

                    productos_agrupados[
                        producto.id
                    ]["producto"] = producto

                    productos_agrupados[
                        producto.id
                    ]["cantidad_pedida"] += (
                        componente.cantidad
                    )

    # ==========================================
    # 2. RESTAR STOCK
    # ==========================================

    lista_productos = []

    for item in productos_agrupados.values():

        producto = item["producto"]

        cantidad = item["cantidad_pedida"]
        stock = producto.stock

        a_imprimir = max(
            cantidad - stock,
            0
        )

        item["stock"] = stock
        item["a_imprimir"] = a_imprimir

        if a_imprimir >= 6:
            item["prioridad"] = "ALTA"
            item["prioridad_clase"] = "prioridad-alta"

        elif a_imprimir >= 3:
            item["prioridad"] = "MEDIA"
            item["prioridad_clase"] = "prioridad-media"

        elif a_imprimir >= 1:
            item["prioridad"] = "BAJA"
            item["prioridad_clase"] = "prioridad-baja"

        else:
            item["prioridad"] = "SIN NECESIDAD"
            item["prioridad_clase"] = "prioridad-cero"

        lista_productos.append(item)

    # ==========================================
    # 3. ORDENAR
    # ==========================================

    lista_productos.sort(
        key=lambda item: (
            -item["a_imprimir"],
            item["producto"].nombre.lower(),
        )
    )

    return render(
        request,
        "pedidos/impresiones_por_producto.html",
        {
            "productos":
                lista_productos,
        }
    )
