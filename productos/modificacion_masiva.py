from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import redirect, render

from .models import Producto, TipoProducto


BOOLEAN_FIELDS = {
    "activo": ("Activo", "activo"),
    "permite_elegir_color": ("Permite elegir color", "permite_color"),
    "personalizable": ("Personalizable", "personalizable"),
    "requiere_impresion": ("Requiere impresión", "requiere_impresion"),
}


def _decimal(valor):
    try:
        return Decimal(str(valor or "").strip().replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _filtrar_productos(data):
    qs = (
        Producto.objects
        .filter(solo_produccion=False)
        .select_related("tipo")
        .order_by("-activo", "nombre", "id")
    )

    busqueda = str(data.get("q") or "").strip()
    tipo = str(data.get("tipo") or "").strip()
    categoria = str(data.get("categoria") or "").strip()
    activo = str(data.get("f_activo") or "").strip()
    color = str(data.get("f_color") or "").strip()
    personalizable = str(data.get("f_personalizable") or "").strip()

    if busqueda:
        filtro = Q(nombre__icontains=busqueda)
        codigo = busqueda.upper().replace("P", "").strip()
        if codigo.isdigit():
            filtro |= Q(id=int(codigo))
        qs = qs.filter(filtro)

    if tipo.isdigit():
        qs = qs.filter(tipo_id=int(tipo))

    categorias_validas = {clave for clave, _ in Producto.CATEGORIAS}
    if categoria in categorias_validas:
        qs = qs.filter(categoria=categoria)

    if activo in {"1", "0"}:
        qs = qs.filter(activo=(activo == "1"))

    if color in {"1", "0"}:
        qs = qs.filter(permite_elegir_color=(color == "1"))

    if personalizable in {"1", "0"}:
        qs = qs.filter(personalizable=(personalizable == "1"))

    return qs


def _leer_acciones(request):
    acciones = {}
    errores = []

    for campo_modelo, (_, campo_post) in BOOLEAN_FIELDS.items():
        valor = str(request.POST.get(campo_post) or "").strip()
        if valor in {"1", "0"}:
            acciones[campo_modelo] = valor == "1"

    categoria = str(request.POST.get("accion_categoria") or "").strip()
    categorias_validas = {clave for clave, _ in Producto.CATEGORIAS}
    if categoria:
        if categoria not in categorias_validas:
            errores.append("La categoría seleccionada no es válida.")
        else:
            acciones["categoria"] = categoria

    tipo_id = str(request.POST.get("accion_tipo") or "").strip()
    if tipo_id:
        tipo = (
            TipoProducto.objects
            .filter(pk=tipo_id, activo=True)
            .first()
        )
        if not tipo:
            errores.append("El tipo seleccionado no es válido.")
        else:
            acciones["tipo"] = tipo

    margen_modo = str(request.POST.get("margen_modo") or "").strip()
    margen_valor = _decimal(request.POST.get("margen_valor"))
    if margen_modo:
        if margen_modo not in {"FIJAR", "AJUSTAR"}:
            errores.append("La acción de margen no es válida.")
        elif margen_valor is None:
            errores.append("Ingresá un valor de margen válido.")
        else:
            acciones["margen_modo"] = margen_modo
            acciones["margen_valor"] = margen_valor

    if not acciones:
        errores.append("Elegí al menos un cambio para previsualizar.")

    return acciones, errores


def _texto_booleano(valor):
    return "Sí" if valor else "No"


def _cambios_para_producto(producto, acciones):
    cambios = []
    nuevos = {}
    errores = []

    for campo, (etiqueta, _) in BOOLEAN_FIELDS.items():
        if campo not in acciones:
            continue

        nuevo = bool(acciones[campo])
        actual = bool(getattr(producto, campo))

        if campo == "requiere_impresion" and nuevo and not actual:
            if producto.es_compuesto:
                valido = producto.horas_totales > 0 and producto.peso_gramos > 0
            else:
                valido = (
                    (int(producto.horas or 0) > 0 or int(producto.minutos or 0) > 0)
                    and Decimal(str(producto.peso_gramos or 0)) > 0
                )
            if not valido:
                errores.append(
                    "No se puede activar impresión: falta tiempo o peso."
                )
                continue

        if actual != nuevo:
            cambios.append(
                {
                    "campo": etiqueta,
                    "antes": _texto_booleano(actual),
                    "despues": _texto_booleano(nuevo),
                }
            )
            nuevos[campo] = nuevo

    if "categoria" in acciones:
        nuevo = acciones["categoria"]
        if producto.categoria != nuevo:
            etiquetas = dict(Producto.CATEGORIAS)
            cambios.append(
                {
                    "campo": "Categoría",
                    "antes": etiquetas.get(producto.categoria, producto.categoria),
                    "despues": etiquetas.get(nuevo, nuevo),
                }
            )
            nuevos["categoria"] = nuevo

    if "tipo" in acciones:
        tipo = acciones["tipo"]
        if producto.tipo_id != tipo.id:
            cambios.append(
                {
                    "campo": "Tipo",
                    "antes": producto.tipo.nombre,
                    "despues": tipo.nombre,
                }
            )
            nuevos["tipo"] = tipo

    if "margen_modo" in acciones:
        actual = Decimal(str(producto.margen_ganancia or 0))
        valor = acciones["margen_valor"]
        nuevo = (
            valor
            if acciones["margen_modo"] == "FIJAR"
            else actual + valor
        )
        if nuevo < 0 or nuevo >= 100:
            errores.append(
                f"El margen resultante ({nuevo}%) debe quedar entre 0% y 99,99%."
            )
        elif nuevo != actual:
            nuevo = nuevo.quantize(Decimal("0.01"))
            cambios.append(
                {
                    "campo": "Margen",
                    "antes": f"{actual.normalize()}%",
                    "despues": f"{nuevo.normalize()}%",
                }
            )
            nuevos["margen_ganancia"] = nuevo

    return cambios, nuevos, errores


def _ids_seleccionados(request, filtrados):
    if request.POST.get("seleccionar_todos_resultados") == "1":
        return list(filtrados.values_list("id", flat=True))

    ids = []
    for valor in request.POST.getlist("producto_ids"):
        try:
            ids.append(int(valor))
        except (TypeError, ValueError):
            continue

    if not ids:
        return []

    permitidos = set(
        filtrados
        .filter(id__in=ids)
        .values_list("id", flat=True)
    )
    return [item for item in ids if item in permitidos]


def modificacion_masiva(request):
    filtros = request.POST if request.method == "POST" else request.GET
    productos_filtrados = _filtrar_productos(filtros)
    total_resultados = productos_filtrados.count()
    tipos = TipoProducto.objects.filter(activo=True).order_by("nombre")

    preview = None
    if request.method == "POST":
        ids = _ids_seleccionados(request, productos_filtrados)
        acciones, errores = _leer_acciones(request)

        if not ids:
            errores.append("Seleccioná al menos un producto.")

        productos = list(
            Producto.objects
            .filter(id__in=ids, solo_produccion=False)
            .select_related("tipo")
            .order_by("nombre", "id")
        )

        filas = []
        errores_filas = []
        total_cambios = 0

        if not errores:
            for producto in productos:
                cambios, nuevos, errores_producto = _cambios_para_producto(
                    producto,
                    acciones,
                )
                if errores_producto:
                    errores_filas.append(
                        {
                            "producto": producto,
                            "errores": errores_producto,
                        }
                    )
                filas.append(
                    {
                        "producto": producto,
                        "cambios": cambios,
                        "nuevos": nuevos,
                    }
                )
                if cambios:
                    total_cambios += 1

        if request.POST.get("accion") == "aplicar":
            if errores or errores_filas:
                for error in errores:
                    messages.error(request, error)
                for fila in errores_filas[:5]:
                    messages.error(
                        request,
                        f"{fila['producto'].codigo}: {fila['errores'][0]}",
                    )
            elif total_cambios <= 0:
                messages.info(
                    request,
                    "Los productos seleccionados ya tienen esos valores.",
                )
            else:
                with transaction.atomic():
                    modificados = 0
                    for fila in filas:
                        if not fila["nuevos"]:
                            continue
                        producto = fila["producto"]
                        update_fields = []
                        for campo, valor in fila["nuevos"].items():
                            setattr(producto, campo, valor)
                            update_fields.append(campo)
                        producto.save(update_fields=update_fields)
                        modificados += 1

                messages.success(
                    request,
                    f"Se actualizaron {modificados} producto"
                    f"{'s' if modificados != 1 else ''}.",
                )
                return redirect("productos:modificacion_masiva")

        preview = {
            "ids": ids,
            "filas": filas,
            "errores": errores,
            "errores_filas": errores_filas,
            "total_seleccionados": len(ids),
            "total_cambios": total_cambios,
            "puede_aplicar": (
                not errores
                and not errores_filas
                and total_cambios > 0
            ),
        }

    return render(
        request,
        "productos/modificacion_masiva.html",
        {
            "productos": list(productos_filtrados),
            "tipos": tipos,
            "categorias": Producto.CATEGORIAS,
            "total_resultados": total_resultados,
            "preview": preview,
            "filtros": {
                "q": str(filtros.get("q") or ""),
                "tipo": str(filtros.get("tipo") or ""),
                "categoria": str(filtros.get("categoria") or ""),
                "f_activo": str(filtros.get("f_activo") or ""),
                "f_color": str(filtros.get("f_color") or ""),
                "f_personalizable": str(
                    filtros.get("f_personalizable") or ""
                ),
            },
        },
    )
