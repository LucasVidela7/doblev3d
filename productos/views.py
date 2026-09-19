from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Prefetch, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render

from calculadora.precios import MARGEN_MINIMO

from .image_environment import entorno_imagenes
from .image_models import ProductoImagen
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



def _imagen_prefetch():
    return Prefetch(
        "imagenes",
        queryset=(
            ProductoImagen.objects
            .filter(ambiente=entorno_imagenes())
            .order_by("orden", "id")
        ),
        to_attr="imagenes_entorno",
    )


def _url_con_filtros(request, **cambios):
    parametros = request.GET.copy()
    for clave, valor in cambios.items():
        if valor in (None, ""):
            parametros.pop(clave, None)
        else:
            parametros[clave] = valor

    query = parametros.urlencode()
    return request.path + (f"?{query}" if query else "")


def _enriquecer_productos(productos):
    """
    Agrega estado operativo sin persistir datos nuevos:
    demanda, producción, reserva de stock, rentabilidad, kits e imagen.
    """
    productos = list(productos)
    if not productos:
        return productos

    from kits.models import Kit, KitComponente
    from pedidos.impresiones_stock import obtener_impresiones_por_producto
    from pedidos.models import EstadoImpresionPedido
    from produccion.models import Produccion

    ids = [producto.id for producto in productos]
    tipos_ids = {
        producto.tipo_id
        for producto in productos
        if producto.tipo_id
    }

    produccion_por_producto = {
        producto_id: {"planificadas": 0, "imprimiendo": 0}
        for producto_id in ids
    }
    for fila in (
        Produccion.objects
        .filter(
            producto_id__in=ids,
            estado__in=["PENDIENTE", "IMPRIMIENDO"],
        )
        .values("producto_id", "estado")
        .annotate(total=Sum("cantidad"))
    ):
        datos = produccion_por_producto.setdefault(
            fila["producto_id"],
            {"planificadas": 0, "imprimiendo": 0},
        )
        if fila["estado"] == "PENDIENTE":
            datos["planificadas"] = int(fila["total"] or 0)
        else:
            datos["imprimiendo"] = int(fila["total"] or 0)

    reservas = {
        fila["producto_id"]: int(fila["total"] or 0)
        for fila in (
            EstadoImpresionPedido.objects
            .filter(
                producto_id__in=ids,
                reservado_stock=True,
            )
            .exclude(
                pedido__estado__in=["ENTREGADO", "CANCELADO"],
            )
            .values("producto_id")
            .annotate(total=Sum("cantidad_stock_reservada"))
        )
    }

    kits_fijos = {
        fila["producto_id"]: int(fila["total"] or 0)
        for fila in (
            KitComponente.objects
            .filter(
                producto_id__in=ids,
                kit__activo=True,
            )
            .values("producto_id")
            .annotate(total=Count("kit_id", distinct=True))
        )
    }

    kits_libres = {
        fila["tipo_producto_id"]: int(fila["total"] or 0)
        for fila in (
            Kit.objects
            .filter(
                activo=True,
                modalidad="LIBRE_CATEGORIA",
                tipo_producto_id__in=tipos_ids,
            )
            .values("tipo_producto_id")
            .annotate(total=Count("id"))
        )
    }

    necesidades = {
        item["producto"].id: item
        for item in obtener_impresiones_por_producto()
        if item.get("producto")
    }

    for producto in productos:
        imagenes = getattr(producto, "imagenes_entorno", [])
        imagen = imagenes[0] if imagenes else None
        producto.imagen_principal_url = (
            (imagen.thumbnail_url or imagen.url)
            if imagen
            else ""
        )

        produccion = produccion_por_producto.get(
            producto.id,
            {"planificadas": 0, "imprimiendo": 0},
        )
        producto.planificadas = produccion["planificadas"]
        producto.imprimiendo = produccion["imprimiendo"]

        necesidad = necesidades.get(producto.id, {})
        producto.demanda_pedidos = int(
            necesidad.get("cantidad_pedida")
            or necesidad.get("a_imprimir")
            or 0
        )
        producto.falta_iniciar = int(
            necesidad.get("falta_iniciar") or 0
        )
        producto.falta_normal_planificar = int(
            necesidad.get("falta_normal_planificar") or 0
        )
        producto.prioridad_operativa = (
            necesidad.get("prioridad")
            or ("EN CURSO" if producto.planificadas or producto.imprimiendo else "")
        )
        producto.origenes_demanda = necesidad.get("origenes") or []

        producto.stock_reservado = reservas.get(producto.id, 0)
        producto.stock_disponible = max(
            int(producto.stock or 0) - producto.stock_reservado,
            0,
        )

        producto.kits_relacionados_count = (
            kits_fijos.get(producto.id, 0)
            + kits_libres.get(producto.tipo_id, 0)
        )

        costo = Decimal(str(producto.costo or 0))
        seguro = Decimal(str(producto.seguro or 0))
        precio = Decimal(str(producto.subtotal or 0))
        producto.costo_productivo = costo + seguro
        producto.margen_real = Decimal("0")
        if precio > 0:
            producto.margen_real = (
                (precio - producto.costo_productivo)
                / precio
                * Decimal("100")
            ).quantize(Decimal("0.1"))

        producto.stock_estado = "OK"
        producto.stock_estado_clase = "ok"
        if int(producto.stock or 0) <= 0:
            producto.stock_estado = "SIN STOCK"
            producto.stock_estado_clase = "danger"
        elif int(producto.stock or 0) <= 2:
            producto.stock_estado = "BAJO"
            producto.stock_estado_clase = "warning"

        alertas = []
        if (
            producto.requiere_impresion
            and producto.horas_totales <= 0
        ):
            alertas.append("Falta tiempo de impresión")
        if (
            producto.requiere_impresion
            and Decimal(str(producto.peso_gramos or 0)) <= 0
        ):
            alertas.append("Falta peso")
        if producto.requiere_impresion and precio <= 0:
            alertas.append("Precio sin calcular")
        elif (
            producto.requiere_impresion
            and precio > 0
            and producto.margen_real < MARGEN_MINIMO
        ):
            alertas.append(
                f"Margen debajo de {MARGEN_MINIMO}%"
            )
        if producto.falta_iniciar > 0:
            alertas.append(
                f"Faltan planificar {producto.falta_iniciar}"
            )

        producto.alertas_operativas = alertas
        producto.necesita_atencion = bool(alertas)
        producto.salud_clase = (
            "danger"
            if any(
                texto.startswith("Falta") or "Margen" in texto
                for texto in alertas
            )
            else ("warning" if alertas else "ok")
        )

    return productos


