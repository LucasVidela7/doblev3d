from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from clientes.models import Cliente
from kits.models import Kit
from productos.models import Producto

from collections import defaultdict

from .models import (
    Pedido,
    DetallePedido,
    DetalleKitProducto,
    EstadoImpresionPedido,
)


def impresiones_por_pedido(request):
    pedidos = (
        Pedido.objects
        .exclude(
            estado__in=[
                "ENTREGADO",
                "CANCELADO",
            ]
        )
        .select_related("cliente")
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

    # Stock físico actual.
    #
    # Se irá reservando virtualmente siguiendo
    # fecha de entrega + ID para impedir que una
    # misma unidad se asigne a dos pedidos.
    stock_disponible = {}

    for pedido in pedidos:

        productos = defaultdict(
            lambda: {
                "producto": None,
                "cantidad_pedido": 0,
                "cantidad": 0,
                "stock_usado": 0,
                "a_imprimir": 0,
                "listo": False,
                "estado_id": None,
                "puede_marcar_listo": False,
            }
        )

        # ==================================================
        # 1. AGRUPAR PRODUCTOS DEL PEDIDO
        # ==================================================

        for detalle in pedido.detalles.all():

            if detalle.estado != "PENDIENTE":
                continue

            # ----------------------------------------------
            # PRODUCTO INDIVIDUAL
            # ----------------------------------------------

            if (
                    detalle.tipo_item == "PRODUCTO"
                    and detalle.producto
                    and detalle.producto.requiere_impresion
            ):

                producto = detalle.producto

                productos[
                    producto.id
                ]["producto"] = producto

                productos[
                    producto.id
                ]["cantidad_pedido"] += detalle.cantidad

            # ----------------------------------------------
            # PRODUCTOS DE KIT
            # ----------------------------------------------

            elif (
                    detalle.tipo_item == "KIT"
                    and detalle.kit
            ):

                for componente in detalle.productos_kit.all():

                    producto = componente.producto

                    if not producto.requiere_impresion:
                        continue

                    productos[
                        producto.id
                    ]["producto"] = producto

                    productos[
                        producto.id
                    ]["cantidad_pedido"] += (
                        componente.cantidad
                    )

        # ==================================================
        # 2. ASIGNAR STOCK SEGÚN PRIORIDAD
        # ==================================================

        lista_productos = []

        for item in productos.values():

            producto = item["producto"]

            cantidad = item["cantidad_pedido"]

            item["cantidad"] = cantidad

            # ----------------------------------------------
            # ESTADO DEL PRODUCTO DENTRO DEL PEDIDO
            # ----------------------------------------------

            estado_impresion, _ = (
                EstadoImpresionPedido.objects.get_or_create(
                    pedido=pedido,
                    producto=producto,
                    defaults={
                        "listo": False,
                    },
                )
            )

            item["listo"] = estado_impresion.listo
            item["estado_id"] = estado_impresion.id

            # ==================================================
            # YA ESTÁ LISTO
            # ==================================================
            #
            # El stock utilizado ya fue descontado físicamente.
            #
            # Por eso NO debemos volver a consumir stock virtual.
            #
            # El checkbox queda habilitado porque necesitamos
            # permitir desmarcarlo.

            if estado_impresion.listo:
                item["stock_usado"] = (
                    estado_impresion
                    .cantidad_stock_descontada
                )

                item["a_imprimir"] = 0

                item["puede_marcar_listo"] = True

                lista_productos.append(item)

                continue

            # ==================================================
            # PRODUCTO TODAVÍA PENDIENTE
            # ==================================================

            if producto.id not in stock_disponible:
                stock_disponible[
                    producto.id
                ] = producto.stock

            disponible = stock_disponible[
                producto.id
            ]

            # Cantidad de este pedido que puede cubrirse
            # con el stock que todavía no fue reservado.

            stock_usado = min(
                cantidad,
                disponible,
            )

            a_imprimir = max(
                cantidad - stock_usado,
                0,
            )

            item["stock_usado"] = stock_usado

            item["a_imprimir"] = a_imprimir

            # ==================================================
            # ¿SE PUEDE MARCAR LISTO?
            # ==================================================
            #
            # Solamente si TODO lo necesario para este pedido
            # está disponible.
            #
            # Ejemplo:
            #
            # Pedido necesita 3
            # Stock reservado disponible = 2
            #
            # -> NO se puede marcar listo.

            item["puede_marcar_listo"] = (
                    stock_usado >= cantidad
            )

            # Reservamos virtualmente ese stock para que
            # los pedidos siguientes no puedan utilizarlo.

            stock_disponible[
                producto.id
            ] = (
                    disponible - stock_usado
            )

            lista_productos.append(item)

        # ==================================================
        # 3. AGREGAR PEDIDO
        # ==================================================

        if lista_productos:
            pedidos_impresion.append(
                {
                    "pedido": pedido,

                    "productos": lista_productos,

                    "total_a_imprimir": sum(
                        item["a_imprimir"]
                        for item in lista_productos
                    ),
                }
            )

    return render(
        request,
        "pedidos/impresiones_por_pedido.html",
        {
            "pedidos_impresion":
                pedidos_impresion,
        },
    )


@transaction.atomic
def cambiar_estado_impresion(request):
    """
    Compatibilidad con una vista anterior.

    EstadoImpresionPedido ya no tiene un campo `estado`;
    actualmente usa el booleano `listo`.

    Si alguna URL o formulario viejo todavía llama a esta vista:
    - LISTO -> listo=True
    - PENDIENTE / IMPRIMIENDO -> listo=False

    La vista operativa actual recomendada es cambiar_listo_impresion().
    """
    if request.method != "POST":
        return redirect("pedidos:impresiones")

    estado_id = request.POST.get("estado_id")
    nuevo_estado = request.POST.get("estado")

    if nuevo_estado not in [
        "PENDIENTE",
        "IMPRIMIENDO",
        "LISTO",
    ]:
        return redirect("pedidos:impresiones")

    estado_impresion = get_object_or_404(
        EstadoImpresionPedido,
        id=estado_id,
    )

    estado_impresion.listo = (
            nuevo_estado == "LISTO"
    )

    estado_impresion.save(
        update_fields=["listo"]
    )

    return redirect("pedidos:impresiones")


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
    clientes = (
        Cliente.objects
        .filter(activo=True)
        .order_by("nombre")
    )

    productos = (
        Producto.objects
        .filter(activo=True)
        .select_related("tipo")
        .order_by("nombre")
    )

    kits = (
        Kit.objects
        .filter(activo=True)
        .select_related("tipo_producto")
        .order_by("nombre")
    )

    if request.method == "POST":

        cliente_id = request.POST.get("cliente")

        fecha_entrega = request.POST.get(
            "fecha_entrega"
        )

        observaciones = request.POST.get(
            "observaciones",
            ""
        ).strip()

        # =========================================
        # CLIENTE
        # =========================================

        if cliente_id == "NUEVO":

            nombre_cliente = request.POST.get(
                "nuevo_cliente_nombre",
                ""
            ).strip()

            telefono_cliente = request.POST.get(
                "nuevo_cliente_telefono",
                ""
            ).strip()

            email_cliente = request.POST.get(
                "nuevo_cliente_email",
                ""
            ).strip()

            if not nombre_cliente:
                messages.error(
                    request,
                    "Debés ingresar el nombre del nuevo cliente."
                )

                return redirect(
                    "pedidos:nuevo"
                )

            cliente = Cliente.objects.create(
                nombre=nombre_cliente,
                telefono=telefono_cliente,
                email=email_cliente,
                activo=True,
            )


        else:

            cliente = get_object_or_404(
                Cliente,
                id=cliente_id,
                activo=True,
            )

        # =========================================
        # CREAR PEDIDO
        # =========================================

        pedido = Pedido.objects.create(
            cliente=cliente,
            fecha_entrega=(
                fecha_entrega
                if fecha_entrega
                else None
            ),
            observaciones=observaciones,
            estado="PENDIENTE",
        )

        # =========================================
        # ITEMS
        # =========================================

        indices = request.POST.getlist(
            "item_indice"
        )

        if not indices:
            messages.error(
                request,
                "El pedido debe tener al menos un producto o kit."
            )

            transaction.set_rollback(True)

            return redirect(
                "pedidos:nuevo"
            )

        for indice in indices:

            tipo_item = request.POST.get(
                f"tipo_item_{indice}"
            )

            cantidad_texto = request.POST.get(
                f"cantidad_{indice}",
                "1"
            )

            try:
                cantidad = int(
                    cantidad_texto
                )

            except (TypeError, ValueError):
                cantidad = 0

            if cantidad <= 0:
                messages.error(
                    request,
                    "Las cantidades deben ser mayores a cero."
                )

                transaction.set_rollback(True)

                return redirect(
                    "pedidos:nuevo"
                )

            # =====================================
            # PRODUCTO
            # =====================================

            if tipo_item == "PRODUCTO":

                producto_id = request.POST.get(
                    f"producto_{indice}"
                )

                producto = get_object_or_404(
                    Producto,
                    id=producto_id,
                    activo=True,
                )

                DetallePedido.objects.create(
                    pedido=pedido,
                    tipo_item="PRODUCTO",
                    producto=producto,
                    cantidad=cantidad,
                    estado="PENDIENTE",
                )


            # =====================================
            # KIT
            # =====================================

            elif tipo_item == "KIT":

                kit_id = request.POST.get(
                    f"kit_{indice}"
                )

                kit = get_object_or_404(
                    Kit,
                    id=kit_id,
                    activo=True,
                )

                # Los selectores corresponden solamente
                # a los productos que contiene UN kit.
                #
                # Ejemplo:
                # Kit de 2 productos x cantidad 3:
                #
                # Producto 1: PIÑA
                # Producto 2: ESTRELLA
                #
                # Resultado:
                # PIÑA x3
                # ESTRELLA x3

                productos_kit_ids = request.POST.getlist(
                    f"productos_kit_{indice}"
                )

                if (
                        len(productos_kit_ids)
                        != kit.cantidad_productos
                ):
                    messages.error(
                        request,
                        (
                            f"El kit {kit.nombre} necesita "
                            f"{kit.cantidad_productos} productos."
                        )
                    )

                    transaction.set_rollback(True)

                    return redirect(
                        "pedidos:nuevo"
                    )

                detalle = DetallePedido.objects.create(
                    pedido=pedido,
                    tipo_item="KIT",
                    kit=kit,
                    cantidad=cantidad,
                    estado="PENDIENTE",
                )

                # =========================================
                # AGRUPAR COMPONENTES
                # =========================================

                productos_seleccionados = {}

                for producto_id in productos_kit_ids:

                    producto = get_object_or_404(
                        Producto,
                        id=producto_id,
                        activo=True,
                        tipo=kit.tipo_producto,
                    )

                    if producto.id not in productos_seleccionados:
                        productos_seleccionados[
                            producto.id
                        ] = {
                            "producto": producto,
                            "cantidad": 0,
                        }

                    # Cada producto seleccionado aparece
                    # una vez dentro del kit.
                    #
                    # La cantidad del detalle determina
                    # cuántas unidades reales necesitamos.

                    productos_seleccionados[
                        producto.id
                    ]["cantidad"] += cantidad

                # =========================================
                # GUARDAR COMPONENTES
                # =========================================

                for item in productos_seleccionados.values():
                    DetalleKitProducto.objects.create(
                        detalle=detalle,
                        producto=item["producto"],
                        cantidad=item["cantidad"],
                    )


            else:

                messages.error(
                    request,
                    "Existe un item del pedido que no es válido."
                )

                transaction.set_rollback(True)

                return redirect(
                    "pedidos:nuevo"
                )

        messages.success(
            request,
            f"{pedido.codigo} creado correctamente."
        )

        return redirect(
            "pedidos:nuevo"
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


def _cantidad_producto_en_pedido(pedido, producto_id):
    """Devuelve cuántas unidades de un producto necesita un pedido activo."""
    cantidad = 0

    for detalle in pedido.detalles.all():
        if detalle.estado != "PENDIENTE":
            continue

        if (
                detalle.tipo_item == "PRODUCTO"
                and detalle.producto_id == producto_id
        ):
            cantidad += detalle.cantidad

        elif detalle.tipo_item == "KIT" and detalle.kit_id:
            for componente in detalle.productos_kit.all():
                if componente.producto_id == producto_id:
                    cantidad += componente.cantidad

    return cantidad


def _stock_disponible_para_pedido(pedido, producto):
    """
    Calcula el stock que realmente le corresponde a este pedido,
    respetando la prioridad fecha_entrega + id.

    Los pedidos anteriores pendientes reservan stock virtualmente.
    Los productos ya marcados LISTO no vuelven a reservar porque su
    stock ya fue descontado físicamente de Producto.stock.
    """
    stock_virtual = producto.stock

    pedidos_activos = (
        Pedido.objects
        .exclude(estado__in=["ENTREGADO", "CANCELADO"])
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
        )
        .order_by("fecha_entrega", "id")
    )

    for pedido_actual in pedidos_activos:
        if pedido_actual.id == pedido.id:
            return stock_virtual

        estado_anterior = (
            EstadoImpresionPedido.objects
            .filter(
                pedido=pedido_actual,
                producto=producto,
                listo=True,
            )
            .first()
        )

        if estado_anterior:
            # Ese stock ya fue descontado físicamente.
            continue

        cantidad_anterior = _cantidad_producto_en_pedido(
            pedido_actual,
            producto.id,
        )

        reservado = min(cantidad_anterior, stock_virtual)
        stock_virtual -= reservado

    return 0


@transaction.atomic
def cambiar_listo_impresion(request):
    if request.method != "POST":
        return redirect("pedidos:impresiones")

    estado_id = request.POST.get("estado_id")

    estado_impresion = get_object_or_404(
        EstadoImpresionPedido.objects.select_for_update(),
        id=estado_id,
    )

    pedido = Pedido.objects.select_for_update().get(
        id=estado_impresion.pedido_id,
    )

    producto = Producto.objects.select_for_update().get(
        id=estado_impresion.producto_id,
    )

    marcar_listo = request.POST.get("listo") == "1"

    # ==================================================
    # MARCAR COMO LISTO
    # ==================================================
    if marcar_listo and not estado_impresion.listo:
        cantidad_necesaria = _cantidad_producto_en_pedido(
            pedido,
            producto.id,
        )

        stock_disponible = _stock_disponible_para_pedido(
            pedido,
            producto,
        )

        if cantidad_necesaria <= 0:
            messages.error(
                request,
                f"No se encontró demanda pendiente para {producto.nombre}.",
            )
            return redirect("pedidos:impresiones")

        if stock_disponible < cantidad_necesaria:
            messages.error(
                request,
                (
                    f"No hay stock suficiente de {producto.nombre}. "
                    f"Este pedido necesita {cantidad_necesaria} y "
                    f"solo tiene {stock_disponible} disponible según prioridad."
                ),
            )
            return redirect("pedidos:impresiones")

        producto.stock -= cantidad_necesaria
        producto.save(update_fields=["stock"])

        estado_impresion.cantidad_stock_descontada = cantidad_necesaria
        estado_impresion.stock_descontado = True
        estado_impresion.listo = True
        estado_impresion.save(
            update_fields=[
                "cantidad_stock_descontada",
                "stock_descontado",
                "listo",
            ]
        )

    # ==================================================
    # VOLVER A PENDIENTE
    # ==================================================
    elif not marcar_listo and estado_impresion.listo:
        if estado_impresion.stock_descontado:
            producto.stock += estado_impresion.cantidad_stock_descontada
            producto.save(update_fields=["stock"])

        estado_impresion.listo = False
        estado_impresion.stock_descontado = False
        estado_impresion.cantidad_stock_descontada = 0
        estado_impresion.save(
            update_fields=[
                "listo",
                "stock_descontado",
                "cantidad_stock_descontada",
            ]
        )

    # ==================================================
    # ACTUALIZAR ESTADO GENERAL DEL PEDIDO
    # ==================================================
    estados = EstadoImpresionPedido.objects.filter(pedido=pedido)
    cantidad_total = estados.count()
    cantidad_listos = estados.filter(listo=True).count()

    if pedido.estado not in ["ENTREGADO", "CANCELADO"]:
        if cantidad_total > 0 and cantidad_total == cantidad_listos:
            pedido.estado = "LISTO"
        elif cantidad_listos > 0:
            pedido.estado = "PREPARANDO"
        else:
            pedido.estado = "PENDIENTE"

        pedido.save(update_fields=["estado"])

    return redirect("pedidos:impresiones")


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


# ==========================================================
# ENTREGAR PEDIDO
# ==========================================================

@transaction.atomic
def entregar_pedido(request, pedido_id):
    if request.method != "POST":
        return redirect("dashboard:inicio")

    pedido = get_object_or_404(
        Pedido.objects.select_for_update(),
        id=pedido_id,
    )

    if pedido.estado == "CANCELADO":
        messages.error(
            request,
            "No se puede entregar un pedido cancelado."
        )

        return redirect(
            "pedidos:impresiones"
        )

    pedido.estado = "ENTREGADO"

    pedido.save(
        update_fields=["estado"]
    )

    messages.success(
        request,
        f"{pedido.codigo} marcado como ENTREGADO."
    )

    return redirect(
        "pedidos:impresiones"
    )


# ==========================================================
# CANCELAR PEDIDO
# ==========================================================

@transaction.atomic
def cancelar_pedido(request, pedido_id):
    if request.method != "POST":
        return redirect("dashboard:inicio")

    pedido = get_object_or_404(
        Pedido.objects.select_for_update(),
        id=pedido_id,
    )

    if pedido.estado == "ENTREGADO":
        messages.error(
            request,
            "Un pedido entregado no puede cancelarse."
        )

        return redirect(
            "pedidos:impresiones"
        )

    # ------------------------------------------------------
    # DEVOLVER AL STOCK LAS UNIDADES QUE HABÍAN SIDO
    # DESCONTADAS AL MARCAR PRODUCTOS COMO LISTO
    # ------------------------------------------------------

    estados_impresion = (
        EstadoImpresionPedido.objects
        .select_for_update()
        .filter(
            pedido=pedido,
            stock_descontado=True,
        )
        .select_related("producto")
    )

    for estado_impresion in estados_impresion:
        producto = Producto.objects.select_for_update().get(
            id=estado_impresion.producto_id
        )

        producto.stock += (
            estado_impresion.cantidad_stock_descontada
        )

        producto.save(
            update_fields=["stock"]
        )

        estado_impresion.listo = False
        estado_impresion.stock_descontado = False
        estado_impresion.cantidad_stock_descontada = 0

        estado_impresion.save(
            update_fields=[
                "listo",
                "stock_descontado",
                "cantidad_stock_descontada",
            ]
        )

    pedido.estado = "CANCELADO"

    pedido.save(
        update_fields=["estado"]
    )

    messages.success(
        request,
        f"{pedido.codigo} fue CANCELADO."
    )

    return redirect(
        "pedidos:impresiones"
    )


# ==========================================================
# ELIMINAR PEDIDO
# ==========================================================

@transaction.atomic
def eliminar_pedido(request, pedido_id):
    if request.method != "POST":
        return redirect("dashboard:inicio")

    pedido = get_object_or_404(
        Pedido.objects.select_for_update(),
        id=pedido_id,
    )

    codigo_pedido = pedido.codigo

    # ------------------------------------------------------
    # RESTAURAR STOCK ANTES DE ELIMINAR
    # ------------------------------------------------------

    estados_impresion = (
        EstadoImpresionPedido.objects
        .select_for_update()
        .filter(
            pedido=pedido,
            stock_descontado=True,
        )
        .select_related("producto")
    )

    for estado_impresion in estados_impresion:
        producto = Producto.objects.select_for_update().get(
            id=estado_impresion.producto_id
        )

        producto.stock += (
            estado_impresion.cantidad_stock_descontada
        )

        producto.save(
            update_fields=["stock"]
        )

    # ------------------------------------------------------
    # BORRAR PEDIDO
    #
    # Los DetallePedido y EstadoImpresionPedido asociados
    # deberían eliminarse automáticamente si sus ForeignKey
    # usan on_delete=models.CASCADE.
    # ------------------------------------------------------

    pedido.delete()

    messages.success(
        request,
        f"{codigo_pedido} eliminado correctamente."
    )

    return redirect(
        "pedidos:impresiones"
    )
