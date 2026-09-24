from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import ConfiguracionCatalogo, Insumo, ProductoInsumo


def _decimal(valor, default=None):
    if valor is None:
        return default
    texto = str(valor).strip().replace(".", "").replace(",", ".") if "," in str(valor) else str(valor).strip()
    if not texto:
        return default
    try:
        return Decimal(texto)
    except (InvalidOperation, TypeError, ValueError):
        return default


def _opciones(choices):
    return [{"valor": valor, "nombre": nombre} for valor, nombre in choices]


def lista(request):
    busqueda = (request.GET.get("q") or "").strip()
    tipo = (request.GET.get("tipo") or "").strip().upper()
    estado = (request.GET.get("estado") or "activos").strip().lower()

    qs = Insumo.objects.annotate(
        productos_asignados_count=Count(
            "productos_asignados",
            distinct=True,
        )
    )

    if busqueda:
        qs = qs.filter(
            Q(nombre__icontains=busqueda)
            | Q(proveedor__icontains=busqueda)
        )

    tipos_validos = {valor for valor, _ in Insumo.TIPOS_USO}
    if tipo in tipos_validos:
        qs = qs.filter(tipo_uso=tipo)
    else:
        tipo = ""

    if estado == "activos":
        qs = qs.filter(activo=True)
    elif estado == "inactivos":
        qs = qs.filter(activo=False)
    elif estado != "todos":
        estado = "activos"
        qs = qs.filter(activo=True)

    todos = Insumo.objects.all()
    metricas = {
        "total": todos.count(),
        "activos": todos.filter(activo=True).count(),
        "producto": todos.filter(activo=True, tipo_uso="PRODUCTO").count(),
        "empaque": todos.filter(activo=True, tipo_uso="EMPAQUE").count(),
        "despacho": todos.filter(activo=True, tipo_uso="DESPACHO").count(),
    }
    config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)

    return render(
        request,
        "productos/insumos_lista.html",
        {
            "insumos": qs.order_by("-activo", "tipo_uso", "nombre"),
            "busqueda": busqueda,
            "tipo_seleccionado": tipo,
            "estado_seleccionado": estado,
            "tipos_uso": _opciones(Insumo.TIPOS_USO),
            "metricas": metricas,
            "incremento_general": config.incremento_insumos_por_defecto,
        },
    )


def _contexto_formulario(insumo=None, errores=None, valores=None):
    config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
    return {
        "insumo": insumo,
        "errores": errores or [],
        "valores": valores or {},
        "tipos_uso": _opciones(Insumo.TIPOS_USO),
        "unidades_medida": _opciones(Insumo.UNIDADES_MEDIDA),
        "incremento_general": config.incremento_insumos_por_defecto,
    }


def _leer_post(request, insumo=None):
    errores = []
    valores = {
        "nombre": (request.POST.get("nombre") or "").strip()[:160],
        "tipo_uso": (request.POST.get("tipo_uso") or "PRODUCTO").strip().upper(),
        "unidad_medida": (request.POST.get("unidad_medida") or "UNIDAD").strip().upper(),
        "precio_compra": (request.POST.get("precio_compra") or "").strip(),
        "cantidad_compra": (request.POST.get("cantidad_compra") or "").strip(),
        "stock": (request.POST.get("stock") or "").strip(),
        "proveedor": (request.POST.get("proveedor") or "").strip()[:160],
        "url_referencia": (request.POST.get("url_referencia") or "").strip()[:500],
        "incremento_personalizado": (request.POST.get("incremento_personalizado") or "").strip(),
        "disponible_como_complementario": (
            request.POST.get("disponible_como_complementario") == "on"
        ),
        "activo": request.POST.get("activo") == "on",
    }

    if not valores["nombre"]:
        errores.append("Ingresá un nombre para el insumo.")

    tipos_validos = {valor for valor, _ in Insumo.TIPOS_USO}
    if valores["tipo_uso"] not in tipos_validos:
        errores.append("Seleccioná un tipo de uso válido.")

    unidades_validas = {valor for valor, _ in Insumo.UNIDADES_MEDIDA}
    if valores["unidad_medida"] not in unidades_validas:
        errores.append("Seleccioná una unidad de medida válida.")

    precio = _decimal(valores["precio_compra"])
    cantidad = _decimal(valores["cantidad_compra"])
    stock = _decimal(valores["stock"], Decimal("0"))
    incremento = (
        _decimal(valores["incremento_personalizado"])
        if valores["incremento_personalizado"]
        else None
    )

    if precio is None or precio < 0:
        errores.append("El precio de compra debe ser un número igual o mayor a 0.")
    if cantidad is None or cantidad <= 0:
        errores.append("La cantidad de compra debe ser mayor a 0.")
    if stock is None or stock < 0:
        errores.append("El stock debe ser un número igual o mayor a 0.")
    if incremento is not None and incremento < 0:
        errores.append("El incremento particular no puede ser negativo.")

    if valores["url_referencia"]:
        try:
            URLValidator()(valores["url_referencia"])
        except ValidationError:
            errores.append("La URL de referencia no es válida.")

    if (
        insumo
        and insumo.pk
        and insumo.tipo_uso == "PRODUCTO"
        and valores["tipo_uso"] != "PRODUCTO"
        and ProductoInsumo.objects.filter(insumo=insumo).exists()
    ):
        errores.append(
            "Este insumo está asignado a productos. Quitá esas asignaciones "
            "antes de cambiarlo a Empaque o Despacho."
        )

    if (
        insumo
        and insumo.pk
        and insumo.tipo_uso == "EMPAQUE"
        and valores["tipo_uso"] != "EMPAQUE"
        and (
            getattr(insumo, "reglas_empaque", None)
            and insumo.reglas_empaque.exists()
            or getattr(insumo, "reglas_empaque_complementarias", None)
            and insumo.reglas_empaque_complementarias.exists()
            or getattr(insumo, "usos_empaque", None)
            and insumo.usos_empaque.exists()
            or getattr(insumo, "usos_empaque_complementarios", None)
            and insumo.usos_empaque_complementarios.exists()
        )
    ):
        errores.append(
            "Este insumo está usado como empaque principal o complementario en reglas/pedidos. "
            "Quitá esas relaciones antes de cambiar su tipo."
        )

    duplicado = Insumo.objects.filter(nombre__iexact=valores["nombre"])
    if insumo and insumo.pk:
        duplicado = duplicado.exclude(pk=insumo.pk)
    if valores["nombre"] and duplicado.exists():
        errores.append("Ya existe un insumo con ese nombre.")

    if valores["tipo_uso"] != "EMPAQUE":
        valores["disponible_como_complementario"] = False

    datos = {
        "nombre": valores["nombre"],
        "tipo_uso": valores["tipo_uso"],
        "unidad_medida": valores["unidad_medida"],
        "precio_compra": precio if precio is not None else Decimal("0"),
        "cantidad_compra": cantidad if cantidad is not None else Decimal("1"),
        "stock": stock if stock is not None else Decimal("0"),
        "proveedor": valores["proveedor"],
        "url_referencia": valores["url_referencia"],
        "incremento_personalizado": incremento,
        "disponible_como_complementario": (
            valores["disponible_como_complementario"]
        ),
        "activo": valores["activo"],
    }
    return datos, valores, errores