def lista(request):
    busqueda = request.GET.get("q", "").strip()
    tipo_seleccionado = request.GET.get("tipo", "").strip()
    estado_seleccionado = request.GET.get("estado", "").strip()
    mostrar_piezas = request.GET.get("piezas", "") == "1"

    productos_qs = (
        Producto.objects
        .select_related("tipo")
        .prefetch_related(
            "componentes__componente",
            _imagen_prefetch(),
        )
        .all()
        .order_by("-activo", "nombre")
    )

    if not mostrar_piezas:
        productos_qs = productos_qs.filter(solo_produccion=False)

    if busqueda:
        filtros = Q(nombre__icontains=busqueda)
        numero = busqueda.upper().replace("P", "").strip()
        if numero.isdigit():
            filtros |= Q(id=int(numero))
        productos_qs = productos_qs.filter(filtros)

    if tipo_seleccionado:
        productos_qs = productos_qs.filter(
            tipo_id=tipo_seleccionado
        )

    productos_base = _enriquecer_productos(productos_qs)

    metricas = {
        "total": len(productos_base),
        "activos": sum(1 for p in productos_base if p.activo),
        "sin_stock": sum(
            1 for p in productos_base
            if int(p.stock or 0) <= 0 and not p.solo_produccion
        ),
        "bajo_stock": sum(
            1 for p in productos_base
            if 0 < int(p.stock or 0) <= 2 and not p.solo_produccion
        ),
        "atencion": sum(
            1 for p in productos_base if p.necesita_atencion
        ),
        "con_demanda": sum(
            1 for p in productos_base
            if p.demanda_pedidos > 0
            or p.planificadas > 0
            or p.imprimiendo > 0
        ),
    }

    filtros_estado = {
        "activos": lambda p: p.activo,
        "inactivos": lambda p: not p.activo,
        "sin_stock": lambda p: (
            int(p.stock or 0) <= 0 and not p.solo_produccion
        ),
        "bajo_stock": lambda p: (
            0 < int(p.stock or 0) <= 2 and not p.solo_produccion
        ),
        "atencion": lambda p: p.necesita_atencion,
        "demanda": lambda p: (
            p.demanda_pedidos > 0
            or p.planificadas > 0
            or p.imprimiendo > 0
        ),
        "compuestos": lambda p: p.es_compuesto,
    }
    if estado_seleccionado in filtros_estado:
        productos = [
            producto
            for producto in productos_base
            if filtros_estado[estado_seleccionado](producto)
        ]
    else:
        productos = productos_base

    tipos = TipoProducto.objects.filter(
        activo=True
    ).order_by("nombre")

    parametros_toggle = request.GET.copy()
    if mostrar_piezas:
        parametros_toggle.pop("piezas", None)
    else:
        parametros_toggle["piezas"] = "1"

    piezas_toggle_url = request.path
    query_toggle = parametros_toggle.urlencode()
    if query_toggle:
        piezas_toggle_url = f"{piezas_toggle_url}?{query_toggle}"

    filtro_urls = {
        "todos": _url_con_filtros(request, estado=None),
        "activos": _url_con_filtros(request, estado="activos"),
        "sin_stock": _url_con_filtros(request, estado="sin_stock"),
        "bajo_stock": _url_con_filtros(request, estado="bajo_stock"),
        "atencion": _url_con_filtros(request, estado="atencion"),
        "demanda": _url_con_filtros(request, estado="demanda"),
        "compuestos": _url_con_filtros(request, estado="compuestos"),
    }

    return render(
        request,
        "productos/lista.html",
        {
            "productos": productos,
            "tipos": tipos,
            "busqueda": busqueda,
            "tipo_seleccionado": tipo_seleccionado,
            "estado_seleccionado": estado_seleccionado,
            "mostrar_piezas": mostrar_piezas,
            "piezas_toggle_url": piezas_toggle_url,
            "metricas": metricas,
            "filtro_urls": filtro_urls,
        },
    )


