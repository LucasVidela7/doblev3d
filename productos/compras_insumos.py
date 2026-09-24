from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from pedidos.finanzas_services import crear_cuotas_gasto
from pedidos.models import Gasto

from .models import CompraInsumo, CompraInsumoItem, Insumo


def _decimal(valor, default=None):
    texto = str(valor or "").strip().replace(",", ".")
    if not texto:
        return default
    try:
        return Decimal(texto)
    except (InvalidOperation, TypeError, ValueError):
        return default


def _contexto(request, valores=None, errores=None):
    preseleccion = (
        request.GET.get("insumo")
        or (valores or {}).get("insumo_preseleccion")
        or ""
    )
    origen = (
        request.GET.get("origen")
        or (valores or {}).get("origen")
        or "insumos"
    )
    compras = (
        CompraInsumo.objects
        .select_related("gasto")
        .prefetch_related("items__insumo")
        .order_by("-fecha_compra", "-id")
    )
    return {
        "insumos": Insumo.objects.filter(
            activo=True,
        ).order_by("tipo_uso", "nombre"),
        "compras_pagina": Paginator(
            compras,
            20,
        ).get_page(request.GET.get("page")),
        "medios_pago": Gasto.MEDIOS_PAGO,
        "hoy": timezone.localdate(),
        "preseleccion": str(preseleccion),
        "origen": origen,
        "valores": valores or {},
        "errores": errores or [],
    }


def lista_compras(request):
    return render(
        request,
        "productos/compras_insumos.html",
        _contexto(request),
    )


