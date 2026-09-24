from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from kits.models import Kit
from productos.models import Insumo, Producto

from .models import Pedido, PedidoEmpaque, ReglaEmpaque


def _decimal(valor, default=None):
    try:
        if valor is None or str(valor).strip() == "":
            return default
        return Decimal(str(valor).strip().replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return default


def insumos_empaque_disponibles():
    return list(
        Insumo.objects
        .filter(tipo_uso="EMPAQUE", activo=True)
        .order_by("nombre")
    )


def _regla_aplica_rango(regla, unidades):
    unidades = max(int(unidades or 0), 0)
    if unidades < int(regla.desde_unidades or 1):
        return False
    if (
        regla.hasta_unidades is not None
        and unidades > int(regla.hasta_unidades)
    ):
        return False
    return True


def sugerir_regla_empaque(unidades, *, kit=None, producto=None):
    reglas = list(
        ReglaEmpaque.objects
        .filter(
            activo=True,
            insumo__activo=True,
            insumo__tipo_uso="EMPAQUE",
        )
        .select_related("insumo", "kit", "producto")
    )

    candidatos = []
    for regla in reglas:
        if not _regla_aplica_rango(regla, unidades):
            continue

        if regla.alcance == "KIT":
            if not kit or regla.kit_id != kit.id:
                continue
            rango = 0
        elif regla.alcance == "PRODUCTO":
            if not producto or regla.producto_id != producto.id:
                continue
            rango = 0
        elif regla.alcance == "GENERAL":
            rango = 1
        else:
            continue

        amplitud = (
            (regla.hasta_unidades - regla.desde_unidades)
            if regla.hasta_unidades is not None
            else 999999
        )
        candidatos.append(
            (
                rango,
                int(regla.prioridad or 100),
                amplitud,
                regla.id,
                regla,
            )
        )

    if not candidatos:
        return None

    candidatos.sort(key=lambda item: item[:4])
    return candidatos[0][4]


def _unidades_paquete(paquete):
    return sum(
        int(item.get("cantidad") or 0)
        for item in paquete.get("productos", [])
    )


def enriquecer_empaques_pedido(pedido, paquetes, productos_sueltos):
    usos = {
        uso.clave_paquete: uso
        for uso in pedido.empaques_usados.select_related("insumo").all()
    }
    opciones = insumos_empaque_disponibles()

    for paquete in paquetes:
        paquete["unidades_contenido"] = _unidades_paquete(paquete)
        regla = sugerir_regla_empaque(
            paquete["unidades_contenido"],
            kit=paquete.get("kit"),
        )
        paquete["regla_empaque"] = regla
        paquete["empaque_sugerido"] = regla.insumo if regla else None
        paquete["cantidad_empaque_sugerida"] = (
            regla.cantidad_insumo if regla else Decimal("1")
        )
        paquete["empaque_usado"] = usos.get(paquete["clave"])
        paquete["opciones_empaque"] = opciones

    paquete_sueltos = None
    if productos_sueltos:
        unidades = sum(
            int(item.get("cantidad") or 0)
            for item in productos_sueltos
        )
        ids = {
            item["producto"].id
            for item in productos_sueltos
            if item.get("producto")
        }
        producto_unico = None
        if len(ids) == 1:
            producto_unico = next(
                (
                    item["producto"]
                    for item in productos_sueltos
                    if item.get("producto")
                ),
                None,
            )

        regla = sugerir_regla_empaque(
            unidades,
            producto=producto_unico,
        )
        paquete_sueltos = {
            "clave": "sueltos",
            "descripcion": "Productos fuera de kits",
            "unidades_contenido": unidades,
            "productos": productos_sueltos,
            "regla_empaque": regla,
            "empaque_sugerido": regla.insumo if regla else None,
            "cantidad_empaque_sugerida": (
                regla.cantidad_insumo if regla else Decimal("1")
            ),
            "empaque_usado": usos.get("sueltos"),
            "opciones_empaque": opciones,
        }

    return paquetes, paquete_sueltos


def _paquetes_validos(pedido):
    from .detalle_views import _armar_paquetes_detalle, _armar_preparacion

    preparacion = _armar_preparacion(pedido)
    paquetes, sueltos = _armar_paquetes_detalle(
        pedido,
        preparacion,
    )
    paquetes, paquete_sueltos = enriquecer_empaques_pedido(
        pedido,
        paquetes,
        sueltos,
    )
    resultado = {paquete["clave"]: paquete for paquete in paquetes}
    if paquete_sueltos:
        resultado["sueltos"] = paquete_sueltos
    return resultado


@transaction.atomic
@require_POST
def usar_empaque(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects.select_for_update(),
        id=pedido_id,
    )
    if pedido.estado in {"ENTREGADO", "CANCELADO"}:
        messages.error(
            request,
            "El empaque no puede modificarse en un pedido cerrado.",
        )
        return redirect("pedidos:detalle", pedido_id=pedido.id)

    clave = (request.POST.get("clave_paquete") or "").strip()
    paquetes = _paquetes_validos(pedido)
    paquete = paquetes.get(clave)
    if not paquete:
        messages.error(request, "No se pudo identificar el paquete.")
        return redirect("pedidos:detalle", pedido_id=pedido.id)

    insumo_id = (request.POST.get("insumo_id") or "").strip()
    cantidad = _decimal(request.POST.get("cantidad"), Decimal("1"))
    if cantidad is None or cantidad <= 0:
        messages.error(request, "La cantidad de empaque debe ser mayor a cero.")
        return redirect("pedidos:detalle", pedido_id=pedido.id)

    insumo = get_object_or_404(
        Insumo,
        id=insumo_id,
        activo=True,
        tipo_uso="EMPAQUE",
    )

    existente = (
        PedidoEmpaque.objects
        .select_for_update()
        .select_related("insumo")
        .filter(pedido=pedido, clave_paquete=clave)
        .first()
    )

    ids_bloqueo = {insumo.id}
    if existente:
        ids_bloqueo.add(existente.insumo_id)
    bloqueados = {
        item.id: item
        for item in Insumo.objects
        .select_for_update()
        .filter(id__in=ids_bloqueo)
    }

    nuevo = bloqueados[insumo.id]
    disponible = Decimal(str(nuevo.stock or 0))
    if existente and existente.insumo_id == nuevo.id:
        disponible += Decimal(str(existente.cantidad or 0))

    if disponible < cantidad:
        messages.error(
            request,
            (
                f"Stock insuficiente de {nuevo.nombre}: "
                f"necesitás {cantidad} y hay {disponible}."
            ),
        )
        return redirect("pedidos:detalle", pedido_id=pedido.id)

    if existente:
        anterior = bloqueados[existente.insumo_id]
        anterior.stock = (
            Decimal(str(anterior.stock or 0))
            + Decimal(str(existente.cantidad or 0))
        )
        anterior.save(update_fields=["stock"])

    nuevo = Insumo.objects.select_for_update().get(id=insumo.id)
    if Decimal(str(nuevo.stock or 0)) < cantidad:
        messages.error(
            request,
            "El stock cambió mientras preparabas el pedido. Volvé a intentar.",
        )
        return redirect("pedidos:detalle", pedido_id=pedido.id)

    nuevo.stock = Decimal(str(nuevo.stock or 0)) - cantidad
    nuevo.save(update_fields=["stock"])

    costo_unitario = Decimal(str(nuevo.costo_unitario_aplicado or 0))
    costo_total = costo_unitario * cantidad
    descripcion = (
        paquete.get("descripcion")
        or paquete.get("nombre_kit")
        or f"Paquete {paquete.get('numero', '')}"
    )

    PedidoEmpaque.objects.update_or_create(
        pedido=pedido,
        clave_paquete=clave,
        defaults={
            "descripcion": descripcion[:200],
            "unidades_contenido": int(
                paquete.get("unidades_contenido") or 0
            ),
            "insumo": nuevo,
            "cantidad": cantidad,
            "costo_unitario_snapshot": costo_unitario,
            "costo_total_snapshot": costo_total,
        },
    )

    messages.success(
        request,
        (
            f"Empaque registrado: {cantidad} × {nuevo.nombre}. "
            "El stock fue descontado."
        ),
    )
    return redirect("pedidos:detalle", pedido_id=pedido.id)


@transaction.atomic
@require_POST
def liberar_empaque(request, pedido_id):
    pedido = get_object_or_404(
        Pedido.objects.select_for_update(),
        id=pedido_id,
    )
    if pedido.estado in {"ENTREGADO", "CANCELADO"}:
        messages.error(
            request,
            "El empaque no puede modificarse en un pedido cerrado.",
        )
        return redirect("pedidos:detalle", pedido_id=pedido.id)

    clave = (request.POST.get("clave_paquete") or "").strip()
    uso = (
        PedidoEmpaque.objects
        .select_for_update()
        .filter(pedido=pedido, clave_paquete=clave)
        .first()
    )
    if not uso:
        messages.info(request, "Ese paquete no tenía empaque registrado.")
        return redirect("pedidos:detalle", pedido_id=pedido.id)

    insumo = Insumo.objects.select_for_update().get(id=uso.insumo_id)
    insumo.stock = (
        Decimal(str(insumo.stock or 0))
        + Decimal(str(uso.cantidad or 0))
    )
    insumo.save(update_fields=["stock"])
    nombre = insumo.nombre
    uso.delete()

    messages.success(
        request,
        f"Se liberó el empaque {nombre} y volvió al stock.",
    )
    return redirect("pedidos:detalle", pedido_id=pedido.id)


def reglas(request):
    editar_id = request.GET.get("editar")
    regla_editar = (
        ReglaEmpaque.objects
        .select_related("insumo", "kit", "producto")
        .filter(id=editar_id)
        .first()
        if editar_id
        else None
    )

    if request.method == "POST":
        regla_id = (request.POST.get("regla_id") or "").strip()
        regla = (
            get_object_or_404(ReglaEmpaque, id=regla_id)
            if regla_id
            else ReglaEmpaque()
        )
        errores = []

        nombre = (request.POST.get("nombre") or "").strip()
        alcance = (request.POST.get("alcance") or "GENERAL").strip().upper()
        insumo_id = (request.POST.get("insumo_id") or "").strip()
        desde = request.POST.get("desde_unidades") or "1"
        hasta = (request.POST.get("hasta_unidades") or "").strip()
        cantidad = _decimal(request.POST.get("cantidad_insumo"), Decimal("1"))
        prioridad = request.POST.get("prioridad") or "100"
        producto_id = (request.POST.get("producto_id") or "").strip()
        kit_id = (request.POST.get("kit_id") or "").strip()

        try:
            desde = max(int(desde), 1)
        except (TypeError, ValueError):
            desde = 1
            errores.append("La cantidad mínima no es válida.")

        if hasta:
            try:
                hasta = int(hasta)
            except (TypeError, ValueError):
                hasta = None
                errores.append("La cantidad máxima no es válida.")
        else:
            hasta = None

        if hasta is not None and hasta < desde:
            errores.append("La cantidad máxima no puede ser menor a la mínima.")

        try:
            prioridad = max(int(prioridad), 0)
        except (TypeError, ValueError):
            prioridad = 100

        insumo = Insumo.objects.filter(
            id=insumo_id,
            tipo_uso="EMPAQUE",
        ).first()
        if not insumo:
            errores.append("Seleccioná un insumo de tipo Empaque.")

        producto = None
        kit = None
        if alcance == "PRODUCTO":
            producto = Producto.objects.filter(id=producto_id).first()
            if not producto:
                errores.append("Seleccioná el producto específico.")
        elif alcance == "KIT":
            kit = Kit.objects.filter(id=kit_id).first()
            if not kit:
                errores.append("Seleccioná el kit específico.")
        elif alcance != "GENERAL":
            alcance = "GENERAL"

        if not nombre:
            errores.append("Ingresá un nombre para la regla.")
        if cantidad is None or cantidad <= 0:
            errores.append("La cantidad de empaque debe ser mayor a cero.")

        if errores:
            for error in errores:
                messages.error(request, error)
        else:
            regla.nombre = nombre
            regla.insumo = insumo
            regla.alcance = alcance
            regla.producto = producto
            regla.kit = kit
            regla.desde_unidades = desde
            regla.hasta_unidades = hasta
            regla.cantidad_insumo = cantidad
            regla.prioridad = prioridad
            regla.activo = request.POST.get("activo") == "on"
            regla.save()
            messages.success(request, "Regla de empaque guardada.")
            return redirect("pedidos:reglas_empaque")

    reglas_qs = (
        ReglaEmpaque.objects
        .select_related("insumo", "kit", "producto")
        .order_by("prioridad", "desde_unidades", "id")
    )
    return render(
        request,
        "pedidos/reglas_empaque.html",
        {
            "reglas": reglas_qs,
            "regla_editar": regla_editar,
            "insumos_empaque": Insumo.objects.filter(
                tipo_uso="EMPAQUE",
                activo=True,
            ).order_by("nombre"),
            "productos": Producto.objects.filter(
                activo=True,
                solo_produccion=False,
            ).order_by("nombre"),
            "kits": Kit.objects.filter(activo=True).order_by("nombre"),
            "alcances": ReglaEmpaque.ALCANCES,
        },
    )


@require_POST
def cambiar_regla_activo(request, regla_id):
    regla = get_object_or_404(ReglaEmpaque, id=regla_id)
    regla.activo = not regla.activo
    regla.save(update_fields=["activo", "actualizado_en"])
    messages.success(
        request,
        f"Regla {'activada' if regla.activo else 'desactivada'}.",
    )
    return redirect("pedidos:reglas_empaque")


@require_POST
def eliminar_regla(request, regla_id):
    regla = get_object_or_404(ReglaEmpaque, id=regla_id)
    regla.delete()
    messages.success(request, "Regla de empaque eliminada.")
    return redirect("pedidos:reglas_empaque")