def detalle(request, producto_id):
    from kits.models import Kit
    from produccion.models import Produccion
    from stock.models import MovimientoStock

    producto = get_object_or_404(
        Producto.objects
        .select_related("tipo")
        .prefetch_related(
            "componentes__componente",
            "usado_como_componente__producto",
            _imagen_prefetch(),
        ),
        id=producto_id,
    )
    _enriquecer_productos([producto])

    producciones_activas = list(
        Produccion.objects
        .filter(
            producto=producto,
            estado__in=["PENDIENTE", "IMPRIMIENDO"],
        )
        .select_related("impresora", "pedido", "pedido__cliente")
        .order_by("estado", "inicio_impresion", "id")
    )

    movimientos_stock = list(
        MovimientoStock.objects
        .filter(producto=producto)
        .order_by("-fecha", "-id")[:10]
    )

    kits_relacionados = list(
        Kit.objects
        .filter(
            Q(
                modalidad="FIJO",
                componentes__producto=producto,
            )
            | Q(
                modalidad="LIBRE_CATEGORIA",
                tipo_producto=producto.tipo,
            ),
            activo=True,
        )
        .distinct()
        .order_by("nombre")
    )

    productos_padre = [
        relacion.producto
        for relacion in producto.usado_como_componente.all()
    ]

    cantidad_sugerida = max(
        producto.falta_normal_planificar,
        producto.falta_iniciar,
        1,
    )

    return render(
        request,
        "productos/detalle.html",
        {
            "producto": producto,
            "producciones_activas": producciones_activas,
            "movimientos_stock": movimientos_stock,
            "kits_relacionados": kits_relacionados,
            "productos_padre": productos_padre,
            "cantidad_sugerida": cantidad_sugerida,
            "margen_minimo": MARGEN_MINIMO,
        },
    )


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
        _enriquecer_productos([producto])

    return {
        "producto": producto,
        "tipos": TipoProducto.objects.filter(activo=True).order_by("nombre"),
        "categorias": Producto.CATEGORIAS,
        "tipos_fabricacion": Producto.TIPOS_FABRICACION,
        "piezas": _piezas_disponibles(producto),
        "componentes_actuales": componentes_actuales,
        "modo": modo,
        "margen_minimo": MARGEN_MINIMO,
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
