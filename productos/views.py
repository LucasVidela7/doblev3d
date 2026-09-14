from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from .models import Producto, ProductoComponente, TipoProducto


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
    mostrar_piezas = request.GET.get("piezas", "") == "1"

    productos = (
        Producto.objects
        .select_related("tipo")
        .prefetch_related("componentes__componente")
        .all()
        .order_by("-activo", "nombre")
    )

    if not mostrar_piezas:
        productos = productos.filter(solo_produccion=False)

    if busqueda:
        filtros = Q(nombre__icontains=busqueda)
        numero = busqueda.upper().replace("P", "").strip()
        if numero.isdigit():
            filtros |= Q(id=int(numero))
        productos = productos.filter(filtros)

    if tipo_seleccionado:
        productos = productos.filter(tipo_id=tipo_seleccionado)

    tipos = TipoProducto.objects.filter(activo=True).order_by("nombre")

    parametros_toggle = request.GET.copy()
    if mostrar_piezas:
        parametros_toggle.pop("piezas", None)
    else:
        parametros_toggle["piezas"] = "1"

    piezas_toggle_url = request.path
    query_toggle = parametros_toggle.urlencode()
    if query_toggle:
        piezas_toggle_url = f"{piezas_toggle_url}?{query_toggle}"

    return render(
        request,
        "productos/lista.html",
        {
            "productos": productos,
            "tipos": tipos,
            "busqueda": busqueda,
            "tipo_seleccionado": tipo_seleccionado,
            "mostrar_piezas": mostrar_piezas,
            "piezas_toggle_url": piezas_toggle_url,
        },
    )


def detalle(request, producto_id):
    producto = get_object_or_404(
        Producto.objects
        .select_related("tipo")
        .prefetch_related("componentes__componente"),
        id=producto_id,
    )
    return render(request, "productos/detalle.html", {"producto": producto})


def _piezas_disponibles(producto=None):
    qs = Producto.objects.filter(
        activo=True,
        requiere_impresion=True,
        tipo_fabricacion="SIMPLE",
    ).order_by("nombre")
    if producto and producto.pk:
        qs = qs.exclude(pk=producto.pk)
    return qs


def _leer_componentes_post(request):
    componentes = {}
    errores = []

    ids = request.POST.getlist("componente_id")
    cantidades = request.POST.getlist("componente_cantidad")

    for indice, componente_id in enumerate(ids):
        componente_id = (componente_id or "").strip()
        if not componente_id:
            continue

        cantidad = _entero(
            cantidades[indice] if indice < len(cantidades) else 0,
            0,
        )
        if cantidad <= 0:
            errores.append("La cantidad de cada pieza debe ser mayor a cero.")
            continue

        pieza = Producto.objects.filter(
            id=componente_id,
            activo=True,
            requiere_impresion=True,
            tipo_fabricacion="SIMPLE",
        ).first()

        if not pieza:
            errores.append("Una de las piezas seleccionadas no es válida.")
            continue

        componentes[pieza.id] = {
            "producto": pieza,
            "cantidad": componentes.get(pieza.id, {}).get("cantidad", 0) + cantidad,
        }

    return list(componentes.values()), errores


