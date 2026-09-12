from django.shortcuts import render
from django.db.models import Q

from .models import Producto, TipoProducto


def lista_productos(request):

    busqueda = request.GET.get(
        "q",
        ""
    ).strip()

    tipo_id = request.GET.get(
        "tipo",
        ""
    ).strip()

    productos = (
        Producto.objects
        .select_related("tipo")
        .all()
        .order_by("nombre")
    )


    if busqueda:

        productos = productos.filter(
            Q(nombre__icontains=busqueda)
            |
            Q(id__icontains=busqueda)
        )


    if tipo_id:

        productos = productos.filter(
            tipo_id=tipo_id
        )


    tipos = (
        TipoProducto.objects
        .filter(activo=True)
        .order_by("nombre")
    )


    return render(
        request,
        "productos/lista.html",
        {
            "productos": productos,
            "tipos": tipos,
            "busqueda": busqueda,
            "tipo_seleccionado": tipo_id,
        }
    )