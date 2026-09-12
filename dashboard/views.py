from django.shortcuts import render

from pedidos.models import Pedido
from produccion.models import Produccion


def inicio(request):
    pedidos_activos = (
        Pedido.objects
        .exclude(
            estado__in=[
                "ENTREGADO",
                "CANCELADO",
            ]
        )
        .count()
    )

    pedidos_listos = (
        Pedido.objects
        .filter(
            estado="LISTO"
        )
        .count()
    )

    producciones_pendientes = (
        Produccion.objects
        .filter(
            estado="PENDIENTE"
        )
        .count()
    )

    producciones_imprimiendo = (
        Produccion.objects
        .filter(
            estado="IMPRIMIENDO"
        )
        .count()
    )

    return render(
        request,
        "dashboard/inicio.html",
        {
            "pedidos_activos": pedidos_activos,
            "pedidos_listos": pedidos_listos,
            "producciones_pendientes": producciones_pendientes,
            "producciones_imprimiendo": producciones_imprimiendo,
        },
    )