@transaction.atomic
def _guardar_producto_desde_post(request, producto=None):
    nombre = request.POST.get("nombre", "").strip()
    categoria = request.POST.get("categoria", "").strip()
    tipo_id = request.POST.get("tipo", "").strip()
    tipo_fabricacion = request.POST.get("tipo_fabricacion", "SIMPLE").strip()

    horas = max(_entero(request.POST.get("horas"), 0), 0)
    minutos = max(_entero(request.POST.get("minutos"), 0), 0)
    peso_gramos = max(_decimal(request.POST.get("peso_gramos")), Decimal("0"))
    margen_ganancia = _decimal(request.POST.get("margen_ganancia"), Decimal("0"))
    stock = _entero(request.POST.get("stock"), 0)
    requiere_impresion = request.POST.get("requiere_impresion") == "1"
    personalizable = request.POST.get("personalizable") == "1"
    activo = request.POST.get("activo") == "1"
    solo_produccion = request.POST.get("solo_produccion") == "1"

    errores = []

    if not nombre:
        errores.append("Ingresá el nombre del producto.")

    categorias_validas = {clave for clave, _ in Producto.CATEGORIAS}
    if categoria not in categorias_validas:
        errores.append("Seleccioná una categoría válida.")

    tipo = TipoProducto.objects.filter(id=tipo_id, activo=True).first()
    if not tipo:
        errores.append("Seleccioná un tipo de producto válido.")

    if tipo_fabricacion not in {"SIMPLE", "COMPUESTO"}:
        errores.append("Seleccioná un tipo de fabricación válido.")

    if minutos >= 60:
        horas += minutos // 60
        minutos %= 60

    if margen_ganancia < 0 or margen_ganancia >= 100:
        errores.append("El margen debe ser mayor o igual a 0 y menor a 100%.")

    componentes = []
    if tipo_fabricacion == "COMPUESTO":
        requiere_impresion = True
        solo_produccion = False
        componentes, errores_componentes = _leer_componentes_post(request)
        errores.extend(errores_componentes)
        if not componentes:
            errores.append("Un producto compuesto debe tener al menos una pieza.")
        if producto and any(item["producto"].id == producto.id for item in componentes):
            errores.append("Un producto no puede contenerse a sí mismo.")
    elif requiere_impresion:
        if horas == 0 and minutos == 0:
            errores.append("Un producto que requiere impresión debe tener un tiempo mayor a 0.")
        if peso_gramos <= 0:
            errores.append("Un producto que requiere impresión debe tener un peso mayor a 0.")

    if solo_produccion:
        tipo_fabricacion = "SIMPLE"
        personalizable = False
        requiere_impresion = True

    if errores:
        return None, errores

    if producto is None:
        producto = Producto()

    producto.nombre = nombre
    producto.categoria = categoria
    producto.tipo = tipo
    producto.margen_ganancia = margen_ganancia
    producto.requiere_impresion = requiere_impresion
    producto.personalizable = personalizable
    producto.stock = stock
    producto.activo = activo
    producto.tipo_fabricacion = tipo_fabricacion
    producto.solo_produccion = solo_produccion

    if tipo_fabricacion == "SIMPLE":
        producto.horas = horas
        producto.minutos = minutos
        producto.peso_gramos = peso_gramos
    else:
        producto.horas = 0
        producto.minutos = 0
        producto.peso_gramos = Decimal("0")

    producto.save()

    if tipo_fabricacion == "COMPUESTO":
        ProductoComponente.objects.filter(producto=producto).delete()
        for item in componentes:
            ProductoComponente.objects.create(
                producto=producto,
                componente=item["producto"],
                cantidad=item["cantidad"],
            )
        producto.refresh_from_db()
        producto.recalcular_desde_componentes()
    else:
        ProductoComponente.objects.filter(producto=producto).delete()

    return producto, []


def _contexto_formulario(request, producto, modo):
    componentes_actuales = []
    if producto and producto.pk:
        componentes_actuales = list(
            producto.componentes.select_related("componente").all()
        )

    return {
        "producto": producto,
        "tipos": TipoProducto.objects.filter(activo=True).order_by("nombre"),
        "categorias": Producto.CATEGORIAS,
        "tipos_fabricacion": Producto.TIPOS_FABRICACION,
        "piezas": _piezas_disponibles(producto),
        "componentes_actuales": componentes_actuales,
        "modo": modo,
    }


def nuevo(request):
    if request.method == "POST":
        producto, errores = _guardar_producto_desde_post(request)
        if not errores:
            messages.success(request, f"{producto.codigo} creado correctamente.")
            return redirect("productos:detalle", producto_id=producto.id)
        for error in errores:
            messages.error(request, error)

    return render(
        request,
        "productos/formulario.html",
        _contexto_formulario(request, None, "nuevo"),
    )


def editar(request, producto_id):
    producto = get_object_or_404(Producto, id=producto_id)

    if request.method == "POST":
        producto_guardado, errores = _guardar_producto_desde_post(request, producto)
        if not errores:
            messages.success(
                request,
                f"{producto_guardado.codigo} actualizado correctamente.",
            )
            return redirect("productos:detalle", producto_id=producto_guardado.id)
        for error in errores:
            messages.error(request, error)

    return render(
        request,
        "productos/formulario.html",
        _contexto_formulario(request, producto, "editar"),
    )


def cambiar_activo(request, producto_id):
    if request.method != "POST":
        return redirect("productos:detalle", producto_id=producto_id)

    producto = get_object_or_404(Producto, id=producto_id)
    producto.activo = not producto.activo
    producto.save(update_fields=["activo"])

    messages.success(
        request,
        f"{producto.codigo} {'activado' if producto.activo else 'desactivado'}.",
    )
    return redirect("productos:detalle", producto_id=producto.id)
