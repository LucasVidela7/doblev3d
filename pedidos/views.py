from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib import messages
from django.db import transaction, models
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.utils import timezone
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from clientes.models import Cliente
from clientes.telefonos import buscar_cliente_por_telefono
from kits.models import Kit
from productos.models import Insumo, Producto
from produccion.models import Produccion
from calculadora.precios import (
    fila_precio,
    margenes_escenario,
)


from collections import defaultdict
from calendar import monthrange
from datetime import date, datetime, time, timedelta

from .empaques import (
    _restaurar_uso_empaque,
    costo_embalaje_para_rentabilidad,
)
from .finanzas_services import crear_cuotas_gasto
from .models import (
    Pedido,
    PedidoEmpaque,
    PedidoEmpaqueComplemento,
    DetallePedido,
    DetalleKitProducto,
    EstadoImpresionPedido,
    Pago,
    Gasto,
    CuotaGasto,
    CajaCorte,
)


# ==========================================================
# COSTOS / RENTABILIDAD
# ==========================================================

def _decimal_seguro(valor):
    if callable(valor):
        valor = valor()

    if valor is None:
        return None

    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _costo_actual_producto(producto):
    """
    Usa el cálculo ya existente en Producto y evita duplicar
    la fórmula de costos dentro de Pedidos.
    """
    costo_total = _decimal_seguro(
        getattr(producto, "costo_productivo_total", None)
    )
    if costo_total is not None:
        return max(costo_total, Decimal("0"))

    costo = _decimal_seguro(
        getattr(producto, "costo", None)
    )
    seguro = _decimal_seguro(
        getattr(producto, "seguro", None)
    )

    if costo is not None:
        if seguro is not None:
            return max(costo + seguro, Decimal("0"))
        return max(costo, Decimal("0"))

    for nombre in ("costo_total", "costo_estimado"):
        valor = _decimal_seguro(
            getattr(producto, nombre, None)
        )
        if valor is not None:
            return max(valor, Decimal("0"))

    subtotal = _decimal_seguro(
        getattr(producto, "subtotal", None)
    )
    ganancia = _decimal_seguro(
        getattr(producto, "ganancia", None)
    )

    if subtotal is not None and ganancia is not None:
        return max(
            subtotal - ganancia,
            Decimal("0"),
        )

    return Decimal("0")


def _costo_actual_detalle(detalle):
    """
    Respaldo para pedidos viejos sin costo histórico.
    Se muestra expresamente como ESTIMADO ACTUAL.
    """
    if detalle.tipo_item in ["PRODUCTO", "PERSONALIZADO"]:
        if not detalle.producto:
            return Decimal("0")

        return (
            _costo_actual_producto(detalle.producto)
            * detalle.cantidad
        )

    if detalle.tipo_item == "KIT":
        total = Decimal("0")

        for componente in detalle.productos_kit.all():
            total += (
                _costo_actual_producto(componente.producto)
                * componente.cantidad
            )

        return total

    return Decimal("0")


