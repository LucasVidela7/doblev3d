from decimal import Decimal

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import Cliente


def lista_clientes(request):
    busqueda = request.GET.get("q", "").strip()

    clientes = (
        Cliente.objects
        .filter(activo=True)
        .order_by("nombre")
    )

    if busqueda:
        clientes = clientes.filter(
            Q(nombre__icontains=busqueda)
            | Q(telefono__icontains=busqueda)
            | Q(email__icontains=busqueda)
        )

    filas = []

    for cliente in clientes:
        pedidos = (
            cliente.pedidos
            .exclude(estado="CANCELADO")
            .prefetch_related(
                "detalles__producto",
                "detalles__kit",
                "detalles__productos_kit__producto",
                "pagos",
            )
            .order_by("-id")
        )

        total_comprado = Decimal("0")
        total_pagado = Decimal("0")
        saldo_pendiente = Decimal("0")

        for pedido in pedidos:
            total_comprado += pedido.total
            total_pagado += pedido.total_pagado
            saldo_pendiente += pedido.saldo_pendiente

        filas.append(
            {
                "cliente": cliente,
                "cantidad_pedidos": pedidos.count(),
                "total_comprado": total_comprado,
                "total_pagado": total_pagado,
                "saldo_pendiente": saldo_pendiente,
            }
        )

    return render(
        request,
        "clientes/lista.html",
        {
            "filas": filas,
            "busqueda": busqueda,
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
                "clientes:detalle",
                cliente_id=cliente.id,
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

    pedidos = (
        cliente.pedidos
        .exclude(estado="CANCELADO")
        .prefetch_related(
            "detalles",
            "pagos",
        )
        .order_by("-id")
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
        "clientes/detalle.html",
        {
            "cliente": cliente,
            "filas_pedidos": filas_pedidos,
            "cantidad_pedidos": len(filas_pedidos),
            "total_comprado": total_comprado,
            "total_pagado": total_pagado,
            "saldo_pendiente": saldo_pendiente,
        },
    )
