from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from productos.models import Producto, TipoProducto

from .elegibilidad_catalogo import (
    costo_operativo_producto,
    productos_elegibles_para_kit,
)
from .models import Kit, KitComponente


def lista_kits(request):
    kits = (
        Kit.objects
        .select_related("tipo_producto")
        .prefetch_related(
            "componentes__producto"
        )
        .order_by("nombre")
    )

    return render(
        request,
        "kits/lista.html",
        {
            "kits": kits,
        },
    )


@transaction.atomic
def nuevo_kit(request):
    return _formulario_kit(
        request=request,
        kit=None,
    )


@transaction.atomic
def editar_kit(request, kit_id):
    kit = get_object_or_404(
        Kit.objects
        .select_for_update()
        .prefetch_related(
            "componentes__producto"
        ),
        id=kit_id,
    )

    return _formulario_kit(
        request=request,
        kit=kit,
    )


def _formulario_kit(
    request,
    kit=None,
):
    tipos = (
        TipoProducto.objects
        .filter(activo=True)
        .order_by("nombre")
    )

    productos = list(
        Producto.objects
        .filter(activo=True)
        .select_related("tipo")
        .order_by("nombre")
    )
    for producto in productos:
        producto.costo_kit = costo_operativo_producto(producto)

    if request.method == "POST":

        nombre = request.POST.get(
            "nombre",
            "",
        ).strip()

        modalidad = request.POST.get(
            "modalidad",
            "LIBRE_CATEGORIA",
        ).strip()

        tipo_producto_id = request.POST.get(
            "tipo_producto",
            "",
        ).strip()

        cantidad_texto = request.POST.get(
            "cantidad_productos",
            "1",
        ).strip()

        precio_texto = request.POST.get(
            "precio",
            "0",
        ).strip().replace(",", ".")

        activo = (
            request.POST.get("activo")
            == "1"
        )

        if not nombre:
            messages.error(
                request,
                "Ingresá un nombre para el kit.",
            )
            return _render_form(
                request,
                kit,
                tipos,
                productos,
            )

        if modalidad not in {
            "LIBRE_CATEGORIA",
            "FIJO",
        }:
            messages.error(
                request,
                "La modalidad del kit no es válida.",
            )
            return _render_form(
                request,
                kit,
                tipos,
                productos,
            )

        try:
            precio = Decimal(precio_texto)
        except (
            InvalidOperation,
            TypeError,
            ValueError,
        ):
            precio = Decimal("0")

        if precio <= 0:
            messages.error(
                request,
                "El precio del kit debe ser mayor a cero.",
            )
            return _render_form(
                request,
                kit,
                tipos,
                productos,
            )

        if kit is None:
            kit = Kit()

        kit.nombre = nombre
        kit.modalidad = modalidad
        kit.precio = precio
        kit.activo = activo

        if modalidad == "LIBRE_CATEGORIA":

            if not tipo_producto_id:
                messages.error(
                    request,
                    (
                        "Un kit libre necesita una "
                        "categoría/tipo de producto."
                    ),
                )
                return _render_form(
                    request,
                    kit,
                    tipos,
                    productos,
                )

            try:
                cantidad_productos = int(
                    cantidad_texto
                )
            except (
                TypeError,
                ValueError,
            ):
                cantidad_productos = 0

            if cantidad_productos <= 0:
                messages.error(
                    request,
                    (
                        "La cantidad de productos del "
                        "kit debe ser mayor a cero."
                    ),
                )
                return _render_form(
                    request,
                    kit,
                    tipos,
                    productos,
                )

            tipo_producto = get_object_or_404(
                TipoProducto,
                id=tipo_producto_id,
                activo=True,
            )

            kit.tipo_producto = tipo_producto
            kit.cantidad_productos = (
                cantidad_productos
            )
            kit.save()

            # Un kit libre no usa receta fija.
            kit.componentes.all().delete()

        else:
            # =========================================
            # KIT FIJO
            # =========================================

            producto_ids = request.POST.getlist(
                "componente_producto"
            )

            cantidades = request.POST.getlist(
                "componente_cantidad"
            )

            componentes = {}

            for producto_id, cantidad_raw in zip(
                producto_ids,
                cantidades,
            ):
                producto_id = (
                    producto_id or ""
                ).strip()

                cantidad_raw = (
                    cantidad_raw or ""
                ).strip()

                if not producto_id:
                    continue

                try:
                    cantidad = int(
                        cantidad_raw
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    cantidad = 0

                if cantidad <= 0:
                    messages.error(
                        request,
                        (
                            "Todas las cantidades de "
                            "la composición fija deben "
                            "ser mayores a cero."
                        ),
                    )
                    return _render_form(
                        request,
                        kit,
                        tipos,
                        productos,
                    )

                producto = get_object_or_404(
                    Producto,
                    id=producto_id,
                    activo=True,
                )

                if producto.id not in componentes:
                    componentes[
                        producto.id
                    ] = {
                        "producto": producto,
                        "cantidad": 0,
                    }

                componentes[
                    producto.id
                ]["cantidad"] += cantidad

            if not componentes:
                messages.error(
                    request,
                    (
                        "Un kit de composición fija "
                        "necesita al menos un producto."
                    ),
                )
                return _render_form(
                    request,
                    kit,
                    tipos,
                    productos,
                )

            total_piezas = sum(
                item["cantidad"]
                for item in componentes.values()
            )

            kit.tipo_producto = None
            kit.cantidad_productos = total_piezas
            kit.save()

            kit.componentes.all().delete()

            for item in componentes.values():
                KitComponente.objects.create(
                    kit=kit,
                    producto=item["producto"],
                    cantidad=item["cantidad"],
                )

        messages.success(
            request,
            f"{kit.nombre} guardado correctamente.",
        )

        if kit.modalidad == "LIBRE_CATEGORIA":
            candidatos = list(
                Producto.objects
                .filter(
                    tipo_id=kit.tipo_producto_id,
                    activo=True,
                    solo_produccion=False,
                )
                .order_by("nombre")
            )
            if not productos_elegibles_para_kit(
                kit,
                candidatos,
            ):
                messages.warning(
                    request,
                    (
                        "El kit quedó sin opciones rentables con el precio "
                        "actual, por lo que no se publicará en el catálogo "
                        "hasta que ajustes precio, cantidad o costos."
                    ),
                )

        return redirect(
            "kits:lista",
        )

    return _render_form(
        request,
        kit,
        tipos,
        productos,
    )


def _render_form(
    request,
    kit,
    tipos,
    productos,
):
    componentes_iniciales = []

    if kit and kit.id:
        componentes_iniciales = [
            {
                "producto_id":
                    componente.producto_id,
                "cantidad":
                    componente.cantidad,
            }
            for componente
            in kit.componentes.all()
        ]

    return render(
        request,
        "kits/formulario.html",
        {
            "kit": kit,
            "tipos": tipos,
            "productos": productos,
            "componentes_iniciales":
                componentes_iniciales,
        },
    )
