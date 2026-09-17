from django.shortcuts import get_object_or_404, render

from .models import Pedido


def detalle_pedido(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects
        .select_related("cliente")
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
            "pagos",
        ),
        id=pedido_id,
    )

    detalles = list(pedido.detalles.all())
    pagos = list(pedido.pagos.all())

    cantidad_unidades = sum(
        detalle.cantidad
        for detalle in detalles
        if detalle.estado != "CANCELADO"
    )

    return render(
        request,
        "pedidos/detalle.html",
        {
            "pedido": pedido,
            "detalles": detalles,
            "pagos": pagos,
            "cantidad_lineas": len(detalles),
            "cantidad_unidades": cantidad_unidades,
        },
    )