def _guardar_costo_kit(detalle):
    """
    Los componentes guardan cantidades reales totales.
    Se calcula el costo total y luego el costo por kit vendido.
    """
    if detalle.tipo_item != "KIT" or detalle.cantidad <= 0:
        return

    costo_total = Decimal("0")

    for componente in detalle.productos_kit.all():
        costo_total += (
            _costo_actual_producto(componente.producto)
            * componente.cantidad
        )

    detalle.costo_unitario = (
        costo_total / Decimal(detalle.cantidad)
    ).quantize(Decimal("0.01"))

    detalle.save(
        update_fields=["costo_unitario"]
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
    # IMPORTANTE:
    # El stock NO se reserva para los primeros pedidos de la lista.
    # Todos los pedidos pendientes pueden usar el stock disponible
    # en ese momento. El stock se descuenta recién cuando el usuario
    # marca un producto como LISTO.
    #
    # Los PERSONALIZADOS no consumen stock general.
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
            #
            # No se reserva stock según la posición del pedido.
            # Cada fila consulta el stock físico ACTUAL.
            #
            # Ejemplo:
            # - stock = 6
            # - 13 pedidos necesitan 1 unidad
            #
            # Los 13 pueden marcarse mientras haya stock.
            # Cada vez que uno se marca LISTO se descuenta 1.
            # Cuando el stock llega a 0, recién entonces los
            # restantes quedan bloqueados por stock insuficiente.
            # ==================================================

            disponible = producto.stock

            stock_usado = min(
                cantidad,
                disponible,
            )

            a_imprimir = max(
                cantidad - disponible,
                0,
            )

            item["stock_usado"] = stock_usado
            item["a_imprimir"] = a_imprimir

            item["puede_marcar_listo"] = (
                disponible >= cantidad
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
    kit = get_object_or_404(
        Kit.objects.prefetch_related(
            "componentes__producto"
        ),
        id=kit_id,
        activo=True,
    )

    if kit.modalidad == "FIJO":
        componentes = list(
            kit.componentes.all()
        )

        cantidad_productos = sum(
            componente.cantidad
            for componente in componentes
        )

        return JsonResponse({
            "kit": {
                "id": kit.id,
                "nombre": kit.nombre,
                "modalidad": kit.modalidad,
                "cantidad_productos":
                    cantidad_productos,
                "tipo": "",
            },
            "productos": [],
            "componentes": [
                {
                    "id":
                        componente.producto.id,
                    "codigo":
                        componente.producto.codigo,
                    "nombre":
                        componente.producto.nombre,
                    "cantidad":
                        componente.cantidad,
                }
                for componente in componentes
            ],
        })

    productos = (
        Producto.objects
        .filter(
            tipo=kit.tipo_producto,
            activo=True,
        )
        .order_by("nombre")
    )

    return JsonResponse({
        "kit": {
            "id": kit.id,
            "nombre": kit.nombre,
            "modalidad": kit.modalidad,
            "cantidad_productos":
                kit.cantidad_productos,
            "tipo": (
                kit.tipo_producto.nombre
                if kit.tipo_producto
                else ""
            ),
        },
        "productos": [
            {
                "id": producto.id,
                "codigo": producto.codigo,
                "nombre": producto.nombre,
            }
            for producto in productos
        ],
        "componentes": [],
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

            existente = buscar_cliente_por_telefono(
                telefono_cliente
            )
            if existente:
                estado = "" if existente.activo else " (inactivo)"
                messages.error(
                    request,
                    (
                        f"Ese teléfono ya pertenece a {existente.nombre} "
                        f"({existente.codigo}){estado}. Seleccioná el cliente existente."
                    ),
                )
                return redirect(
                    f"{reverse('pedidos:nuevo')}?cliente={existente.id}"
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

                precio_unitario_texto = request.POST.get(
                    f"precio_unitario_{indice}",
                    "",
                ).strip()

                precio_total_texto = request.POST.get(
                    f"precio_total_producto_{indice}",
                    "",
                ).strip()

                try:
                    precio_unitario = Decimal(
                        precio_unitario_texto
                    )
                except (
                    InvalidOperation,
                    TypeError,
                    ValueError,
                ):
                    precio_unitario = Decimal("0")

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

                # El TOTAL acordado es el dato autoritativo.
                # Si viene desde una recomendación, conserva exactamente
                # el total redondeado por la calculadora.
                if precio_total > 0:
                    precio_unitario = (
                        precio_total
                        / Decimal(cantidad)
                    ).quantize(
                        Decimal("0.01")
                    )
                elif precio_unitario > 0:
                    precio_total = (
                        precio_unitario
                        * Decimal(cantidad)
                    ).quantize(
                        Decimal("0.01")
                    )

                if (
                    precio_unitario <= 0
                    or precio_total <= 0
                ):
                    messages.error(
                        request,
                        (
                            f"El precio acordado de "
                            f"{producto.nombre} debe ser mayor a cero."
                        )
                    )

                    transaction.set_rollback(True)

                    return redirect(
                        "pedidos:nuevo"
                    )

                DetallePedido.objects.create(
                    pedido=pedido,
                    tipo_item="PRODUCTO",
                    producto=producto,
                    cantidad=cantidad,
                    precio_unitario=precio_unitario,
                    costo_unitario=_costo_actual_producto(producto),
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
                    Kit.objects.prefetch_related(
                        "componentes__producto"
                    ),
                    id=kit_id,
                    activo=True,
                )

                if (
                    kit.precio is None
                    or kit.precio <= 0
                ):
                    messages.error(
                        request,
                        (
                            f"El kit {kit.nombre} no tiene "
                            "un precio de venta válido."
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
                    precio_unitario=kit.precio,
                    costo_unitario=None,
                    estado="PENDIENTE",
                )

                if kit.modalidad == "FIJO":

                    componentes_fijos = list(
                        kit.componentes.all()
                    )

                    if not componentes_fijos:
                        messages.error(
                            request,
                            (
                                f"El kit {kit.nombre} no tiene "
                                "una composición fija configurada."
                            )
                        )
                        transaction.set_rollback(True)
                        return redirect(
                            "pedidos:nuevo"
                        )

                    for componente in componentes_fijos:
                        DetalleKitProducto.objects.create(
                            detalle=detalle,
                            producto=componente.producto,
                            cantidad=(
                                componente.cantidad
                                * cantidad
                            ),
                        )

                else:
                    productos_kit_ids = (
                        request.POST.getlist(
                            f"productos_kit_{indice}"
                        )
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

                    if not kit.tipo_producto:
                        messages.error(
                            request,
                            (
                                f"El kit {kit.nombre} no tiene "
                                "una categoría configurada."
                            )
                        )
                        transaction.set_rollback(True)
                        return redirect(
                            "pedidos:nuevo"
                        )

                    productos_seleccionados = {}

                    for producto_id in productos_kit_ids:
                        producto = get_object_or_404(
                            Producto,
                            id=producto_id,
                            activo=True,
                            tipo=kit.tipo_producto,
                        )

                        if (
                            producto.id
                            not in productos_seleccionados
                        ):
                            productos_seleccionados[
                                producto.id
                            ] = {
                                "producto": producto,
                                "cantidad": 0,
                            }

                        productos_seleccionados[
                            producto.id
                        ]["cantidad"] += cantidad

                    for item in (
                        productos_seleccionados
                        .values()
                    ):
                        DetalleKitProducto.objects.create(
                            detalle=detalle,
                            producto=item["producto"],
                            cantidad=item["cantidad"],
                        )

                _guardar_costo_kit(detalle)


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
                    costo_unitario=_costo_actual_producto(producto),
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
    Devuelve el stock físico disponible en este momento.

    Ya no se reserva stock según fecha de entrega ni posición
    del pedido en la lista. El stock se consume únicamente
    cuando un producto se marca como LISTO.
    """
    return producto.stock



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

    hay_reservas = (
        estados_normales
        .filter(
            reservado_stock=True,
            listo=False,
        )
        .exists()
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

    elif cantidad_listos > 0 or hay_reservas:
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

    es_ajax = (
        request.headers.get("X-Requested-With")
        == "XMLHttpRequest"
    )

    def responder_error(mensaje, status=409):
        if es_ajax:
            return JsonResponse(
                {
                    "ok": False,
                    "mensaje": mensaje,
                },
                status=status,
            )

        messages.error(
            request,
            mensaje,
        )
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
            return responder_error(
                (
                    "No se puede modificar un pedido "
                    "entregado o cancelado."
                )
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

        if es_ajax:
            pedido.refresh_from_db(
                fields=["estado"]
            )
            return JsonResponse(
                {
                    "ok": True,
                    "listo": marcar_listo,
                    "personalizado": True,
                    "pedido_estado": pedido.estado,
                    "mensaje": (
                        "Personalizado preparado."
                        if marcar_listo
                        else "Personalizado vuelto a pendiente."
                    ),
                }
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
            return responder_error(
                (
                    "No se encontró demanda pendiente "
                    f"para {producto.nombre}."
                )
            )

        if (
            not estado_impresion.reservado_stock
            and stock_disponible < cantidad_necesaria
        ):
            return responder_error(
                (
                    f"No hay stock suficiente de {producto.nombre}. "
                    f"Este pedido necesita {cantidad_necesaria} y "
                    f"solo hay {stock_disponible} disponible."
                )
            )

        if estado_impresion.reservado_stock:
            cantidad_reservada = int(
                estado_impresion.cantidad_stock_reservada or 0
            )

            if cantidad_reservada != cantidad_necesaria:
                return responder_error(
                    (
                        f"La reserva de {producto.nombre} no coincide con "
                        "la cantidad actual del pedido. Liberá la preparación "
                        "y volvé a iniciarla."
                    )
                )

            estado_impresion.cantidad_stock_descontada = cantidad_reservada
            estado_impresion.stock_descontado = True
            estado_impresion.reservado_stock = False
            estado_impresion.cantidad_stock_reservada = 0
            estado_impresion.listo = True

            estado_impresion.save(
                update_fields=[
                    "cantidad_stock_descontada",
                    "stock_descontado",
                    "reservado_stock",
                    "cantidad_stock_reservada",
                    "listo",
                ]
            )
        else:
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

    if es_ajax:
        pedido.refresh_from_db(
            fields=["estado"]
        )
        producto.refresh_from_db(
            fields=["stock"]
        )
        estado_impresion.refresh_from_db(
            fields=[
                "listo",
                "cantidad_stock_descontada",
                "reservado_stock",
                "cantidad_stock_reservada",
            ]
        )

        cantidad_descontada = int(
            estado_impresion.cantidad_stock_descontada
            or 0
        )

        if estado_impresion.listo:
            estado_texto = (
                f"Preparado · {cantidad_descontada} descontado"
                if cantidad_descontada
                else "Preparado"
            )
        elif estado_impresion.reservado_stock:
            reservado = int(
                estado_impresion.cantidad_stock_reservada
                or 0
            )
            estado_texto = (
                f"Reservado · {reservado} "
                f"unidad{'es' if reservado != 1 else ''}"
            )
        else:
            estado_texto = (
                f"Stock {int(producto.stock or 0)} · disponible"
            )

        return JsonResponse(
            {
                "ok": True,
                "listo": bool(estado_impresion.listo),
                "personalizado": False,
                "pedido_estado": pedido.estado,
                "stock_actual": int(producto.stock or 0),
                "estado_texto": estado_texto,
                "reservado_stock": bool(
                    estado_impresion.reservado_stock
                ),
                "stock_reservado": int(
                    estado_impresion.cantidad_stock_reservada
                    or 0
                ),
                "mensaje": (
                    f"{producto.nombre} preparado."
                    if estado_impresion.listo
                    else f"{producto.nombre} volvió a pendiente."
                ),
            }
        )

    return redirect(
        "pedidos:impresiones"
    )



# ==========================================================
# API - PRECIO MAYORISTA POR PRODUCTO
# ==========================================================

def precio_producto(request):
    """
    Devuelve las recomendaciones de precio por cantidad que usa
    Nuevo Pedido para PRODUCTO y PERSONALIZADO.

    Esta vista existía en la integración mayorista. Se mantiene
    separada de la pantalla de Producción porque pedidos/urls.py
    la referencia como pedidos:precio_producto.
    """
    if request.method != "GET":
        return JsonResponse(
            {
                "ok": False,
                "mensaje": "Método no permitido.",
            },
            status=405,
        )

    producto_id = request.GET.get(
        "producto_id",
        "",
    ).strip()

    cantidad_texto = request.GET.get(
        "cantidad",
        "1",
    ).strip()

    try:
        cantidad = int(cantidad_texto)
    except (TypeError, ValueError):
        cantidad = 0

    if not producto_id or cantidad <= 0:
        return JsonResponse(
            {
                "ok": False,
                "mensaje": "Producto o cantidad no válidos.",
            },
            status=400,
        )

    producto = get_object_or_404(
        Producto,
        id=producto_id,
        activo=True,
    )

    costo_productivo = (
        _costo_actual_producto(producto)
    )

    margen_tope = Decimal(
        str(
            producto.margen_ganancia
            or 0
        )
    )

    margenes = margenes_escenario(
        cantidad,
        margen_tope,
    )

    escenarios = {}

    for estrategia in (
        "conservador",
        "recomendado",
        "agresivo",
    ):
        margen = margenes[estrategia]

        fila = fila_precio(
            costo_productivo,
            cantidad,
            margen,
        )

        total_recomendado = Decimal(
            str(
                fila["total_recomendado"]
            )
        )

        precio_unitario = Decimal(
            str(
                fila["precio_unitario"]
            )
        )

        precio_unitario_pedido = (
            total_recomendado
            / Decimal(cantidad)
        ).quantize(
            Decimal("0.01")
        )

        escenarios[estrategia] = {
            "estrategia": estrategia,
            "margen_objetivo": float(
                Decimal(
                    str(
                        fila["margen_objetivo"]
                    )
                )
            ),
            "precio_unitario": float(
                precio_unitario
            ),
            "total_recomendado": float(
                total_recomendado
            ),
            "precio_unitario_pedido": float(
                precio_unitario_pedido
            ),
            "total_pedido": float(
                precio_unitario_pedido
                * Decimal(cantidad)
            ),
        }

    return JsonResponse(
        {
            "ok": True,
            "producto": {
                "id": producto.id,
                "codigo": producto.codigo,
                "nombre": producto.nombre,
            },
            "cantidad": cantidad,
            "precio_lista": float(
                Decimal(
                    str(
                        producto.subtotal
                    )
                )
            ),
            "costo_productivo": float(
                costo_productivo
            ),
            "margen_tope": float(
                margen_tope
            ),
            "escenarios": escenarios,
        }
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
            "en_produccion": 0,
            "falta_iniciar": 0,
            "impresoras": [],
        }
    )

    # ==========================================
    # 1. AGRUPAR DEMANDA PENDIENTE
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

            if (
                detalle.tipo_item == "PERSONALIZADO"
                and detalle.producto
                and detalle.producto.requiere_impresion
            ):
                if detalle.estado == "LISTO":
                    continue

                producto = detalle.producto
                item = productos_agrupados[producto.id]
                item["producto"] = producto

                item["cantidad_personalizada"] += (
                    detalle.cantidad
                )

                item["cantidad_pedida"] += (
                    detalle.cantidad
                )

                continue

            if (
                detalle.tipo_item == "PRODUCTO"
                and detalle.producto
                and detalle.producto.requiere_impresion
            ):
                producto = detalle.producto

                if producto.id in productos_normales_listos:
                    continue

                item = productos_agrupados[producto.id]
                item["producto"] = producto

                item["cantidad_normal"] += (
                    detalle.cantidad
                )

                item["cantidad_pedida"] += (
                    detalle.cantidad
                )

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

                    if producto.id in productos_normales_listos:
                        continue

                    item = productos_agrupados[producto.id]
                    item["producto"] = producto

                    item["cantidad_normal"] += (
                        componente.cantidad
                    )

                    item["cantidad_pedida"] += (
                        componente.cantidad
                    )

    # ==========================================
    # 2. PRODUCCIONES QUE YA ESTÁN IMPRIMIENDO
    # ==========================================
    #
    # No reducimos "A IMPRIMIR": ese número sigue
    # representando la necesidad total.
    #
    # Mostramos aparte:
    # - EN PRODUCCIÓN
    # - FALTA INICIAR
    #
    # Sólo cuenta estado IMPRIMIENDO.
    # ==========================================

    producciones_en_curso = (
        Produccion.objects
        .filter(
            estado="IMPRIMIENDO",
        )
        .select_related(
            "producto",
            "impresora",
        )
        .order_by(
            "producto_id",
            "id",
        )
    )

    en_curso_por_producto = defaultdict(
        lambda: {
            "cantidad": 0,
            "impresoras": [],
        }
    )

    for produccion in producciones_en_curso:
        item_curso = en_curso_por_producto[
            produccion.producto_id
        ]

        item_curso["cantidad"] += (
            produccion.cantidad
        )

        if produccion.impresora:
            texto_impresora = (
                f"{produccion.impresora.nombre} "
                f"· {produccion.cantidad}"
            )

            item_curso["impresoras"].append(
                texto_impresora
            )

    # ==========================================
    # 3. CALCULAR NECESIDAD / PRODUCCIÓN / FALTA
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

        produciendo = en_curso_por_producto.get(
            producto.id,
            {
                "cantidad": 0,
                "impresoras": [],
            },
        )

        en_produccion = (
            produciendo["cantidad"]
        )

        falta_iniciar = max(
            a_imprimir - en_produccion,
            0,
        )

        item["stock"] = stock
        item["a_imprimir"] = a_imprimir
        item["en_produccion"] = en_produccion
        item["falta_iniciar"] = falta_iniciar
        item["impresoras"] = (
            produciendo["impresoras"]
        )

        # La prioridad ahora se calcula con lo que
        # realmente falta poner a imprimir.
        if falta_iniciar >= 6:
            item["prioridad"] = "ALTA"
            item["prioridad_clase"] = (
                "prioridad-alta"
            )

        elif falta_iniciar >= 3:
            item["prioridad"] = "MEDIA"
            item["prioridad_clase"] = (
                "prioridad-media"
            )

        elif falta_iniciar >= 1:
            item["prioridad"] = "BAJA"
            item["prioridad_clase"] = (
                "prioridad-baja"
            )

        else:
            if en_produccion > 0 and a_imprimir > 0:
                item["prioridad"] = "EN CURSO"
                item["prioridad_clase"] = (
                    "prioridad-curso"
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
    # 4. ORDENAR
    # ==========================================

    lista_productos.sort(
        key=lambda item: (
            -item["falta_iniciar"],
            -item["en_produccion"],
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
        if origen in {"pagos", "finanzas"}:
            url = reverse("pedidos:finanzas")
            periodo = request.POST.get("periodo", "").strip()
            if periodo:
                url += f"?periodo={periodo}&vista=cobros"
            else:
                url += "?vista=cobros"
            return redirect(url)

        if origen == "cliente" and cliente_id:
            return redirect(
                "clientes:detalle",
                cliente_id=cliente_id,
            )

        if origen == "detalle":
            return redirect(
                "pedidos:detalle",
                pedido_id=pedido_id,
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

    nuevo_saldo = max(saldo - monto, Decimal("0"))

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

    devolver = 0
    if estado.stock_descontado and estado.cantidad_stock_descontada:
        devolver += int(estado.cantidad_stock_descontada or 0)
    if estado.reservado_stock and estado.cantidad_stock_reservada:
        devolver += int(estado.cantidad_stock_reservada or 0)

    if devolver:
        producto = (
            Producto.objects
            .select_for_update()
            .get(id=producto_id)
        )
        producto.stock += devolver
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
                "precio_unitario":
                    (
                        str(detalle.precio_unitario)
                        if detalle.precio_unitario is not None
                        else ""
                    ),
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
                "volver_cliente": (
                    request.GET.get("volver") == "cliente"
                ),
                "volver_cliente_id": (
                    request.GET.get("cliente_id", "").strip()
                ),
            },
        )

    # ------------------------------------------------------
    # DATOS GENERALES
    # ------------------------------------------------------
    cliente_id = request.POST.get("cliente")
    fecha_entrega = request.POST.get("fecha_entrega")
    observaciones = request.POST.get("observaciones", "").strip()

    volver_cliente = (
        request.POST.get("volver") == "cliente"
    )

    volver_cliente_id = (
        request.POST.get(
            "volver_cliente_id",
            "",
        ).strip()
    )

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

            precio_unitario_texto = request.POST.get(
                f"precio_unitario_{indice}",
                "",
            ).strip()

            precio_total_texto = request.POST.get(
                f"precio_total_producto_{indice}",
                "",
            ).strip()

            try:
                precio_unitario = Decimal(
                    precio_unitario_texto
                )
            except (
                InvalidOperation,
                TypeError,
                ValueError,
            ):
                precio_unitario = Decimal("0")

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

            # El TOTAL acordado es el dato autoritativo.
            # Esto evita que al editar el pedido se vuelva a calcular
            # accidentalmente como precio de lista x cantidad.
            if precio_total > 0:
                precio_unitario = (
                    precio_total
                    / Decimal(cantidad)
                ).quantize(
                    Decimal("0.01")
                )
            elif precio_unitario > 0:
                precio_total = (
                    precio_unitario
                    * Decimal(cantidad)
                ).quantize(
                    Decimal("0.01")
                )

            if precio_unitario <= 0 or precio_total <= 0:
                messages.error(
                    request,
                    (
                        f"El precio acordado de "
                        f"{producto.nombre} debe ser mayor a cero."
                    )
                )
                transaction.set_rollback(True)
                return redirect(
                    "pedidos:editar",
                    pedido_id=pedido.id,
                )

            nuevos_items.append({
                "detalle_id": detalle_id,
                "tipo_item": "PRODUCTO",
                "cantidad": cantidad,
                "producto": producto,
                "precio_unitario": precio_unitario,
                "precio_total": precio_total,
            })

        elif tipo_item == "KIT":
            kit = get_object_or_404(
                Kit.objects.prefetch_related(
                    "componentes__producto"
                ),
                id=request.POST.get(
                    f"kit_{indice}"
                ),
                activo=True,
            )

            componentes = defaultdict(int)

            if kit.modalidad == "FIJO":

                componentes_fijos = list(
                    kit.componentes.all()
                )

                if not componentes_fijos:
                    messages.error(
                        request,
                        (
                            f"El kit {kit.nombre} no tiene "
                            "una composición fija configurada."
                        )
                    )
                    transaction.set_rollback(True)
                    return redirect(
                        "pedidos:editar",
                        pedido_id=pedido.id,
                    )

                for componente in componentes_fijos:
                    componentes[
                        componente.producto_id
                    ] += (
                        componente.cantidad
                        * cantidad
                    )

            else:
                productos_kit_ids = (
                    request.POST.getlist(
                        f"productos_kit_{indice}"
                    )
                )

                if (
                    len(productos_kit_ids)
                    != kit.cantidad_productos
                ):
                    messages.error(
                        request,
                        f"El kit {kit.nombre} necesita "
                        f"{kit.cantidad_productos} productos."
                    )
                    transaction.set_rollback(True)
                    return redirect(
                        "pedidos:editar",
                        pedido_id=pedido.id,
                    )

                if not kit.tipo_producto:
                    messages.error(
                        request,
                        (
                            f"El kit {kit.nombre} no tiene "
                            "una categoría configurada."
                        )
                    )
                    transaction.set_rollback(True)
                    return redirect(
                        "pedidos:editar",
                        pedido_id=pedido.id,
                    )

                for producto_id in (
                    productos_kit_ids
                ):
                    producto = get_object_or_404(
                        Producto,
                        id=producto_id,
                        activo=True,
                        tipo=kit.tipo_producto,
                    )
                    componentes[
                        producto.id
                    ] += cantidad

            nuevos_items.append({
                "detalle_id": detalle_id,
                "tipo_item": "KIT",
                "cantidad": cantidad,
                "kit": kit,
                "componentes": dict(
                    componentes
                ),
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
            producto = item["producto"]
            precio_unitario = item["precio_unitario"]

            DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="PRODUCTO",
                producto=producto,
                cantidad=item["cantidad"],
                precio_unitario=precio_unitario,
                costo_unitario=_costo_actual_producto(producto),
                estado="PENDIENTE",
            )

        elif item["tipo_item"] == "KIT":
            kit = item["kit"]

            if kit.precio is None or kit.precio <= 0:
                messages.error(
                    request,
                    f"El kit {kit.nombre} no tiene un precio válido."
                )
                transaction.set_rollback(True)
                return redirect(
                    "pedidos:editar",
                    pedido_id=pedido.id,
                )

            detalle = DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="KIT",
                kit=kit,
                cantidad=item["cantidad"],
                precio_unitario=kit.precio,
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
                costo_unitario=_costo_actual_producto(item["producto"]),
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

    if volver_cliente and volver_cliente_id:
        return redirect(
            "clientes:detalle",
            cliente_id=volver_cliente_id,
        )

    return redirect("pedidos:impresiones")



# ==========================================================
# GASTOS / CUOTAS
# ==========================================================

@transaction.atomic
def registrar_gasto(request):
    if request.method != "POST":
        return redirect(
            "pedidos:finanzas"
        )

    fecha_texto = request.POST.get(
        "fecha_compra",
        "",
    ).strip()

    tipo = request.POST.get(
        "tipo",
        "OPERATIVO",
    ).strip().upper()

    categoria = request.POST.get(
        "categoria",
        "OTRO",
    ).strip().upper()

    descripcion = request.POST.get(
        "descripcion",
        "",
    ).strip()

    monto_texto = (
        request.POST.get(
            "monto_total",
            "",
        )
        .strip()
        .replace(",", ".")
    )

    medio_pago = request.POST.get(
        "medio_pago",
        "TRANSFERENCIA",
    ).strip().upper()

    cuotas_texto = request.POST.get(
        "cantidad_cuotas",
        "1",
    ).strip()

    primera_cuota_texto = request.POST.get(
        "fecha_primera_cuota",
        "",
    ).strip()

    observaciones = request.POST.get(
        "observaciones",
        "",
    ).strip()

    try:
        fecha_compra = date.fromisoformat(
            fecha_texto
        )
    except (TypeError, ValueError):
        messages.error(
            request,
            "La fecha de compra no es válida."
        )
        return redirect(
            "pedidos:finanzas"
        )

    try:
        monto_total = Decimal(
            monto_texto
        ).quantize(
            Decimal("0.01")
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        monto_total = Decimal("0")

    try:
        cantidad_cuotas = int(
            cuotas_texto or 1
        )
    except (TypeError, ValueError):
        cantidad_cuotas = 1

    if not descripcion:
        messages.error(
            request,
            "Ingresá una descripción para el gasto."
        )
        return redirect(
            "pedidos:finanzas"
        )

    if monto_total <= 0:
        messages.error(
            request,
            "El monto debe ser mayor a cero."
        )
        return redirect(
            "pedidos:finanzas"
        )

    tipos_validos = {
        clave
        for clave, _ in Gasto.TIPOS
    }

    categorias_validas = {
        clave
        for clave, _ in Gasto.CATEGORIAS
    }

    medios_validos = {
        clave
        for clave, _ in Gasto.MEDIOS_PAGO
    }

    if tipo not in tipos_validos:
        tipo = "OPERATIVO"

    if categoria not in categorias_validas:
        categoria = "OTRO"

    if medio_pago not in medios_validos:
        medio_pago = "OTRO"

    fecha_primera_cuota = None

    if medio_pago == "TARJETA_CREDITO":
        cantidad_cuotas = max(
            min(cantidad_cuotas, 36),
            1,
        )

        if not primera_cuota_texto:
            messages.error(
                request,
                (
                    "Para una compra con tarjeta de crédito "
                    "indicá el vencimiento de la primera cuota."
                )
            )
            return redirect(
                "pedidos:finanzas"
            )

        try:
            fecha_primera_cuota = (
                date.fromisoformat(
                    primera_cuota_texto
                )
            )
        except (TypeError, ValueError):
            messages.error(
                request,
                "El primer vencimiento no es válido."
            )
            return redirect(
                "pedidos:finanzas"
            )

    else:
        cantidad_cuotas = 1

    gasto = Gasto.objects.create(
        fecha_compra=fecha_compra,
        tipo=tipo,
        categoria=categoria,
        descripcion=descripcion,
        monto_total=monto_total,
        medio_pago=medio_pago,
        cantidad_cuotas=cantidad_cuotas,
        fecha_primera_cuota=fecha_primera_cuota,
        observaciones=observaciones,
    )

    crear_cuotas_gasto(
        gasto
    )

    messages.success(
        request,
        (
            f"Gasto registrado: {gasto.descripcion} "
            f"por ${gasto.monto_total:,.2f}."
        )
    )

    periodo = fecha_compra.strftime(
        "%Y-%m"
    )

    return redirect(
        f"{redirect('pedidos:finanzas').url}?periodo={periodo}&vista=gastos"
    )


@transaction.atomic
def cambiar_estado_cuota(
    request,
    cuota_id,
):
    if request.method != "POST":
        return redirect(
            "pedidos:finanzas"
        )

    cuota = get_object_or_404(
        CuotaGasto.objects
        .select_for_update()
        .select_related("gasto"),
        id=cuota_id,
    )

    pagada = (
        request.POST.get(
            "pagada"
        )
        == "1"
    )

    cuota.pagada = pagada
    cuota.fecha_pago = (
        timezone.localdate()
        if pagada
        else None
    )
    cuota.pagada_en = (
        timezone.now()
        if pagada
        else None
    )

    cuota.save(
        update_fields=[
            "pagada",
            "fecha_pago",
            "pagada_en",
        ]
    )

    periodo = request.POST.get(
        "periodo",
        timezone.localdate().strftime(
            "%Y-%m"
        ),
    )

    return redirect(
        f"{redirect('pedidos:finanzas').url}?periodo={periodo}&vista=cuotas"
    )


@transaction.atomic
def eliminar_gasto(
    request,
    gasto_id,
):
    if request.method != "POST":
        return redirect(
            "pedidos:finanzas"
        )

    gasto = get_object_or_404(
        Gasto,
        id=gasto_id,
    )

    descripcion = gasto.descripcion
    gasto.delete()

    messages.success(
        request,
        f"Gasto eliminado: {descripcion}."
    )

    periodo = request.POST.get(
        "periodo",
        timezone.localdate().strftime(
            "%Y-%m"
        ),
    )

    return redirect(
        f"{redirect('pedidos:finanzas').url}?periodo={periodo}&vista=gastos"
    )



@transaction.atomic
def actualizar_saldo_caja(request):
    """
    Guarda un nuevo punto cero para la caja de Mercado Pago.

    El usuario carga el saldo REAL que ve en Mercado Pago.
    Desde este momento se suman cobros y se restan egresos
    registrados posteriormente.
    """
    if request.method != "POST":
        return redirect(
            "pedidos:finanzas"
        )

    saldo_texto = (
        request.POST.get(
            "saldo_real",
            "",
        )
        .strip()
        .replace(",", ".")
    )

    observaciones = request.POST.get(
        "observaciones",
        "",
    ).strip()

    try:
        saldo_real = Decimal(
            saldo_texto
        ).quantize(
            Decimal("0.01")
        )
    except (
        InvalidOperation,
        TypeError,
        ValueError,
    ):
        messages.error(
            request,
            "El saldo de Mercado Pago no es válido."
        )
        return redirect(
            "pedidos:finanzas"
        )

    if saldo_real < 0:
        messages.error(
            request,
            "El saldo no puede ser negativo."
        )
        return redirect(
            "pedidos:finanzas"
        )

    CajaCorte.objects.create(
        saldo_real=saldo_real,
        observaciones=observaciones,
    )

    messages.success(
        request,
        (
            "Saldo real de Mercado Pago actualizado. "
            "Este valor queda como nuevo punto de conciliación."
        )
    )

    periodo = request.POST.get(
        "periodo",
        timezone.localdate().strftime(
            "%Y-%m"
        ),
    )

    return redirect(
        f"{redirect('pedidos:finanzas').url}?periodo={periodo}&vista=caja"
    )


def _resumen_caja_mercadopago(hoy):
    """
    Calcula la caja operativa desde el último corte manual.

    saldo_estimado =
        saldo_real_del_corte
        + cobros registrados después
        - egresos registrados después

    Como el usuario indicó que hoy maneja la operatoria por
    Mercado Pago, esta primera versión considera todos los
    cobros y egresos registrados como movimientos de esa caja.
    """
    corte = (
        CajaCorte.objects
        .order_by(
            "-fecha",
            "-id",
        )
        .first()
    )

    if not corte:
        return {
            "corte": None,
            "saldo_base": Decimal("0"),
            "ingresos_desde_corte": Decimal("0"),
            "egresos_desde_corte": Decimal("0"),
            "saldo_estimado": Decimal("0"),
            "requiere_corte": True,
        }

    ingresos = (
        Pago.objects
        .filter(
            fecha__gt=corte.fecha,
        )
        .aggregate(
            total=Sum("monto")
        )
        .get("total")
        or Decimal("0")
    )

    egresos = (
        CuotaGasto.objects
        .filter(
            pagada=True,
            pagada_en__gt=corte.fecha,
        )
        .aggregate(
            total=Sum("monto")
        )
        .get("total")
        or Decimal("0")
    )

    saldo_estimado = (
        corte.saldo_real
        + ingresos
        - egresos
    )

    return {
        "corte": corte,
        "saldo_base": corte.saldo_real,
        "ingresos_desde_corte": ingresos,
        "egresos_desde_corte": egresos,
        "saldo_estimado": saldo_estimado,
        "requiere_corte": False,
    }


def _rentabilidad_acumulada():
    """Rentabilidad histórica sin cargar todos los pedidos en memoria."""
    money = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )

    subtotal_normal = models.ExpressionWrapper(
        models.F("precio_unitario")
        * models.F("cantidad"),
        output_field=money,
    )
    subtotal_venta = models.Case(
        models.When(
            tipo_item="PERSONALIZADO",
            precio_total_personalizado__isnull=False,
            then=models.F("precio_total_personalizado"),
        ),
        default=subtotal_normal,
        output_field=money,
    )
    costo_snapshot = models.ExpressionWrapper(
        models.F("costo_unitario")
        * models.F("cantidad"),
        output_field=money,
    )

    detalles = (
        DetallePedido.objects
        .exclude(estado="CANCELADO")
        .exclude(pedido__estado="CANCELADO")
    )

    ventas = (
        detalles
        .aggregate(total=Sum(subtotal_venta))
        .get("total")
        or Decimal("0")
    )

    costos_snapshot = (
        detalles
        .filter(costo_unitario__isnull=False)
        .aggregate(total=Sum(costo_snapshot))
        .get("total")
        or Decimal("0")
    )

    # Sólo los registros antiguos sin snapshot necesitan la
    # estimación actual. Esa excepción desaparece naturalmente
    # a medida que crece el historial nuevo.
    sin_snapshot = (
        detalles
        .filter(costo_unitario__isnull=True)
        .select_related("producto", "kit")
        .prefetch_related(
            "productos_kit__producto",
        )
    )

    costos_estimados = sum(
        (
            _costo_actual_detalle(detalle)
            for detalle in sin_snapshot
        ),
        Decimal("0"),
    )

    costo_empaques = (
        PedidoEmpaque.objects
        .exclude(pedido__estado="CANCELADO")
        .aggregate(total=Sum("costo_total_snapshot"))
        .get("total")
        or Decimal("0")
    )
    costo_empaques_complementarios = (
        PedidoEmpaqueComplemento.objects
        .exclude(pedido_empaque__pedido__estado="CANCELADO")
        .aggregate(total=Sum("costo_total_snapshot"))
        .get("total")
        or Decimal("0")
    )

    costos = (
        costos_snapshot
        + costos_estimados
        + costo_empaques
        + costo_empaques_complementarios
    )

    return {
        "ventas": ventas,
        "costos": costos,
        "ganancia_bruta": ventas - costos,
    }


def _pedidos_con_saldo_finanzas():
    """Pedidos con saldo calculados en SQL para evitar recorrer todo el historial."""
    money = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )

    subtotal_normal = models.ExpressionWrapper(
        models.F("precio_unitario")
        * models.F("cantidad"),
        output_field=money,
    )
    subtotal_detalle = models.Case(
        models.When(
            tipo_item="PERSONALIZADO",
            precio_total_personalizado__isnull=False,
            then=models.F("precio_total_personalizado"),
        ),
        default=subtotal_normal,
        output_field=money,
    )

    total_detalles = (
        DetallePedido.objects
        .filter(pedido_id=models.OuterRef("pk"))
        .exclude(estado="CANCELADO")
        .values("pedido_id")
        .annotate(total=Sum(subtotal_detalle))
        .values("total")[:1]
    )

    total_pagos = (
        Pago.objects
        .filter(pedido_id=models.OuterRef("pk"))
        .values("pedido_id")
        .annotate(total=Sum("monto"))
        .values("total")[:1]
    )

    cero = models.Value(
        Decimal("0"),
        output_field=money,
    )

    return (
        Pedido.objects
        .exclude(estado="CANCELADO")
        .select_related("cliente")
        .annotate(
            total_fin=Coalesce(
                models.Subquery(
                    total_detalles,
                    output_field=money,
                ),
                cero,
                output_field=money,
            ),
            pagado_fin=Coalesce(
                models.Subquery(
                    total_pagos,
                    output_field=money,
                ),
                cero,
                output_field=money,
            ),
        )
        .annotate(
            saldo_fin=models.ExpressionWrapper(
                models.F("total_fin")
                - models.F("pagado_fin"),
                output_field=money,
            )
        )
        .filter(saldo_fin__gt=0)
    )


def _resolver_rango_finanzas(request, hoy):
    """Rango rápido compatible con el antiguo ?periodo=YYYY-MM."""
    rango = request.GET.get("rango", "").strip()
    periodo_legacy = request.GET.get("periodo", "").strip()

    if periodo_legacy and not rango:
        try:
            anio_texto, mes_texto = periodo_legacy.split("-", 1)
            anio = int(anio_texto)
            mes = int(mes_texto)
            inicio = date(anio, mes, 1)
            fin = date(
                anio,
                mes,
                monthrange(anio, mes)[1],
            )
            return {
                "rango": "personalizado_mes",
                "inicio": inicio,
                "fin": fin,
                "periodo": periodo_legacy,
                "label": inicio.strftime("%m/%Y"),
            }
        except (TypeError, ValueError):
            pass

    if rango == "mes_anterior":
        primero_actual = hoy.replace(day=1)
        fin = primero_actual - timedelta(days=1)
        inicio = fin.replace(day=1)
        return {
            "rango": rango,
            "inicio": inicio,
            "fin": fin,
            "periodo": inicio.strftime("%Y-%m"),
            "label": "Mes anterior",
        }

    if rango == "anio":
        inicio = date(hoy.year, 1, 1)
        fin = date(hoy.year, 12, 31)
        return {
            "rango": rango,
            "inicio": inicio,
            "fin": fin,
            "periodo": hoy.strftime("%Y-%m"),
            "label": f"Año {hoy.year}",
        }

    if rango == "personalizado":
        try:
            inicio = date.fromisoformat(
                request.GET.get("desde", "")
            )
            fin = date.fromisoformat(
                request.GET.get("hasta", "")
            )
            if inicio > fin:
                inicio, fin = fin, inicio
            return {
                "rango": rango,
                "inicio": inicio,
                "fin": fin,
                "periodo": inicio.strftime("%Y-%m"),
                "label": (
                    f"{inicio:%d/%m/%Y} – "
                    f"{fin:%d/%m/%Y}"
                ),
            }
        except (TypeError, ValueError):
            pass

    inicio = hoy.replace(day=1)
    fin = date(
        hoy.year,
        hoy.month,
        monthrange(hoy.year, hoy.month)[1],
    )
    return {
        "rango": "mes_actual",
        "inicio": inicio,
        "fin": fin,
        "periodo": hoy.strftime("%Y-%m"),
        "label": "Este mes",
    }


# ==========================================================
# FINANZAS / RENTABILIDAD
# ==========================================================
def _restaurar_empaques_pedido(pedido):
    usos = list(
        PedidoEmpaque.objects
        .select_for_update()
        .filter(pedido=pedido)
        .prefetch_related("complementos")
        .order_by("insumo_id", "id")
    )
    for uso in usos:
        _restaurar_uso_empaque(uso)
    if usos:
        PedidoEmpaque.objects.filter(
            id__in=[uso.id for uso in usos]
        ).delete()
    return len(usos)


# FINANZAS / RENTABILIDAD
# ==========================================================

def finanzas(request):
    hoy = timezone.localdate()
    rango = _resolver_rango_finanzas(
        request,
        hoy,
    )
    inicio = rango["inicio"]
    fin = rango["fin"]
    periodo = rango["periodo"]

    vistas_validas = {
        "resumen",
        "cobros",
        "gastos",
        "cuotas",
        "caja",
        "rentabilidad",
    }
    vista = request.GET.get(
        "vista",
        "resumen",
    ).strip().lower()
    if vista not in vistas_validas:
        vista = "resumen"

    # ------------------------------------------------------
    # RENTABILIDAD DEL PERÍODO
    # Acotada por fechas: nunca carga el historial completo.
    # ------------------------------------------------------
    pedidos_periodo = (
        Pedido.objects
        .filter(
            fecha__gte=inicio,
            fecha__lte=fin,
        )
        .exclude(estado="CANCELADO")
        .select_related("cliente")
        .prefetch_related(
            "detalles__producto__tipo",
            "detalles__kit__componentes__producto__tipo",
            "detalles__productos_kit__producto__tipo",
            "pagos",
            "empaques_usados__complementos__insumo",
        )
        .order_by("-fecha", "-id")
    )

    ventas = Decimal("0")
    costos = Decimal("0")
    cobrado_pedidos = Decimal("0")
    saldo_periodo = Decimal("0")
    detalles_sin_snapshot = 0
    filas_rentabilidad = []

    for pedido in pedidos_periodo:
        venta_pedido = pedido.total
        costo_pedido = Decimal("0")
        usa_estimacion_actual = False

        for detalle in pedido.detalles.all():
            if detalle.estado == "CANCELADO":
                continue

            if detalle.costo_unitario is not None:
                costo_detalle = (
                    detalle.costo_unitario
                    * detalle.cantidad
                )
            else:
                costo_detalle = _costo_actual_detalle(
                    detalle
                )
                detalles_sin_snapshot += 1
                usa_estimacion_actual = True

            costo_pedido += costo_detalle

        (
            costo_empaque_pedido,
            empaque_estimado,
        ) = costo_embalaje_para_rentabilidad(pedido)
        costo_pedido += costo_empaque_pedido

        ganancia_pedido = (
            venta_pedido - costo_pedido
        )
        margen_pedido = (
            ganancia_pedido
            * Decimal("100")
            / venta_pedido
            if venta_pedido > 0
            else Decimal("0")
        )

        pagado_pedido = pedido.total_pagado
        saldo_pedido = pedido.saldo_pendiente

        ventas += venta_pedido
        costos += costo_pedido
        cobrado_pedidos += pagado_pedido
        saldo_periodo += saldo_pedido

        if vista == "rentabilidad":
            filas_rentabilidad.append(
                {
                    "pedido": pedido,
                    "venta": venta_pedido,
                    "costo": costo_pedido,
                    "costo_empaque": costo_empaque_pedido,
                    "empaque_estimado": empaque_estimado,
                    "ganancia": ganancia_pedido,
                    "margen": margen_pedido,
                    "pagado": pagado_pedido,
                    "saldo": saldo_pedido,
                    "usa_estimacion_actual":
                        usa_estimacion_actual,
                }
            )

    ganancia = ventas - costos
    margen = (
        ganancia
        * Decimal("100")
        / ventas
        if ventas > 0
        else Decimal("0")
    )

    cobrado_periodo = (
        Pago.objects
        .filter(
            fecha__date__gte=inicio,
            fecha__date__lte=fin,
        )
        .aggregate(total=Sum("monto"))
        .get("total")
        or Decimal("0")
    )

    # ------------------------------------------------------
    # COBROS ACTUALES - SQL + paginación
    # ------------------------------------------------------
    cobros_qs = (
        _pedidos_con_saldo_finanzas()
        .order_by(
            "fecha_entrega",
            "id",
        )
    )

    saldo_resumen = (
        cobros_qs
        .aggregate(
            total=Sum("saldo_fin"),
            cantidad=models.Count("id"),
        )
    )
    saldo_total_actual = (
        saldo_resumen.get("total")
        or Decimal("0")
    )
    pedidos_con_saldo_actual = (
        saldo_resumen.get("cantidad")
        or 0
    )

    cobrado_hoy = (
        Pago.objects
        .filter(fecha__date=hoy)
        .aggregate(total=Sum("monto"))
        .get("total")
        or Decimal("0")
    )

    # El selector de cobro es un atajo, no un historial.
    # Limitamos su tamaño para que el modal siga siendo ágil
    # cuando la cartera de clientes crezca.
    cobros_modal = list(
        cobros_qs[:50]
    )
    cobros_pendientes_modal = [
        {
            "pedido": pedido,
            "total": pedido.total_fin,
            "pagado": pedido.pagado_fin,
            "saldo": pedido.saldo_fin,
        }
        for pedido in cobros_modal
    ]

    cobros_pagina = None
    busqueda_cobros = request.GET.get(
        "q",
        "",
    ).strip()

    if vista == "cobros":
        cobros_filtrados = cobros_qs

        if busqueda_cobros:
            filtro = models.Q(
                cliente__nombre__icontains=
                    busqueda_cobros
            ) | models.Q(
                cliente__telefono__icontains=
                    busqueda_cobros
            )
            if busqueda_cobros.isdigit():
                filtro |= models.Q(
                    id=int(busqueda_cobros)
                )
            cobros_filtrados = (
                cobros_filtrados.filter(filtro)
            )

        cobros_pagina = Paginator(
            cobros_filtrados,
            20,
        ).get_page(
            request.GET.get("page")
        )

    # ------------------------------------------------------
    # GASTOS DEL PERÍODO
    # ------------------------------------------------------
    gastos_base = (
        Gasto.objects
        .filter(
            fecha_compra__gte=inicio,
            fecha_compra__lte=fin,
        )
        .prefetch_related("cuotas")
        .order_by(
            "-fecha_compra",
            "-id",
        )
    )

    gastos_operativos = (
        gastos_base
        .filter(tipo="OPERATIVO")
        .aggregate(total=Sum("monto_total"))
        .get("total")
        or Decimal("0")
    )
    inversiones_periodo = (
        gastos_base
        .filter(tipo="INVERSION")
        .aggregate(total=Sum("monto_total"))
        .get("total")
        or Decimal("0")
    )

    resultado_operativo = (
        ganancia - gastos_operativos
    )

    gastos_pagina = None
    filtro_tipo_gasto = request.GET.get(
        "tipo_gasto",
        "",
    ).strip().upper()
    filtro_categoria_gasto = request.GET.get(
        "categoria_gasto",
        "",
    ).strip().upper()

    if vista == "gastos":
        gastos_filtrados = gastos_base
        if filtro_tipo_gasto in {
            valor for valor, _ in Gasto.TIPOS
        }:
            gastos_filtrados = (
                gastos_filtrados.filter(
                    tipo=filtro_tipo_gasto
                )
            )
        if filtro_categoria_gasto in {
            valor for valor, _ in Gasto.CATEGORIAS
        }:
            gastos_filtrados = (
                gastos_filtrados.filter(
                    categoria=
                        filtro_categoria_gasto
                )
            )

        gastos_pagina = Paginator(
            gastos_filtrados,
            20,
        ).get_page(
            request.GET.get("page")
        )

    # ------------------------------------------------------
    # CUOTAS / CAJA
    # ------------------------------------------------------
    cuotas_pagadas_periodo = (
        CuotaGasto.objects
        .filter(
            pagada=True,
            fecha_pago__gte=inicio,
            fecha_pago__lte=fin,
        )
        .aggregate(total=Sum("monto"))
        .get("total")
        or Decimal("0")
    )

    flujo_neto_caja = (
        cobrado_periodo
        - cuotas_pagadas_periodo
    )

    deuda_pendiente = (
        CuotaGasto.objects
        .filter(pagada=False)
        .aggregate(total=Sum("monto"))
        .get("total")
        or Decimal("0")
    )

    limite_7 = hoy + timedelta(days=7)
    limite_30 = hoy + timedelta(days=30)
    limite_90 = hoy + timedelta(days=90)

    compromiso_7_qs = (
        CuotaGasto.objects
        .filter(
            pagada=False,
            fecha_vencimiento__gte=hoy,
            fecha_vencimiento__lte=limite_7,
        )
    )
    compromiso_7 = (
        compromiso_7_qs
        .aggregate(total=Sum("monto"))
        .get("total")
        or Decimal("0")
    )
    compromiso_30 = (
        CuotaGasto.objects
        .filter(
            pagada=False,
            fecha_vencimiento__gte=hoy,
            fecha_vencimiento__lte=limite_30,
        )
        .aggregate(total=Sum("monto"))
        .get("total")
        or Decimal("0")
    )
    compromiso_90 = (
        CuotaGasto.objects
        .filter(
            pagada=False,
            fecha_vencimiento__gte=hoy,
            fecha_vencimiento__lte=limite_90,
        )
        .aggregate(total=Sum("monto"))
        .get("total")
        or Decimal("0")
    )

    vencidas_qs = (
        CuotaGasto.objects
        .filter(
            pagada=False,
            fecha_vencimiento__lt=hoy,
        )
    )
    vencidas_resumen = (
        vencidas_qs.aggregate(
            total=Sum("monto"),
            cantidad=models.Count("id"),
        )
    )
    cuotas_vencidas_total = (
        vencidas_resumen.get("total")
        or Decimal("0")
    )
    cuotas_vencidas_count = (
        vencidas_resumen.get("cantidad")
        or 0
    )

    cuotas_pagina = None
    filtro_cuota = request.GET.get(
        "estado_cuota",
        "PENDIENTES",
    ).strip().upper()

    if vista == "cuotas":
        cuotas_filtradas = (
            CuotaGasto.objects
            .select_related("gasto")
            .order_by(
                "pagada",
                "fecha_vencimiento",
                "id",
            )
        )
        if filtro_cuota == "PAGADAS":
            cuotas_filtradas = (
                cuotas_filtradas.filter(
                    pagada=True
                )
            )
        elif filtro_cuota == "TODAS":
            pass
        else:
            filtro_cuota = "PENDIENTES"
            cuotas_filtradas = (
                cuotas_filtradas.filter(
                    pagada=False
                )
            )

        cuotas_pagina = Paginator(
            cuotas_filtradas,
            20,
        ).get_page(
            request.GET.get("page")
        )

    caja = _resumen_caja_mercadopago(
        hoy
    )
    saldo_caja = caja["saldo_estimado"]
    reserva_30 = compromiso_30
    disponible_operativo = max(
        saldo_caja - reserva_30,
        Decimal("0"),
    )

    if caja["requiere_corte"]:
        estado_caja = "SIN_CORTE"
        accion_caja = (
            "Cargá el saldo real de Mercado Pago "
            "para establecer un punto de control."
        )
    elif saldo_caja < compromiso_7:
        estado_caja = "URGENTE"
        accion_caja = (
            "La caja estimada no cubre los compromisos "
            "de los próximos 7 días."
        )
    elif saldo_caja < reserva_30:
        estado_caja = "AJUSTADA"
        accion_caja = (
            "La caja cubre lo inmediato pero no todos "
            "los compromisos de 30 días."
        )
    else:
        estado_caja = "OK"
        accion_caja = (
            "La caja estimada cubre los compromisos "
            "de los próximos 30 días."
        )

    cortes_pagina = None
    if vista == "caja":
        cortes_pagina = Paginator(
            CajaCorte.objects.order_by(
                "-fecha",
                "-id",
            ),
            20,
        ).get_page(
            request.GET.get("page")
        )

    # ------------------------------------------------------
    # ACTIVIDAD RECIENTE DEL CENTRO
    # ------------------------------------------------------
    ultimos_pagos = list(
        Pago.objects
        .select_related(
            "pedido",
            "pedido__cliente",
        )
        .order_by(
            "-fecha",
            "-id",
        )[:5]
    )
    ultimos_gastos = list(
        Gasto.objects
        .order_by(
            "-fecha_compra",
            "-id",
        )[:5]
    )
    cuotas_proximas = list(
        CuotaGasto.objects
        .filter(
            pagada=False,
            fecha_vencimiento__lte=limite_30,
        )
        .select_related("gasto")
        .order_by(
            "fecha_vencimiento",
            "id",
        )[:5]
    )

    # ------------------------------------------------------
    # ALERTAS OPERATIVAS
    # ------------------------------------------------------
    alertas_finanzas = []

    if cuotas_vencidas_count:
        alertas_finanzas.append(
            {
                "nivel": "danger",
                "titulo": (
                    f"{cuotas_vencidas_count} cuota(s) vencida(s)"
                ),
                "detalle": (
                    f"$ {cuotas_vencidas_total:,.0f} "
                    "pendientes de regularizar"
                ),
                "vista": "cuotas",
            }
        )

    if pedidos_con_saldo_actual:
        alertas_finanzas.append(
            {
                "nivel": "warning",
                "titulo": (
                    f"{pedidos_con_saldo_actual} pedido(s) "
                    "con saldo"
                ),
                "detalle": (
                    f"$ {saldo_total_actual:,.0f} "
                    "por cobrar"
                ),
                "vista": "cobros",
            }
        )

    if caja["requiere_corte"]:
        alertas_finanzas.append(
            {
                "nivel": "warning",
                "titulo": "Caja sin conciliar",
                "detalle": (
                    "Cargá el saldo real de Mercado Pago."
                ),
                "vista": "caja",
            }
        )
    elif estado_caja in {"URGENTE", "AJUSTADA"}:
        alertas_finanzas.append(
            {
                "nivel": (
                    "danger"
                    if estado_caja == "URGENTE"
                    else "warning"
                ),
                "titulo": (
                    "Atención de caja"
                    if estado_caja == "URGENTE"
                    else "Caja ajustada"
                ),
                "detalle": accion_caja,
                "vista": "caja",
            }
        )

    # ------------------------------------------------------
    # RENTABILIDAD DETALLADA: sólo cuando se solicita
    # ------------------------------------------------------
    rentabilidad_pagina = None
    acumulado = None
    gastos_operativos_acumulados = Decimal("0")
    inversion_total = Decimal("0")
    resultado_operativo_acumulado = Decimal("0")
    inversion_recuperada = Decimal("0")
    inversion_pendiente = Decimal("0")
    porcentaje_recuperado = Decimal("0")
    meses_estimados = None
    ventas_objetivo_recuperacion = None

    if vista == "rentabilidad":
        rentabilidad_pagina = Paginator(
            filas_rentabilidad,
            20,
        ).get_page(
            request.GET.get("page")
        )

        acumulado = _rentabilidad_acumulada()

        gastos_operativos_acumulados = (
            Gasto.objects
            .filter(tipo="OPERATIVO")
            .aggregate(total=Sum("monto_total"))
            .get("total")
            or Decimal("0")
        )
        inversion_total = (
            Gasto.objects
            .filter(tipo="INVERSION")
            .aggregate(total=Sum("monto_total"))
            .get("total")
            or Decimal("0")
        )

        resultado_operativo_acumulado = (
            acumulado["ganancia_bruta"]
            - gastos_operativos_acumulados
        )

        capacidad_recuperacion = max(
            resultado_operativo_acumulado,
            Decimal("0"),
        )
        inversion_recuperada = min(
            capacidad_recuperacion,
            inversion_total,
        )
        inversion_pendiente = max(
            inversion_total
            - inversion_recuperada,
            Decimal("0"),
        )

        if inversion_total > 0:
            porcentaje_recuperado = (
                inversion_recuperada
                * Decimal("100")
                / inversion_total
            )

        margen_operativo_periodo = (
            resultado_operativo / ventas
            if ventas > 0
            else Decimal("0")
        )

        if (
            inversion_pendiente > 0
            and resultado_operativo > 0
        ):
            meses_estimados = int(
                (
                    inversion_pendiente
                    / resultado_operativo
                ).to_integral_value(
                    rounding="ROUND_CEILING"
                )
            )

        if (
            inversion_pendiente > 0
            and margen_operativo_periodo > 0
        ):
            ventas_objetivo_recuperacion = (
                inversion_pendiente
                / margen_operativo_periodo
            )

    # ------------------------------------------------------
    # Query para tabs/paginación sin perder período/filtros
    # ------------------------------------------------------
    query_base = request.GET.copy()
    query_base.pop("page", None)
    query_base.pop("vista", None)
    if "rango" not in query_base and not request.GET.get("periodo"):
        query_base["rango"] = rango["rango"]
    query_base_encoded = query_base.urlencode()

    query_pagina = request.GET.copy()
    query_pagina.pop("page", None)
    query_pagina_encoded = query_pagina.urlencode()

    return render(
        request,
        "pedidos/finanzas.html",
        {
            "hoy": hoy,
            "vista": vista,
            "rango": rango,
            "periodo": periodo,
            "inicio_periodo": inicio,
            "fin_periodo": fin,
            "query_base": query_base_encoded,
            "query_pagina": query_pagina_encoded,

            "ventas": ventas,
            "costos": costos,
            "ganancia": ganancia,
            "margen": margen,
            "cobrado_periodo": cobrado_periodo,
            "cobrado_pedidos": cobrado_pedidos,
            "saldo": saldo_periodo,
            "cantidad_pedidos": pedidos_periodo.count(),
            "detalles_sin_snapshot":
                detalles_sin_snapshot,

            "saldo_total_actual":
                saldo_total_actual,
            "pedidos_con_saldo_actual":
                pedidos_con_saldo_actual,
            "cobrado_hoy": cobrado_hoy,
            "cobros_pendientes":
                cobros_pendientes_modal,
            "cobros_pagina": cobros_pagina,
            "busqueda_cobros":
                busqueda_cobros,

            "gastos_operativos":
                gastos_operativos,
            "inversiones_periodo":
                inversiones_periodo,
            "resultado_operativo":
                resultado_operativo,
            "gastos_pagina": gastos_pagina,
            "filtro_tipo_gasto":
                filtro_tipo_gasto,
            "filtro_categoria_gasto":
                filtro_categoria_gasto,

            "cuotas_pagadas_periodo":
                cuotas_pagadas_periodo,
            "flujo_neto_caja":
                flujo_neto_caja,
            "deuda_pendiente":
                deuda_pendiente,
            "cuotas_proximas":
                cuotas_proximas,
            "cuotas_pagina":
                cuotas_pagina,
            "filtro_cuota": filtro_cuota,
            "cuotas_vencidas_count":
                cuotas_vencidas_count,
            "cuotas_vencidas_total":
                cuotas_vencidas_total,
            "compromiso_7":
                compromiso_7,
            "compromiso_30":
                compromiso_30,
            "compromiso_90":
                compromiso_90,

            "caja": caja,
            "saldo_caja": saldo_caja,
            "reserva_30": reserva_30,
            "disponible_operativo":
                disponible_operativo,
            "estado_caja": estado_caja,
            "accion_caja": accion_caja,
            "cortes_pagina":
                cortes_pagina,

            "alertas_finanzas":
                alertas_finanzas,
            "ultimos_pagos":
                ultimos_pagos,
            "ultimos_gastos":
                ultimos_gastos,

            "rentabilidad_pagina":
                rentabilidad_pagina,
            "ventas_acumuladas": (
                acumulado["ventas"]
                if acumulado
                else Decimal("0")
            ),
            "ganancia_bruta_acumulada": (
                acumulado["ganancia_bruta"]
                if acumulado
                else Decimal("0")
            ),
            "gastos_operativos_acumulados":
                gastos_operativos_acumulados,
            "resultado_operativo_acumulado":
                resultado_operativo_acumulado,
            "inversion_total":
                inversion_total,
            "inversion_recuperada":
                inversion_recuperada,
            "inversion_pendiente":
                inversion_pendiente,
            "porcentaje_recuperado":
                porcentaje_recuperado,
            "meses_estimados":
                meses_estimados,
            "ventas_objetivo_recuperacion":
                ventas_objetivo_recuperacion,

            "medios_pago": Pago.MEDIOS,
            "tipos_gasto": Gasto.TIPOS,
            "categorias_gasto":
                Gasto.CATEGORIAS,
            "medios_gasto":
                Gasto.MEDIOS_PAGO,
        },
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
        )
        .filter(
            models.Q(stock_descontado=True)
            | models.Q(reservado_stock=True)
        )
        .select_related("producto")
    )

    for estado_impresion in estados_impresion:
        producto = Producto.objects.select_for_update().get(
            id=estado_impresion.producto_id
        )

        producto.stock += (
            int(estado_impresion.cantidad_stock_descontada or 0)
            + int(estado_impresion.cantidad_stock_reservada or 0)
        )

        producto.save(
            update_fields=["stock"]
        )

        estado_impresion.listo = False
        estado_impresion.stock_descontado = False
        estado_impresion.cantidad_stock_descontada = 0
        estado_impresion.reservado_stock = False
        estado_impresion.cantidad_stock_reservada = 0

        estado_impresion.save(
            update_fields=[
                "listo",
                "stock_descontado",
                "cantidad_stock_descontada",
                "reservado_stock",
                "cantidad_stock_reservada",
            ]
        )

    _restaurar_empaques_pedido(pedido)

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
        )
        .filter(
            models.Q(stock_descontado=True)
            | models.Q(reservado_stock=True)
        )
        .select_related("producto")
    )

    for estado_impresion in estados_impresion:
        producto = Producto.objects.select_for_update().get(
            id=estado_impresion.producto_id
        )

        producto.stock += (
            int(estado_impresion.cantidad_stock_descontada or 0)
            + int(estado_impresion.cantidad_stock_reservada or 0)
        )

        producto.save(
            update_fields=["stock"]
        )

    _restaurar_empaques_pedido(pedido)

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