def nuevo(request):
    if request.method == "POST":
        datos, valores, errores = _leer_post(request)
        if not errores:
            cantidad_base = Decimal(str(datos["cantidad_compra"] or 0))
            datos["costo_promedio_unitario"] = (
                Decimal(str(datos["precio_compra"] or 0))
                / cantidad_base
                if cantidad_base > 0
                else Decimal("0")
            )
            insumo = Insumo.objects.create(**datos)
            messages.success(
                request,
                f"Insumo {insumo.nombre} creado correctamente.",
            )
            return redirect("productos:insumos")
        return render(
            request,
            "productos/insumo_formulario.html",
            _contexto_formulario(errores=errores, valores=valores),
        )

    return render(
        request,
        "productos/insumo_formulario.html",
        _contexto_formulario(),
    )


def editar(request, insumo_id):
    insumo = get_object_or_404(Insumo, id=insumo_id)

    if request.method == "POST":
        datos, valores, errores = _leer_post(request, insumo=insumo)
        if not errores:
            cambio_precio = (
                Decimal(str(insumo.precio_compra or 0)) != datos["precio_compra"]
                or Decimal(str(insumo.cantidad_compra or 0)) != datos["cantidad_compra"]
            )
            for campo, valor in datos.items():
                setattr(insumo, campo, valor)
            if cambio_precio:
                cantidad_base = Decimal(
                    str(datos["cantidad_compra"] or 0)
                )
                insumo.costo_promedio_unitario = (
                    Decimal(str(datos["precio_compra"] or 0))
                    / cantidad_base
                    if cantidad_base > 0
                    else Decimal("0")
                )
                insumo.precio_actualizado_en = timezone.now()
            insumo.save()
            messages.success(
                request,
                f"Insumo {insumo.nombre} actualizado.",
            )
            return redirect("productos:insumos")

        return render(
            request,
            "productos/insumo_formulario.html",
            _contexto_formulario(
                insumo=insumo,
                errores=errores,
                valores=valores,
            ),
        )

    valores = {
        "nombre": insumo.nombre,
        "tipo_uso": insumo.tipo_uso,
        "unidad_medida": insumo.unidad_medida,
        "precio_compra": insumo.precio_compra,
        "cantidad_compra": insumo.cantidad_compra,
        "stock": insumo.stock,
        "proveedor": insumo.proveedor,
        "url_referencia": insumo.url_referencia,
        "incremento_personalizado": (
            insumo.incremento_personalizado
            if insumo.incremento_personalizado is not None
            else ""
        ),
        "disponible_como_complementario": (
            insumo.disponible_como_complementario
        ),
        "activo": insumo.activo,
    }
    return render(
        request,
        "productos/insumo_formulario.html",
        _contexto_formulario(insumo=insumo, valores=valores),
    )


@require_POST
def cambiar_activo(request, insumo_id):
    insumo = get_object_or_404(Insumo, id=insumo_id)
    insumo.activo = not insumo.activo
    insumo.save(update_fields=["activo", "actualizado_en"])
    messages.success(
        request,
        f"{insumo.nombre}: {'activado' if insumo.activo else 'desactivado'}.",
    )
    return redirect("productos:insumos")
