from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction, models
from django.db.models import Sum
from django.utils import timezone
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
    Pago,
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
            "pagos",
        )
        .order_by(
            "fecha_entrega",
            "id",
        )
    )

    pedidos_impresion = []

    # Stock físico actual.
    #
    # Se reserva virtualmente siguiendo
    # fecha de entrega + ID para impedir que una
    # misma unidad se asigne a dos pedidos.
    #
    # Los PERSONALIZADOS no consumen stock general:
    # fueron fabricados específicamente para su pedido.
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
                "detalle_personalizado_id": None,
                "puede_marcar_listo": False,
                "es_personalizado": False,
                "detalle_personalizacion": "",
                "color_personalizacion": "",
            }
        )

        personalizados = []

        # ==================================================
        # 1. AGRUPAR PRODUCTOS DEL PEDIDO
        # ==================================================

        for detalle in pedido.detalles.all():

            # ----------------------------------------------
            # PERSONALIZADO
            # ----------------------------------------------
            #
            # Se muestra como una fila independiente.
            # No se agrupa con productos normales aunque use
            # el mismo producto base.
            #
            # Tampoco depende del stock general.
            # ----------------------------------------------

            if (
                detalle.tipo_item == "PERSONALIZADO"
                and detalle.producto
                and detalle.producto.requiere_impresion
                and detalle.estado in ["PENDIENTE", "LISTO"]
            ):

                esta_listo = (
                    detalle.estado == "LISTO"
                )

                personalizados.append(
                    {
                        "producto": detalle.producto,
                        "cantidad_pedido": detalle.cantidad,
                        "cantidad": detalle.cantidad,
                        "stock_usado": 0,
                        "a_imprimir": (
                            0
                            if esta_listo
                            else detalle.cantidad
                        ),
                        "listo": esta_listo,
                        "estado_id": None,
                        "detalle_personalizado_id": detalle.id,
                        "puede_marcar_listo": True,
                        "es_personalizado": True,
                        "detalle_personalizacion":
                            detalle.detalle_personalizacion,
                        "color_personalizacion":
                            detalle.color_personalizacion,
                    }
                )

                continue

            # Los productos y kits normales siguen usando
            # el flujo existente de stock.
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
            item["es_personalizado"] = False

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
            # No debemos volver a consumir stock virtual.
            # ==================================================

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

            # Para productos normales sólo se permite marcar
            # LISTO cuando todo el pedido puede cubrirse
            # con stock general.
            item["puede_marcar_listo"] = (
                stock_usado >= cantidad
            )

            # Reservar virtualmente para pedidos posteriores.
            stock_disponible[
                producto.id
            ] = (
                disponible - stock_usado
            )

            lista_productos.append(item)

        # Los personalizados se agregan como filas propias.
        lista_productos.extend(
            personalizados
        )

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
                    "total_pedido": pedido.total,
                    "total_pagado": pedido.total_pagado,
                    "saldo_pendiente": pedido.saldo_pendiente,
                    "estado_pago": pedido.estado_pago,
                    "estado_pago_display": pedido.estado_pago_display,
                    "pagos": list(pedido.pagos.all()),
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
    cliente_inicial_id = request.GET.get("cliente", "").strip()

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
                "El pedido debe tener al menos un producto, kit o personalizado."
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


            # =====================================
            # PERSONALIZADO
            # =====================================

            elif tipo_item == "PERSONALIZADO":

                producto_id = request.POST.get(
                    f"producto_personalizado_{indice}"
                )

                detalle_personalizacion = request.POST.get(
                    f"detalle_personalizacion_{indice}",
                    ""
                ).strip()

                color_personalizacion = request.POST.get(
                    f"color_personalizacion_{indice}",
                    ""
                ).strip()

                precio_total_texto = request.POST.get(
                    f"precio_total_personalizado_{indice}",
                    ""
                ).strip()

                if not producto_id:
                    messages.error(
                        request,
                        "Debés seleccionar un producto base para el personalizado."
                    )

                    transaction.set_rollback(True)

                    return redirect(
                        "pedidos:nuevo"
                    )

                if not detalle_personalizacion:
                    messages.error(
                        request,
                        "Debés ingresar el detalle de la personalización."
                    )

                    transaction.set_rollback(True)

                    return redirect(
                        "pedidos:nuevo"
                    )

                try:
                    precio_total = Decimal(
                        precio_total_texto
                    )

                except (
                    InvalidOperation,
                    TypeError,
                    ValueError,
                ):
                    precio_total = Decimal("0")

                if precio_total <= 0:
                    messages.error(
                        request,
                        "El precio total del personalizado debe ser mayor a cero."
                    )

                    transaction.set_rollback(True)

                    return redirect(
                        "pedidos:nuevo"
                    )

                producto = get_object_or_404(
                    Producto,
                    id=producto_id,
                    activo=True,
                )

                precio_unitario = (
                    precio_total
                    / Decimal(cantidad)
                ).quantize(
                    Decimal("0.01")
                )

                DetallePedido.objects.create(
                    pedido=pedido,
                    tipo_item="PERSONALIZADO",
                    producto=producto,
                    cantidad=cantidad,
                    precio_unitario=precio_unitario,
                    precio_total_personalizado=precio_total,
                    estado="PENDIENTE",
                    personalizado=True,
                    detalle_personalizacion=detalle_personalizacion,
                    color_personalizacion=color_personalizacion,
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
            "cliente_inicial_id": cliente_inicial_id,
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


def _actualizar_estado_general_pedido(pedido):
    """
    Actualiza el estado general considerando:

    - productos normales / kits:
      EstadoImpresionPedido

    - personalizados:
      DetallePedido.estado

    Los personalizados no consumen stock general.
    """

    estados_normales = (
        EstadoImpresionPedido.objects
        .filter(
            pedido=pedido
        )
    )

    cantidad_normales = (
        estados_normales.count()
    )

    normales_listos = (
        estados_normales
        .filter(
            listo=True
        )
        .count()
    )

    personalizados = (
        DetallePedido.objects
        .filter(
            pedido=pedido,
            tipo_item="PERSONALIZADO",
            producto__requiere_impresion=True,
            estado__in=[
                "PENDIENTE",
                "LISTO",
            ],
        )
    )

    cantidad_personalizados = (
        personalizados.count()
    )

    personalizados_listos = (
        personalizados
        .filter(
            estado="LISTO"
        )
        .count()
    )

    cantidad_total = (
        cantidad_normales
        + cantidad_personalizados
    )

    cantidad_listos = (
        normales_listos
        + personalizados_listos
    )

    if pedido.estado in [
        "ENTREGADO",
        "CANCELADO",
    ]:
        return

    if (
        cantidad_total > 0
        and cantidad_total == cantidad_listos
    ):
        pedido.estado = "LISTO"

    elif cantidad_listos > 0:
        pedido.estado = "PREPARANDO"

    else:
        pedido.estado = "PENDIENTE"

    pedido.save(
        update_fields=[
            "estado"
        ]
    )


@transaction.atomic
def cambiar_listo_impresion(request):
    if request.method != "POST":
        return redirect(
            "pedidos:impresiones"
        )

    marcar_listo = (
        request.POST.get("listo")
        == "1"
    )

    detalle_personalizado_id = (
        request.POST.get(
            "detalle_personalizado_id"
        )
    )

    # ==================================================
    # PERSONALIZADO
    # ==================================================
    #
    # No modifica Producto.stock.
    # El estado se guarda directamente en DetallePedido.
    # ==================================================

    if detalle_personalizado_id:

        detalle = get_object_or_404(
            DetallePedido.objects
            .select_for_update()
            .select_related(
                "pedido",
                "producto",
            ),
            id=detalle_personalizado_id,
            tipo_item="PERSONALIZADO",
        )

        pedido = (
            Pedido.objects
            .select_for_update()
            .get(
                id=detalle.pedido_id
            )
        )

        if pedido.estado in [
            "ENTREGADO",
            "CANCELADO",
        ]:
            messages.error(
                request,
                (
                    "No se puede modificar un pedido "
                    "entregado o cancelado."
                ),
            )

            return redirect(
                "pedidos:impresiones"
            )

        detalle.estado = (
            "LISTO"
            if marcar_listo
            else "PENDIENTE"
        )

        detalle.save(
            update_fields=[
                "estado"
            ]
        )

        _actualizar_estado_general_pedido(
            pedido
        )

        return redirect(
            "pedidos:impresiones"
        )

    # ==================================================
    # PRODUCTO NORMAL / KIT
    # ==================================================

    estado_id = request.POST.get(
        "estado_id"
    )

    estado_impresion = get_object_or_404(
        EstadoImpresionPedido.objects
        .select_for_update(),
        id=estado_id,
    )

    pedido = (
        Pedido.objects
        .select_for_update()
        .get(
            id=estado_impresion.pedido_id,
        )
    )

    producto = (
        Producto.objects
        .select_for_update()
        .get(
            id=estado_impresion.producto_id,
        )
    )

    # ==================================================
    # MARCAR COMO LISTO
    # ==================================================

    if (
        marcar_listo
        and not estado_impresion.listo
    ):

        cantidad_necesaria = (
            _cantidad_producto_en_pedido(
                pedido,
                producto.id,
            )
        )

        stock_disponible = (
            _stock_disponible_para_pedido(
                pedido,
                producto,
            )
        )

        if cantidad_necesaria <= 0:

            messages.error(
                request,
                (
                    "No se encontró demanda pendiente "
                    f"para {producto.nombre}."
                ),
            )

            return redirect(
                "pedidos:impresiones"
            )

        if (
            stock_disponible
            < cantidad_necesaria
        ):

            messages.error(
                request,
                (
                    f"No hay stock suficiente de {producto.nombre}. "
                    f"Este pedido necesita {cantidad_necesaria} y "
                    f"solo tiene {stock_disponible} disponible "
                    "según prioridad."
                ),
            )

            return redirect(
                "pedidos:impresiones"
            )

        producto.stock -= (
            cantidad_necesaria
        )

        producto.save(
            update_fields=[
                "stock"
            ]
        )

        estado_impresion.cantidad_stock_descontada = (
            cantidad_necesaria
        )

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

    elif (
        not marcar_listo
        and estado_impresion.listo
    ):

        if estado_impresion.stock_descontado:

            producto.stock += (
                estado_impresion
                .cantidad_stock_descontada
            )

            producto.save(
                update_fields=[
                    "stock"
                ]
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

    _actualizar_estado_general_pedido(
        pedido
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
            "estados_impresion",
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
            "cantidad_normal": 0,
            "cantidad_personalizada": 0,
            "stock": 0,
            "a_imprimir": 0,
        }
    )

    # ==========================================
    # 1. AGRUPAR DEMANDA PENDIENTE
    # ==========================================
    #
    # PRODUCTOS / KITS:
    # - sí pueden cubrirse con stock general.
    #
    # PERSONALIZADOS:
    # - siempre deben fabricarse para su pedido.
    # - NO se descuentan del stock general.
    #
    # Los productos ya marcados LISTO en
    # "Impresiones por pedido" tampoco deben
    # volver a aparecer como demanda pendiente.
    # ==========================================

    for pedido in pedidos:

        productos_normales_listos = {
            estado.producto_id
            for estado in pedido.estados_impresion.all()
            if estado.listo
        }

        for detalle in pedido.detalles.all():

            if detalle.estado in [
                "CANCELADO",
                "ENTREGADO",
            ]:
                continue

            # --------------------------------------
            # PERSONALIZADO
            # --------------------------------------

            if (
                detalle.tipo_item == "PERSONALIZADO"
                and detalle.producto
                and detalle.producto.requiere_impresion
            ):

                # Si ya fue marcado LISTO desde
                # Impresiones por pedido, no queda
                # pendiente de fabricación.
                if detalle.estado == "LISTO":
                    continue

                producto = detalle.producto

                item = productos_agrupados[
                    producto.id
                ]

                item["producto"] = producto

                item["cantidad_personalizada"] += (
                    detalle.cantidad
                )

                item["cantidad_pedida"] += (
                    detalle.cantidad
                )

                continue

            # --------------------------------------
            # PRODUCTO INDIVIDUAL NORMAL
            # --------------------------------------

            if (
                detalle.tipo_item == "PRODUCTO"
                and detalle.producto
                and detalle.producto.requiere_impresion
            ):

                producto = detalle.producto

                # Ya está preparado para este pedido.
                if (
                    producto.id
                    in productos_normales_listos
                ):
                    continue

                item = productos_agrupados[
                    producto.id
                ]

                item["producto"] = producto

                item["cantidad_normal"] += (
                    detalle.cantidad
                )

                item["cantidad_pedida"] += (
                    detalle.cantidad
                )

            # --------------------------------------
            # PRODUCTOS DE KIT
            # --------------------------------------

            elif (
                detalle.tipo_item == "KIT"
                and detalle.kit
            ):

                for componente in (
                    detalle.productos_kit.all()
                ):

                    producto = componente.producto

                    if not producto.requiere_impresion:
                        continue

                    # Ya está preparado para este pedido.
                    if (
                        producto.id
                        in productos_normales_listos
                    ):
                        continue

                    item = productos_agrupados[
                        producto.id
                    ]

                    item["producto"] = producto

                    item["cantidad_normal"] += (
                        componente.cantidad
                    )

                    item["cantidad_pedida"] += (
                        componente.cantidad
                    )

    # ==========================================
    # 2. CALCULAR A IMPRIMIR
    # ==========================================
    #
    # Sólo la demanda NORMAL puede cubrirse
    # con stock general.
    #
    # Los PERSONALIZADOS se suman completos
    # a "A IMPRIMIR".
    #
    # Ejemplo:
    #
    # Normal pendiente:       5
    # Stock:                  3
    # Personalizado:         20
    #
    # Falta normal:           2
    # A imprimir total:      22
    # ==========================================

    lista_productos = []

    for item in productos_agrupados.values():

        producto = item["producto"]

        cantidad_normal = (
            item["cantidad_normal"]
        )

        cantidad_personalizada = (
            item["cantidad_personalizada"]
        )

        stock = producto.stock

        falta_normal = max(
            cantidad_normal - stock,
            0,
        )

        a_imprimir = (
            falta_normal
            + cantidad_personalizada
        )

        item["stock"] = stock
        item["a_imprimir"] = a_imprimir

        if a_imprimir >= 6:
            item["prioridad"] = "ALTA"
            item["prioridad_clase"] = (
                "prioridad-alta"
            )

        elif a_imprimir >= 3:
            item["prioridad"] = "MEDIA"
            item["prioridad_clase"] = (
                "prioridad-media"
            )

        elif a_imprimir >= 1:
            item["prioridad"] = "BAJA"
            item["prioridad_clase"] = (
                "prioridad-baja"
            )

        else:
            item["prioridad"] = (
                "SIN NECESIDAD"
            )
            item["prioridad_clase"] = (
                "prioridad-cero"
            )

        lista_productos.append(
            item
        )

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
# PAGOS
# ==========================================================

def pagos(request):
    hoy = timezone.localdate()
    inicio_mes = hoy.replace(day=1)

    filtro_estado = request.GET.get("estado", "TODOS").upper()
    busqueda = request.GET.get("q", "").strip()

    pedidos = (
        Pedido.objects
        .exclude(estado="CANCELADO")
        .select_related("cliente")
        .prefetch_related(
            "detalles",
            "pagos",
        )
        .order_by(
            "fecha_entrega",
            "id",
        )
    )

    if busqueda:
        pedidos = pedidos.filter(
            models.Q(cliente__nombre__icontains=busqueda)
            | models.Q(id__icontains=busqueda)
        )

    filas = []

    saldo_total = Decimal("0")
    pedidos_con_saldo = 0

    for pedido in pedidos:
        total = pedido.total
        pagado = pedido.total_pagado
        saldo = pedido.saldo_pendiente
        estado_pago = pedido.estado_pago

        if saldo > 0:
            saldo_total += saldo
            pedidos_con_saldo += 1

        if (
            filtro_estado != "TODOS"
            and estado_pago != filtro_estado
        ):
            continue

        filas.append(
            {
                "pedido": pedido,
                "total": total,
                "pagado": pagado,
                "saldo": saldo,
                "estado_pago": estado_pago,
                "estado_pago_display": pedido.estado_pago_display,
                "pagos": list(pedido.pagos.all()),
            }
        )

    cobrado_hoy = (
        Pago.objects
        .filter(fecha__date=hoy)
        .aggregate(total=Sum("monto"))
        .get("total")
        or Decimal("0")
    )

    cobrado_mes = (
        Pago.objects
        .filter(fecha__date__gte=inicio_mes)
        .aggregate(total=Sum("monto"))
        .get("total")
        or Decimal("0")
    )

    ultimos_pagos = (
        Pago.objects
        .select_related(
            "pedido",
            "pedido__cliente",
        )
        .order_by("-fecha", "-id")[:8]
    )

    return render(
        request,
        "pedidos/pagos.html",
        {
            "filas": filas,
            "filtro_estado": filtro_estado,
            "busqueda": busqueda,
            "cobrado_hoy": cobrado_hoy,
            "cobrado_mes": cobrado_mes,
            "saldo_total": saldo_total,
            "pedidos_con_saldo": pedidos_con_saldo,
            "ultimos_pagos": ultimos_pagos,
        },
    )


# ==========================================================
# REGISTRAR PAGO
# ==========================================================

@transaction.atomic
def registrar_pago(request, pedido_id):
    origen = request.POST.get("origen", "impresiones")
    cliente_id = request.POST.get("cliente_id")

    def volver():
        if origen == "pagos":
            return redirect("pedidos:pagos")

        if origen == "cliente" and cliente_id:
            return redirect(
                "clientes:detalle",
                cliente_id=cliente_id,
            )

        return redirect("pedidos:impresiones")

    if request.method != "POST":
        return redirect("pedidos:impresiones")

    pedido = get_object_or_404(
        Pedido.objects
        .select_for_update()
        .prefetch_related("detalles", "pagos"),
        id=pedido_id,
    )

    if pedido.estado == "CANCELADO":
        messages.error(
            request,
            "No se pueden registrar pagos en un pedido cancelado."
        )
        return volver()

    monto_texto = request.POST.get("monto", "").strip().replace(" ", "")
    if "," in monto_texto and "." not in monto_texto:
        monto_texto = monto_texto.replace(",", ".")

    medio = request.POST.get("medio", "").strip()
    observaciones = request.POST.get("observaciones", "").strip()

    try:
        monto = Decimal(monto_texto)
    except (InvalidOperation, TypeError, ValueError):
        monto = Decimal("0")

    medios_validos = {valor for valor, _ in Pago.MEDIOS}

    if monto <= 0:
        messages.error(request, "El monto del pago debe ser mayor a cero.")
        return volver()

    if medio not in medios_validos:
        messages.error(request, "Seleccioná un medio de pago válido.")
        return volver()

    saldo = pedido.saldo_pendiente

    if saldo <= 0:
        messages.warning(
            request,
            f"{pedido.codigo} ya se encuentra completamente pagado."
        )
        return volver()

    if monto > saldo:
        messages.error(
            request,
            (
                f"El pago (${monto:.2f}) supera el saldo pendiente "
                f"(${saldo:.2f})."
            )
        )
        return volver()

    Pago.objects.create(
        pedido=pedido,
        monto=monto,
        medio=medio,
        observaciones=observaciones,
    )

    nuevo_saldo = pedido.saldo_pendiente

    if nuevo_saldo <= 0:
        messages.success(
            request,
            f"Pago registrado. {pedido.codigo} quedó PAGADO."
        )
    else:
        messages.success(
            request,
            (
                f"Pago registrado en {pedido.codigo}. "
                f"Saldo pendiente: ${nuevo_saldo:.2f}."
            )
        )

    return volver()


# ==========================================================
# EDITAR PEDIDO
# ==========================================================

def _restaurar_estado_impresion_para_edicion(pedido, producto_id):
    """
    Si el producto estaba marcado LISTO, devuelve al stock exactamente
    lo que se había descontado y elimina su estado operativo anterior.
    """
    estado = (
        EstadoImpresionPedido.objects
        .select_for_update()
        .filter(
            pedido=pedido,
            producto_id=producto_id,
        )
        .first()
    )

    if not estado:
        return

    if estado.stock_descontado and estado.cantidad_stock_descontada:
        producto = (
            Producto.objects
            .select_for_update()
            .get(id=producto_id)
        )
        producto.stock += estado.cantidad_stock_descontada
        producto.save(update_fields=["stock"])

    estado.delete()


def _firmas_normales_del_pedido(pedido):
    """
    Firma por producto para PRODUCTO + componentes de KIT.
    Permite detectar qué productos normales cambiaron realmente.
    """
    firmas = defaultdict(int)

    for detalle in pedido.detalles.all():
        if detalle.tipo_item == "PRODUCTO" and detalle.producto_id:
            firmas[detalle.producto_id] += detalle.cantidad

        elif detalle.tipo_item == "KIT":
            for componente in detalle.productos_kit.all():
                firmas[componente.producto_id] += componente.cantidad

    return dict(firmas)


@transaction.atomic
def editar_pedido(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects
        .select_for_update()
        .select_related("cliente"),
        id=pedido_id,
    )

    if pedido.estado in ["ENTREGADO", "CANCELADO"]:
        messages.error(
            request,
            "No se puede editar un pedido entregado o cancelado."
        )
        return redirect("pedidos:impresiones")

    clientes = Cliente.objects.filter(activo=True).order_by("nombre")
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

    detalles_actuales = list(
        pedido.detalles
        .select_related("producto", "kit")
        .prefetch_related("productos_kit__producto")
        .all()
    )

    if request.method == "GET":
        items_iniciales = []

        for detalle in detalles_actuales:
            item = {
                "id": detalle.id,
                "tipo_item": detalle.tipo_item,
                "cantidad": detalle.cantidad,
                "producto_id": detalle.producto_id,
                "kit_id": detalle.kit_id,
                "productos_kit_ids": [
                    componente.producto_id
                    for componente in detalle.productos_kit.all()
                ],
                "detalle_personalizacion":
                    detalle.detalle_personalizacion,
                "color_personalizacion":
                    detalle.color_personalizacion,
                "precio_total_personalizado":
                    (
                        str(detalle.precio_total_personalizado)
                        if detalle.precio_total_personalizado is not None
                        else ""
                    ),
            }
            items_iniciales.append(item)

        return render(
            request,
            "pedidos/editar_pedido.html",
            {
                "pedido": pedido,
                "clientes": clientes,
                "productos": productos,
                "kits": kits,
                "items_iniciales": items_iniciales,
            },
        )

    # ------------------------------------------------------
    # DATOS GENERALES
    # ------------------------------------------------------
    cliente_id = request.POST.get("cliente")
    fecha_entrega = request.POST.get("fecha_entrega")
    observaciones = request.POST.get("observaciones", "").strip()

    cliente = get_object_or_404(
        Cliente,
        id=cliente_id,
        activo=True,
    )

    indices = request.POST.getlist("item_indice")
    if not indices:
        messages.error(
            request,
            "El pedido debe tener al menos un producto, kit o personalizado."
        )
        transaction.set_rollback(True)
        return redirect("pedidos:editar", pedido_id=pedido.id)

    # Firma anterior de demanda normal.
    pedido_prefetch = (
        Pedido.objects
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
        )
        .get(id=pedido.id)
    )
    firma_anterior = _firmas_normales_del_pedido(pedido_prefetch)

    # Personalizados LISTO se conservan solamente si el detalle existente
    # queda exactamente igual.
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

    # Construimos primero los nuevos datos sin tocar la base.
    nuevos_items = []

    for indice in indices:
        detalle_id_texto = request.POST.get(
            f"detalle_id_{indice}", ""
        ).strip()

        try:
            detalle_id = int(detalle_id_texto) if detalle_id_texto else None
        except (TypeError, ValueError):
            detalle_id = None

        tipo_item = request.POST.get(f"tipo_item_{indice}")
        cantidad_texto = request.POST.get(f"cantidad_{indice}", "1")

        try:
            cantidad = int(cantidad_texto)
        except (TypeError, ValueError):
            cantidad = 0

        if cantidad <= 0:
            messages.error(
                request,
                "Las cantidades deben ser mayores a cero."
            )
            transaction.set_rollback(True)
            return redirect("pedidos:editar", pedido_id=pedido.id)

        if tipo_item == "PRODUCTO":
            producto = get_object_or_404(
                Producto,
                id=request.POST.get(f"producto_{indice}"),
                activo=True,
            )
            nuevos_items.append({
                "detalle_id": detalle_id,
                "tipo_item": "PRODUCTO",
                "cantidad": cantidad,
                "producto": producto,
            })

        elif tipo_item == "KIT":
            kit = get_object_or_404(
                Kit,
                id=request.POST.get(f"kit_{indice}"),
                activo=True,
            )
            productos_kit_ids = request.POST.getlist(
                f"productos_kit_{indice}"
            )

            if len(productos_kit_ids) != kit.cantidad_productos:
                messages.error(
                    request,
                    f"El kit {kit.nombre} necesita "
                    f"{kit.cantidad_productos} productos."
                )
                transaction.set_rollback(True)
                return redirect("pedidos:editar", pedido_id=pedido.id)

            componentes = defaultdict(int)
            for producto_id in productos_kit_ids:
                producto = get_object_or_404(
                    Producto,
                    id=producto_id,
                    activo=True,
                    tipo=kit.tipo_producto,
                )
                componentes[producto.id] += cantidad

            nuevos_items.append({
                "detalle_id": detalle_id,
                "tipo_item": "KIT",
                "cantidad": cantidad,
                "kit": kit,
                "componentes": dict(componentes),
            })

        elif tipo_item == "PERSONALIZADO":
            producto = get_object_or_404(
                Producto,
                id=request.POST.get(
                    f"producto_personalizado_{indice}"
                ),
                activo=True,
            )
            detalle_personalizacion = request.POST.get(
                f"detalle_personalizacion_{indice}", ""
            ).strip()
            color = request.POST.get(
                f"color_personalizacion_{indice}", ""
            ).strip()
            precio_texto = request.POST.get(
                f"precio_total_personalizado_{indice}", ""
            ).strip()

            if not detalle_personalizacion:
                messages.error(
                    request,
                    "Debés ingresar el detalle de la personalización."
                )
                transaction.set_rollback(True)
                return redirect("pedidos:editar", pedido_id=pedido.id)

            try:
                precio_total = Decimal(precio_texto)
            except (InvalidOperation, TypeError, ValueError):
                precio_total = Decimal("0")

            if precio_total <= 0:
                messages.error(
                    request,
                    "El precio total del personalizado debe ser mayor a cero."
                )
                transaction.set_rollback(True)
                return redirect("pedidos:editar", pedido_id=pedido.id)

            nuevos_items.append({
                "detalle_id": detalle_id,
                "tipo_item": "PERSONALIZADO",
                "cantidad": cantidad,
                "producto": producto,
                "detalle_personalizacion": detalle_personalizacion,
                "color": color,
                "precio_total": precio_total,
            })

        else:
            messages.error(
                request,
                "Existe un item del pedido que no es válido."
            )
            transaction.set_rollback(True)
            return redirect("pedidos:editar", pedido_id=pedido.id)

    # Firma nueva de productos normales.
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
        if firma_anterior.get(producto_id, 0)
        != firma_nueva.get(producto_id, 0)
    }

    # Si cambió la demanda de un producto normal, restauramos su LISTO.
    for producto_id in productos_afectados:
        _restaurar_estado_impresion_para_edicion(
            pedido,
            producto_id,
        )

    # Guardar cabecera.
    pedido.cliente = cliente
    pedido.fecha_entrega = fecha_entrega if fecha_entrega else None
    pedido.observaciones = observaciones
    pedido.save(
        update_fields=[
            "cliente",
            "fecha_entrega",
            "observaciones",
        ]
    )

    # Reemplazamos detalles, pero conservamos LISTO de personalizados
    # únicamente cuando el mismo detalle sigue idéntico.
    ids_nuevos_personalizados = set()

    # Eliminamos todos los detalles y recreamos. Los estados normales viven
    # aparte y sólo se resetearon para productos cuya demanda cambió.
    pedido.detalles.all().delete()

    for item in nuevos_items:
        if item["tipo_item"] == "PRODUCTO":
            DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="PRODUCTO",
                producto=item["producto"],
                cantidad=item["cantidad"],
                estado="PENDIENTE",
            )

        elif item["tipo_item"] == "KIT":
            detalle = DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="KIT",
                kit=item["kit"],
                cantidad=item["cantidad"],
                estado="PENDIENTE",
            )
            for producto_id, cantidad in item["componentes"].items():
                DetalleKitProducto.objects.create(
                    detalle=detalle,
                    producto_id=producto_id,
                    cantidad=cantidad,
                )

        else:
            anterior = personalizados_anteriores.get(
                item["detalle_id"]
            )
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
            ).quantize(Decimal("0.01"))

            DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="PERSONALIZADO",
                producto=item["producto"],
                cantidad=item["cantidad"],
                precio_unitario=precio_unitario,
                precio_total_personalizado=item["precio_total"],
                estado="LISTO" if conservar_listo else "PENDIENTE",
                personalizado=True,
                detalle_personalizacion=item["detalle_personalizacion"],
                color_personalizacion=item["color"],
            )

    # Eliminar estados normales que ya no corresponden a demanda actual.
    EstadoImpresionPedido.objects.filter(
        pedido=pedido
    ).exclude(
        producto_id__in=list(firma_nueva.keys())
    ).delete()

    _actualizar_estado_general_pedido(pedido)

    messages.success(
        request,
        f"{pedido.codigo} actualizado correctamente."
    )
    return redirect("pedidos:impresiones")

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


    if pedido.pagos.exists():
        messages.error(
            request,
            (
                f"{pedido.codigo} tiene pagos registrados y no puede "
                "eliminarse. Si corresponde, cancelá el pedido para "
                "conservar el historial financiero."
            )
        )
        return redirect("pedidos:impresiones")

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
