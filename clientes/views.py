from decimal import Decimal

from django.contrib import messages
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render

from pedidos.detalle_views import _armar_preparacion
from pedidos.models import Pedido

from .models import Cliente
from .telefonos import buscar_cliente_por_telefono


def _pedidos_cliente_queryset():
    """Todos los pedidos existentes forman parte del historial del cliente."""
    return (
        Pedido.objects
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
            "pagos",
        )
        .order_by("-id")
    )


def _pedido_vigente(pedido):
    return pedido.estado != "CANCELADO"


def lista_clientes(request):
    busqueda = request.GET.get("q", "").strip()

    clientes = (
        Cliente.objects
        .filter(activo=True)
        .prefetch_related(
            Prefetch(
                "pedidos",
                queryset=_pedidos_cliente_queryset(),
                to_attr="pedidos_historial_cache",
            )
        )
        .order_by("nombre")
    )

    if busqueda:
        clientes = clientes.filter(
            Q(nombre__icontains=busqueda)
            | Q(telefono__icontains=busqueda)
            | Q(email__icontains=busqueda)
        )

    filas = []
    total_comprado_general = Decimal("0")
    saldo_pendiente_general = Decimal("0")
    clientes_con_saldo = 0

    for cliente in clientes:
        pedidos = cliente.pedidos_historial_cache
        pedidos_vigentes = [
            pedido for pedido in pedidos
            if _pedido_vigente(pedido)
        ]

        total_comprado = Decimal("0")
        total_pagado = Decimal("0")
        saldo_pendiente = Decimal("0")

        for pedido in pedidos_vigentes:
            total_comprado += pedido.total
            total_pagado += pedido.total_pagado
            saldo_pendiente += pedido.saldo_pendiente

        total_comprado_general += total_comprado
        saldo_pendiente_general += saldo_pendiente

        if saldo_pendiente > 0:
            clientes_con_saldo += 1

        filas.append(
            {
                "cliente": cliente,
                "cantidad_pedidos": len(pedidos),
                "cantidad_cancelados": sum(
                    1 for pedido in pedidos
                    if pedido.estado == "CANCELADO"
                ),
                "total_comprado": total_comprado,
                "total_pagado": total_pagado,
                "saldo_pendiente": saldo_pendiente,
                "ultimo_pedido": pedidos[0] if pedidos else None,
            }
        )

    return render(
        request,
        "clientes/lista_v2.html",
        {
            "filas": filas,
            "busqueda": busqueda,
            "cantidad_clientes": len(filas),
            "total_comprado_general": total_comprado_general,
            "saldo_pendiente_general": saldo_pendiente_general,
            "clientes_con_saldo": clientes_con_saldo,
        },
    )


def detalle_cliente(request, cliente_id):
    cliente = get_object_or_404(
        Cliente,
        id=cliente_id,
    )

    if request.method == "POST":
        nombre = request.POST.get("nombre", "").strip()
        telefono = request.POST.get("telefono", "").strip()
        email = request.POST.get("email", "").strip()
        observaciones = request.POST.get("observaciones", "").strip()

        if not nombre:
            messages.error(
                request,
                "El nombre del cliente no puede quedar vacío."
            )
            return redirect(
                f"{request.path}?editar=1"
            )

        existente = buscar_cliente_por_telefono(
            telefono,
            excluir_id=cliente.id,
        )
        if existente:
            messages.error(
                request,
                (
                    f"Ese teléfono ya pertenece a {existente.nombre} "
                    f"({existente.codigo})."
                ),
            )
            return redirect(
                f"{request.path}?editar=1"
            )

        cliente.nombre = nombre
        cliente.telefono = telefono
        cliente.email = email
        cliente.observaciones = observaciones
        cliente.save(
            update_fields=[
                "nombre",
                "telefono",
                "email",
                "observaciones",
            ]
        )

        messages.success(
            request,
            "Datos del cliente actualizados."
        )

        return redirect(
            "clientes:detalle",
            cliente_id=cliente.id,
        )

    pedidos = list(
        _pedidos_cliente_queryset()
        .filter(cliente=cliente)
    )

    filas_pedidos = []

    total_comprado = Decimal("0")
    total_pagado = Decimal("0")
    saldo_pendiente = Decimal("0")

    for pedido in pedidos:
        total = pedido.total
        pagado = pedido.total_pagado
        cancelado = pedido.estado == "CANCELADO"
        entregado = pedido.estado == "ENTREGADO"
        activo = not cancelado and not entregado
        saldo_modelo = pedido.saldo_pendiente

        if not cancelado:
            total_comprado += total
            total_pagado += pagado
            saldo_pendiente += saldo_modelo

        preparacion = _armar_preparacion(pedido) if activo else []
        preparacion_total = len(preparacion)
        preparacion_listos = sum(
            1 for item_preparacion in preparacion
            if item_preparacion["listo"]
        )
        preparacion_porcentaje = (
            int(round((preparacion_listos * 100) / preparacion_total))
            if preparacion_total
            else 0
        )
        faltantes_stock = sum(
            1 for item_preparacion in preparacion
            if item_preparacion.get("estado_operativo") == "FALTANTE"
        )

        filas_pedidos.append(
            {
                "pedido": pedido,
                "total": total,
                "pagado": pagado,
                # Los cancelados quedan visibles, pero ya no integran
                # la cuenta corriente ni habilitan nuevos pagos.
                "saldo": Decimal("0") if cancelado else saldo_modelo,
                "saldo_historico": saldo_modelo,
                "estado_pago": "CANCELADO" if cancelado else pedido.estado_pago,
                "estado_pago_display": (
                    "Cancelado" if cancelado else pedido.estado_pago_display
                ),
                "cancelado": cancelado,
                "entregado": entregado,
                "activo": activo,
                "preparacion": preparacion,
                "preparacion_total": preparacion_total,
                "preparacion_listos": preparacion_listos,
                "preparacion_porcentaje": preparacion_porcentaje,
                "faltantes_stock": faltantes_stock,
            }
        )

    return render(
        request,
        "clientes/detalle_v2.html",
        {
            "cliente": cliente,
            "filas_pedidos": filas_pedidos,
            "cantidad_pedidos": len(filas_pedidos),
            "cantidad_cancelados": sum(
                1 for fila in filas_pedidos
                if fila["cancelado"]
            ),
            "total_comprado": total_comprado,
            "total_pagado": total_pagado,
            "saldo_pendiente": saldo_pendiente,
            "modo_edicion": request.GET.get("editar") == "1",
        },
    )
