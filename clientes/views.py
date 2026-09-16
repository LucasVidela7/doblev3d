from decimal import Decimal

from django.contrib import messages
from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render

from pedidos.models import Pedido

from .models import Cliente


def _pedidos_cliente_queryset():
    return (
        Pedido.objects
        .exclude(estado="CANCELADO")
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
            "pagos",
        )
        .order_by("-id")
    )


def lista_clientes(request):
    busqueda = request.GET.get("q", "").strip()

    clientes = (
        Cliente.objects
        .filter(activo=True)
        .prefetch_related(
            Prefetch(
                "pedidos",
                queryset=_pedidos_cliente_queryset(),
                to_attr="pedidos_activos_cache",
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
        pedidos = cliente.pedidos_activos_cache

        total_comprado = Decimal("0")
        total_pagado = Decimal("0")
        saldo_pendiente = Decimal("0")

        for pedido in pedidos:
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
        saldo = pedido.saldo_pendiente

        total_comprado += total
        total_pagado += pagado
        saldo_pendiente += saldo

        filas_pedidos.append(
            {
                "pedido": pedido,
                "total": total,
                "pagado": pagado,
                "saldo": saldo,
                "estado_pago": pedido.estado_pago,
                "estado_pago_display": pedido.estado_pago_display,
            }
        )

    return render(
        request,
        "clientes/detalle_v2.html",
        {
            "cliente": cliente,
            "filas_pedidos": filas_pedidos,
            "cantidad_pedidos": len(filas_pedidos),
            "total_comprado": total_comprado,
            "total_pagado": total_pagado,
            "saldo_pendiente": saldo_pendiente,
            "modo_edicion": request.GET.get("editar") == "1",
        },
    )
