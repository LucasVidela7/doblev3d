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


@transaction.atomic
def _armar_producto(producto_id, cantidad):
    """Consume piezas y genera stock terminado de forma atómica."""
    from stock.models import MovimientoStock

    producto = (
        Producto.objects
        .select_for_update()
        .get(id=producto_id)
    )

    if producto.tipo_fabricacion != "COMPUESTO":
        raise ValueError("Solo se pueden armar productos compuestos.")
    if cantidad <= 0:
        raise ValueError("La cantidad a armar debe ser mayor a cero.")

    relaciones = list(
        producto.componentes
        .select_related("componente")
        .order_by("componente_id")
    )
    if not relaciones:
        raise ValueError("El producto compuesto no tiene piezas configuradas.")

    consumos = []
    for relacion in relaciones:
        pieza = (
            Producto.objects
            .select_for_update()
            .get(id=relacion.componente_id)
        )
        necesaria = int(relacion.cantidad) * cantidad
        if pieza.stock < necesaria:
            raise ValueError(
                f"Stock insuficiente de {pieza.nombre}: "
                f"se necesitan {necesaria} y hay {pieza.stock}."
            )
        consumos.append((pieza, necesaria))

    referencia = f"ARMADO {producto.codigo}"
    for pieza, necesaria in consumos:
        pieza.stock -= necesaria
        pieza.save(update_fields=["stock"])
        MovimientoStock.objects.create(
            producto=pieza,
            tipo="SALIDA_ARMADO",
            cantidad=necesaria,
            referencia=referencia,
            observaciones=(
                f"Consumo para armar {cantidad} unidad(es) "
                f"de {producto.nombre}."
            ),
        )

    producto.stock += cantidad
    producto.save(update_fields=["stock"])
    MovimientoStock.objects.create(
        producto=producto,
        tipo="ENTRADA_ARMADO",
        cantidad=cantidad,
        referencia=referencia,
        observaciones="Ingreso de producto compuesto terminado.",
    )

    return producto, consumos


def armar_producto(request, producto_id):
    if request.method != "POST":
        return redirect("productos:detalle", producto_id=producto_id)

    cantidad = _entero(request.POST.get("cantidad"), 0)
    try:
        producto, _ = _armar_producto(producto_id, cantidad)
    except Producto.DoesNotExist:
        messages.error(request, "El producto no existe.")
    except ValueError as error:
        messages.error(request, str(error))
    else:
        messages.success(
            request,
            f"Se armaron {cantidad} unidad(es) de {producto.nombre}.",
        )

    return redirect("productos:detalle", producto_id=producto_id)


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
    """Lee piezas existentes y nuevas sin crear nada todavía."""
    modos = request.POST.getlist("componente_modo")
    ids = request.POST.getlist("componente_id")
    nombres = request.POST.getlist("componente_nombre")
    horas_lista = request.POST.getlist("componente_horas")
    minutos_lista = request.POST.getlist("componente_minutos")
    pesos = request.POST.getlist("componente_peso")
    cantidades = request.POST.getlist("componente_cantidad")

    total_filas = max(
        len(modos), len(ids), len(nombres), len(horas_lista),
        len(minutos_lista), len(pesos), len(cantidades), 0,
    )

    componentes = []
    errores = []
    ids_existentes = set()
    nombres_nuevos = set()

    for indice in range(total_filas):
        modo = (modos[indice] if indice < len(modos) else "EXISTENTE").strip().upper()
        cantidad = _entero(
            cantidades[indice] if indice < len(cantidades) else 0,
            0,
        )

        if cantidad <= 0:
            errores.append(f"La cantidad de la pieza {indice + 1} debe ser mayor a cero.")
            continue

        if modo == "NUEVA":
            nombre = (nombres[indice] if indice < len(nombres) else "").strip()
            horas = max(_entero(horas_lista[indice] if indice < len(horas_lista) else 0, 0), 0)
            minutos = max(_entero(minutos_lista[indice] if indice < len(minutos_lista) else 0, 0), 0)
            peso = max(_decimal(pesos[indice] if indice < len(pesos) else 0), Decimal("0"))

            if minutos >= 60:
                horas += minutos // 60
                minutos %= 60

            if not nombre:
                errores.append(f"Ingresá el nombre de la pieza nueva {indice + 1}.")
                continue
            if horas == 0 and minutos == 0:
                errores.append(f"La pieza nueva '{nombre}' debe tener un tiempo mayor a 0.")
                continue
            if peso <= 0:
                errores.append(f"La pieza nueva '{nombre}' debe tener un peso mayor a 0.")
                continue

            clave_nombre = nombre.casefold()
            if clave_nombre in nombres_nuevos:
                errores.append(f"La pieza nueva '{nombre}' está repetida en la composición.")
                continue

            existente_mismo_nombre = Producto.objects.filter(
                nombre__iexact=nombre,
                tipo_fabricacion="SIMPLE",
                activo=True,
            ).first()
            if existente_mismo_nombre:
                errores.append(
                    f"Ya existe la pieza '{existente_mismo_nombre.nombre}' "
                    f"({existente_mismo_nombre.codigo}). Seleccionala como pieza existente."
                )
                continue

            nombres_nuevos.add(clave_nombre)
            componentes.append(
                {
                    "modo": "NUEVA",
                    "nombre": nombre,
                    "horas": horas,
                    "minutos": minutos,
                    "peso": peso,
                    "cantidad": cantidad,
                }
            )
            continue

        componente_id = (ids[indice] if indice < len(ids) else "").strip()
        if not componente_id:
            errores.append(f"Seleccioná una pieza existente en la fila {indice + 1}.")
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

        if pieza.id in ids_existentes:
            errores.append(f"La pieza '{pieza.nombre}' está repetida en la composición.")
            continue

        ids_existentes.add(pieza.id)
        componentes.append(
            {
                "modo": "EXISTENTE",
                "producto": pieza,
                "cantidad": cantidad,
            }
        )

    return componentes, errores


def _crear_pieza_interna(item, tipo, margen_ganancia):
    """Crea una pieza simple interna con los datos mínimos de fabricación."""
    return Producto.objects.create(
        nombre=item["nombre"],
        categoria="PRODUCTO",
        tipo=tipo,
        horas=item["horas"],
        minutos=item["minutos"],
        peso_gramos=item["peso"],
        margen_ganancia=margen_ganancia,
        requiere_impresion=True,
        personalizable=False,
        stock=0,
        activo=True,
        tipo_fabricacion="SIMPLE",
        solo_produccion=True,
    )


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
        if producto and any(
            item.get("producto") and item["producto"].id == producto.id
            for item in componentes
        ):
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
            if item["modo"] == "NUEVA":
                pieza = _crear_pieza_interna(
                    item,
                    tipo=tipo,
                    margen_ganancia=margen_ganancia,
                )
            else:
                pieza = item["producto"]

            ProductoComponente.objects.create(
                producto=producto,
                componente=pieza,
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
