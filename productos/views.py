from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import Producto, TipoProducto


def _entero(valor, default=0):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return default


def _decimal(valor, default=Decimal("0")):
    if valor is None:
        return default

    texto = str(valor).strip().replace(",", ".")

    if texto == "":
        return default

    try:
        return Decimal(texto)
    except (InvalidOperation, TypeError, ValueError):
        return default


def lista(request):
    busqueda = request.GET.get("q", "").strip()
    tipo_seleccionado = request.GET.get("tipo", "").strip()

    productos = (
        Producto.objects
        .select_related("tipo")
        .all()
        .order_by("-activo", "nombre")
    )

    if busqueda:
        filtros = Q(nombre__icontains=busqueda)

        numero = busqueda.upper().replace("P", "").strip()
        if numero.isdigit():
            filtros |= Q(id=int(numero))

        productos = productos.filter(filtros)

    if tipo_seleccionado:
        productos = productos.filter(
            tipo_id=tipo_seleccionado
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
            "tipo_seleccionado": tipo_seleccionado,
        },
    )


def detalle(request, producto_id):
    producto = get_object_or_404(
        Producto.objects.select_related("tipo"),
        id=producto_id,
    )

    return render(
        request,
        "productos/detalle.html",
        {
            "producto": producto,
        },
    )


def _guardar_producto_desde_post(request, producto=None):
    nombre = request.POST.get("nombre", "").strip()
    categoria = request.POST.get("categoria", "").strip()
    tipo_id = request.POST.get("tipo", "").strip()

    horas = max(
        _entero(request.POST.get("horas"), 0),
        0,
    )

    minutos = max(
        _entero(request.POST.get("minutos"), 0),
        0,
    )

    peso_gramos = max(
        _decimal(request.POST.get("peso_gramos")),
        Decimal("0"),
    )

    margen_ganancia = _decimal(
        request.POST.get("margen_ganancia"),
        Decimal("0"),
    )

    stock = _entero(
        request.POST.get("stock"),
        0,
    )

    requiere_impresion = (
        request.POST.get("requiere_impresion")
        == "1"
    )

    personalizable = (
        request.POST.get("personalizable")
        == "1"
    )

    activo = (
        request.POST.get("activo")
        == "1"
    )

    errores = []

    if not nombre:
        errores.append(
            "Ingresá el nombre del producto."
        )

    categorias_validas = {
        clave
        for clave, _ in Producto.CATEGORIAS
    }

    if categoria not in categorias_validas:
        errores.append(
            "Seleccioná una categoría válida."
        )

    tipo = (
        TipoProducto.objects
        .filter(
            id=tipo_id,
            activo=True,
        )
        .first()
    )

    if not tipo:
        errores.append(
            "Seleccioná un tipo de producto válido."
        )

    if minutos >= 60:
        horas += minutos // 60
        minutos %= 60

    if margen_ganancia < 0 or margen_ganancia >= 100:
        errores.append(
            "El margen debe ser mayor o igual a 0 y menor a 100%."
        )

    if requiere_impresion:
        if horas == 0 and minutos == 0:
            errores.append(
                "Un producto que requiere impresión debe tener un tiempo mayor a 0."
            )

        if peso_gramos <= 0:
            errores.append(
                "Un producto que requiere impresión debe tener un peso mayor a 0."
            )

    if errores:
        return None, errores

    if producto is None:
        producto = Producto()

    producto.nombre = nombre
    producto.categoria = categoria
    producto.tipo = tipo
    producto.horas = horas
    producto.minutos = minutos
    producto.peso_gramos = peso_gramos
    producto.margen_ganancia = margen_ganancia
    producto.requiere_impresion = requiere_impresion
    producto.personalizable = personalizable
    producto.stock = stock
    producto.activo = activo

    producto.save()

    return producto, []


def nuevo(request):
    tipos = (
        TipoProducto.objects
        .filter(activo=True)
        .order_by("nombre")
    )

    if request.method == "POST":
        producto, errores = (
            _guardar_producto_desde_post(
                request,
                producto=None,
            )
        )

        if not errores:
            messages.success(
                request,
                f"{producto.codigo} creado correctamente.",
            )

            return redirect(
                "productos:detalle",
                producto_id=producto.id,
            )

        for error in errores:
            messages.error(request, error)

    return render(
        request,
        "productos/formulario.html",
        {
            "producto": None,
            "tipos": tipos,
            "categorias": Producto.CATEGORIAS,
            "modo": "nuevo",
        },
    )


def editar(request, producto_id):
    producto = get_object_or_404(
        Producto,
        id=producto_id,
    )

    tipos = (
        TipoProducto.objects
        .filter(activo=True)
        .order_by("nombre")
    )

    if request.method == "POST":
        producto_guardado, errores = (
            _guardar_producto_desde_post(
                request,
                producto=producto,
            )
        )

        if not errores:
            messages.success(
                request,
                f"{producto_guardado.codigo} actualizado correctamente.",
            )

            return redirect(
                "productos:detalle",
                producto_id=producto_guardado.id,
            )

        for error in errores:
            messages.error(request, error)

    return render(
        request,
        "productos/formulario.html",
        {
            "producto": producto,
            "tipos": tipos,
            "categorias": Producto.CATEGORIAS,
            "modo": "editar",
        },
    )


def cambiar_activo(request, producto_id):
    if request.method != "POST":
        return redirect(
            "productos:detalle",
            producto_id=producto_id,
        )

    producto = get_object_or_404(
        Producto,
        id=producto_id,
    )

    producto.activo = not producto.activo
    producto.save(
        update_fields=["activo"]
    )

    messages.success(
        request,
        (
            f"{producto.codigo} activado."
            if producto.activo
            else f"{producto.codigo} desactivado."
        ),
    )

    return redirect(
        "productos:detalle",
        producto_id=producto.id,
    )