@transaction.atomic
def registrar_compra(request):
    if request.method != "POST":
        return redirect("productos:compras_insumos")

    errores = []
    fecha_texto = (request.POST.get("fecha_compra") or "").strip()
    proveedor = (request.POST.get("proveedor") or "").strip()[:160]
    medio_pago = (
        request.POST.get("medio_pago") or "TRANSFERENCIA"
    ).strip().upper()
    cuotas_texto = (request.POST.get("cantidad_cuotas") or "1").strip()
    primera_cuota_texto = (
        request.POST.get("fecha_primera_cuota") or ""
    ).strip()
    observaciones = (request.POST.get("observaciones") or "").strip()
    origen = (request.POST.get("origen") or "insumos").strip()

    try:
        fecha_compra = date.fromisoformat(fecha_texto)
    except (TypeError, ValueError):
        fecha_compra = None
        errores.append("La fecha de compra no es válida.")

    if medio_pago not in {valor for valor, _ in Gasto.MEDIOS_PAGO}:
        medio_pago = "OTRO"

    try:
        cantidad_cuotas = max(
            min(int(cuotas_texto or 1), 36),
            1,
        )
    except (TypeError, ValueError):
        cantidad_cuotas = 1

    fecha_primera_cuota = None
    if medio_pago == "TARJETA_CREDITO":
        if not primera_cuota_texto:
            errores.append(
                "Indicá el vencimiento de la primera cuota."
            )
        else:
            try:
                fecha_primera_cuota = date.fromisoformat(
                    primera_cuota_texto
                )
            except (TypeError, ValueError):
                errores.append(
                    "El vencimiento de la primera cuota no es válido."
                )
    else:
        cantidad_cuotas = 1

    ids = request.POST.getlist("insumo_id")
    cantidades = request.POST.getlist("cantidad")
    montos = request.POST.getlist("monto_linea")

    lineas = []
    ids_vistos = set()
    max_len = max(len(ids), len(cantidades), len(montos), 0)

    for indice in range(max_len):
        insumo_id = ids[indice].strip() if indice < len(ids) else ""
        cantidad = _decimal(
            cantidades[indice] if indice < len(cantidades) else ""
        )
        monto = _decimal(
            montos[indice] if indice < len(montos) else ""
        )

        if not insumo_id and cantidad is None and monto is None:
            continue
        if not insumo_id:
            errores.append(
                f"Seleccioná el insumo de la línea {indice + 1}."
            )
            continue
        if insumo_id in ids_vistos:
            errores.append(
                "Un mismo insumo no puede repetirse en la misma compra."
            )
            continue
        ids_vistos.add(insumo_id)

        try:
            insumo_pk = int(insumo_id)
        except (TypeError, ValueError):
            errores.append("Hay un insumo inválido en la compra.")
            continue

        if cantidad is None or cantidad <= 0:
            errores.append(
                f"La cantidad de la línea {indice + 1} debe ser mayor a cero."
            )
            continue
        if monto is None or monto <= 0:
            errores.append(
                f"El importe de la línea {indice + 1} debe ser mayor a cero."
            )
            continue

        lineas.append(
            {
                "insumo_id": insumo_pk,
                "cantidad": cantidad.quantize(Decimal("0.001")),
                "monto": monto.quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                ),
            }
        )

    if not lineas:
        errores.append("Agregá al menos un insumo a la compra.")

    valores = {
        "fecha_compra": fecha_texto,
        "proveedor": proveedor,
        "medio_pago": medio_pago,
        "cantidad_cuotas": cantidad_cuotas,
        "fecha_primera_cuota": primera_cuota_texto,
        "observaciones": observaciones,
        "origen": origen,
    }

    if errores:
        for error in errores:
            messages.error(request, error)
        return render(
            request,
            "productos/compras_insumos.html",
            _contexto(
                request,
                valores=valores,
                errores=errores,
            ),
            status=400,
        )

    ids_linea = [item["insumo_id"] for item in lineas]
    insumos_bloqueados = {
        insumo.id: insumo
        for insumo in (
            Insumo.objects
            .select_for_update()
            .filter(
                id__in=ids_linea,
                activo=True,
            )
        )
    }
    if len(insumos_bloqueados) != len(ids_linea):
        messages.error(
            request,
            "Uno de los insumos ya no está disponible.",
        )
        return redirect("productos:compras_insumos")

    monto_total = sum(
        (item["monto"] for item in lineas),
        Decimal("0"),
    ).quantize(Decimal("0.01"))

    todos_empaque = all(
        insumos_bloqueados[item["insumo_id"]].tipo_uso == "EMPAQUE"
        for item in lineas
    )
    categoria = "EMBALAJE" if todos_empaque else "INSUMOS"

    if len(lineas) == 1:
        nombre = insumos_bloqueados[
            lineas[0]["insumo_id"]
        ].nombre
        descripcion = f"Compra de {nombre}"
    else:
        descripcion = f"Compra de insumos · {len(lineas)} ítems"
    if proveedor:
        descripcion = f"{descripcion} · {proveedor}"
    descripcion = descripcion[:200]

    gasto = Gasto.objects.create(
        fecha_compra=fecha_compra,
        tipo="OPERATIVO",
        categoria=categoria,
        descripcion=descripcion,
        monto_total=monto_total,
        medio_pago=medio_pago,
        cantidad_cuotas=cantidad_cuotas,
        fecha_primera_cuota=fecha_primera_cuota,
        observaciones=observaciones,
    )
    crear_cuotas_gasto(gasto)

    compra = CompraInsumo.objects.create(
        fecha_compra=fecha_compra,
        proveedor=proveedor,
        gasto=gasto,
        observaciones=observaciones,
    )

    for linea in lineas:
        insumo = insumos_bloqueados[linea["insumo_id"]]
        cantidad = linea["cantidad"]
        monto = linea["monto"]

        stock_anterior = max(
            Decimal(str(insumo.stock or 0)),
            Decimal("0"),
        )
        costo_anterior = max(
            Decimal(str(insumo.costo_unitario or 0)),
            Decimal("0"),
        )
        costo_compra = (
            monto / cantidad
        ).quantize(Decimal("0.0001"))

        stock_nuevo = stock_anterior + cantidad
        valor_stock_anterior = stock_anterior * costo_anterior
        costo_promedio_nuevo = (
            (valor_stock_anterior + monto)
            / stock_nuevo
        ).quantize(Decimal("0.0001"))

        CompraInsumoItem.objects.create(
            compra=compra,
            insumo=insumo,
            cantidad=cantidad,
            monto_total=monto,
            costo_unitario_compra=costo_compra,
            stock_anterior=stock_anterior,
            costo_promedio_anterior=costo_anterior,
            costo_promedio_nuevo=costo_promedio_nuevo,
        )

        insumo.stock = stock_nuevo
        insumo.precio_compra = monto
        insumo.cantidad_compra = cantidad
        insumo.costo_promedio_unitario = costo_promedio_nuevo
        insumo.precio_actualizado_en = timezone.now()
        if proveedor:
            insumo.proveedor = proveedor
        insumo.save(
            update_fields=[
                "stock",
                "precio_compra",
                "cantidad_compra",
                "costo_promedio_unitario",
                "precio_actualizado_en",
                "proveedor",
                "actualizado_en",
            ]
        )

    messages.success(
        request,
        (
            f"Compra {compra.codigo} registrada por "
            f"ARS {monto_total:,.2f}. Stock y Finanzas actualizados."
        ),
    )

    if origen == "finanzas":
        periodo = fecha_compra.strftime("%Y-%m")
        return redirect(
            f"{reverse('pedidos:finanzas')}"
            f"?periodo={periodo}&vista=gastos"
        )

    return redirect("productos:compras_insumos")
