from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from kits.models import Kit
from productos.models import Insumo, Producto, TipoProducto

from .models import (
    Pedido,
    PedidoEmpaque,
    PedidoEmpaqueComplemento,
    ReglaEmpaque,
    ReglaEmpaqueComplemento,
)


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


def sugerir_regla_empaque(
    unidades,
    *,
    kit=None,
    producto=None,
    tipo_producto=None,
):
    reglas = list(
        ReglaEmpaque.objects
        .filter(
            activo=True,
            insumo__activo=True,
            insumo__tipo_uso="EMPAQUE",
        )
        .select_related(
            "insumo",
            "kit",
            "producto",
            "tipo_producto",
        )
        .prefetch_related("complementos__insumo")
    )

    if tipo_producto is None and producto is not None:
        tipo_producto = getattr(producto, "tipo", None)

    candidatos = []
    for regla in reglas:
        if not _regla_aplica_rango(regla, unidades):
            continue

        if regla.alcance == "KIT":
            if not kit or regla.kit_id != kit.id:
                continue
            especificidad = 0
        elif regla.alcance == "PRODUCTO":
            if not producto or regla.producto_id != producto.id:
                continue
            especificidad = 0
        elif regla.alcance == "CATEGORIA":
            if (
                not tipo_producto
                or regla.tipo_producto_id != tipo_producto.id
            ):
                continue
            especificidad = 1
        elif regla.alcance == "GENERAL":
            especificidad = 2
        else:
            continue

        amplitud = (
            (regla.hasta_unidades - regla.desde_unidades)
            if regla.hasta_unidades is not None
            else 999999
        )
        candidatos.append(
            (
                especificidad,
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


def _insumos_estimados_regla(regla):
    if not regla:
        return []

    resultado = [
        {
            "insumo": regla.insumo,
            "cantidad": Decimal(str(regla.cantidad_insumo or 1)),
            "principal": True,
        }
    ]
    for complemento in regla.complementos.all():
        if not complemento.insumo.activo:
            continue
        resultado.append(
            {
                "insumo": complemento.insumo,
                "cantidad": Decimal(str(complemento.cantidad or 1)),
                "principal": False,
            }
        )

    for item in resultado:
        costo_unitario = Decimal(
            str(item["insumo"].costo_unitario_aplicado or 0)
        )
        item["costo_unitario"] = costo_unitario
        item["costo_total"] = costo_unitario * item["cantidad"]

    return resultado


def _detalle_estimado_regla(regla):
    insumos = _insumos_estimados_regla(regla)
    return {
        "regla": regla,
        "insumos": insumos,
        "costo_estimado": sum(
            (item["costo_total"] for item in insumos),
            Decimal("0"),
        ),
    }


def _componentes_item_kit(item):
    relacionados = getattr(item, "productos_kit", None)
    if relacionados is not None:
        componentes = list(relacionados.all())
        if componentes:
            return componentes, True

    kit = getattr(item, "kit", None)
    if kit and getattr(kit, "modalidad", "") == "FIJO":
        return list(kit.componentes.select_related("producto").all()), False

    return [], False


def _producto_de_componente(componente):
    return getattr(componente, "producto", None)


def _cantidad_de_componente(componente):
    return max(int(getattr(componente, "cantidad", 0) or 0), 0)


def _tipo_producto_comun(productos):
    productos_validos = [
        producto
        for producto in productos
        if producto is not None
        and getattr(producto, "tipo_id", None)
    ]
    ids_tipo = {
        producto.tipo_id
        for producto in productos_validos
    }
    if len(ids_tipo) != 1:
        return None
    return productos_validos[0].tipo


def _tipo_producto_kit(kit, componentes=None):
    if not kit:
        return None

    if getattr(kit, "tipo_producto_id", None):
        return kit.tipo_producto

    productos = []
    for componente in componentes or []:
        producto = _producto_de_componente(componente)
        if producto is not None:
            productos.append(producto)

    tipo = _tipo_producto_comun(productos)
    if tipo is not None:
        return tipo

    if getattr(kit, "modalidad", "") == "FIJO":
        productos_fijos = [
            componente.producto
            for componente in kit.componentes.select_related(
                "producto__tipo"
            ).all()
        ]
        return _tipo_producto_comun(productos_fijos)

    return None


def _tipo_producto_paquete(paquete):
    productos = [
        item.get("producto")
        for item in paquete.get("productos", [])
        if item.get("producto")
    ]
    tipo = _tipo_producto_comun(productos)
    if tipo is not None:
        return tipo
    return _tipo_producto_kit(paquete.get("kit"))


def estimar_embalaje_items(items):
    paquetes = []
    sueltos = []

    for item in items:
        tipo_item = getattr(item, "tipo_item", "")
        cantidad_linea = max(int(getattr(item, "cantidad", 0) or 0), 0)
        if cantidad_linea <= 0:
            continue

        if tipo_item == "KIT" and getattr(item, "kit", None):
            kit = item.kit
            componentes, cantidades_totales = _componentes_item_kit(item)
            tipo_producto_kit = _tipo_producto_kit(
                kit,
                componentes,
            )

            for unidad in range(cantidad_linea):
                unidades_contenido = 0
                for componente in componentes:
                    total = _cantidad_de_componente(componente)
                    if cantidades_totales:
                        base, resto = divmod(total, cantidad_linea)
                        cantidad_paquete = base + (
                            1 if unidad < resto else 0
                        )
                    else:
                        cantidad_paquete = total
                    unidades_contenido += cantidad_paquete

                if unidades_contenido <= 0:
                    unidades_contenido = max(
                        int(getattr(kit, "cantidad_productos", 0) or 0),
                        1,
                    )

                regla = sugerir_regla_empaque(
                    unidades_contenido,
                    kit=kit,
                    tipo_producto=tipo_producto_kit,
                )
                detalle = _detalle_estimado_regla(regla)
                descripcion = (
                    f"{kit.nombre} · kit {unidad + 1}/{cantidad_linea}"
                    if cantidad_linea > 1
                    else kit.nombre
                )
                paquetes.append(
                    {
                        "clave": (
                            f"kit-{getattr(item, 'id', 'x')}-{unidad + 1}"
                        ),
                        "descripcion": descripcion,
                        "unidades_contenido": unidades_contenido,
                        **detalle,
                    }
                )
            continue

        producto = getattr(item, "producto", None)
        if producto:
            sueltos.append(
                {
                    "producto": producto,
                    "cantidad": cantidad_linea,
                }
            )

    if sueltos:
        unidades = sum(item["cantidad"] for item in sueltos)
        ids_producto = {item["producto"].id for item in sueltos}
        ids_tipo = {
            item["producto"].tipo_id
            for item in sueltos
            if getattr(item["producto"], "tipo_id", None)
        }

        producto_unico = (
            sueltos[0]["producto"]
            if len(ids_producto) == 1
            else None
        )
        tipo_producto = (
            sueltos[0]["producto"].tipo
            if len(ids_tipo) == 1
            else None
        )

        regla = sugerir_regla_empaque(
            unidades,
            producto=producto_unico,
            tipo_producto=tipo_producto,
        )
        detalle = _detalle_estimado_regla(regla)
        paquetes.append(
            {
                "clave": "sueltos",
                "descripcion": "Productos fuera de kits",
                "unidades_contenido": unidades,
                **detalle,
            }
        )

    return {
        "paquetes": paquetes,
        "total": sum(
            (paquete["costo_estimado"] for paquete in paquetes),
            Decimal("0"),
        ),
        "tiene_reglas": any(paquete["regla"] for paquete in paquetes),
    }


def _costo_uso_completo(uso):
    return (
        Decimal(str(uso.costo_total_snapshot or 0))
        + sum(
            (
                Decimal(str(item.costo_total_snapshot or 0))
                for item in uso.complementos.all()
            ),
            Decimal("0"),
        )
    )


def costo_embalaje_para_rentabilidad(pedido):
    estimacion = estimar_embalaje_items(list(pedido.detalles.all()))
    estimados = {
        paquete["clave"]: paquete["costo_estimado"]
        for paquete in estimacion["paquetes"]
    }
    usos = {
        uso.clave_paquete: uso
        for uso in pedido.empaques_usados.all()
    }

    total = Decimal("0")
    usa_estimacion = False

    for clave, costo_estimado in estimados.items():
        uso = usos.pop(clave, None)
        if uso:
            total += _costo_uso_completo(uso)
        else:
            total += costo_estimado
            if costo_estimado > 0:
                usa_estimacion = True

    for uso in usos.values():
        total += _costo_uso_completo(uso)

    return total, usa_estimacion


def _unidades_paquete(paquete):
    return sum(
        int(item.get("cantidad") or 0)
        for item in paquete.get("productos", [])
    )


def _aplicar_estimacion_paquete(paquete, regla):
    detalle = _detalle_estimado_regla(regla)
    paquete["regla_empaque"] = regla
    paquete["empaque_sugerido"] = regla.insumo if regla else None
    paquete["cantidad_empaque_sugerida"] = (
        regla.cantidad_insumo if regla else Decimal("1")
    )
    paquete["complementos_sugeridos"] = [
        item
        for item in detalle["insumos"]
        if not item["principal"]
    ]
    paquete["costo_empaque_estimado"] = detalle["costo_estimado"]


def enriquecer_empaques_pedido(pedido, paquetes, productos_sueltos):
    usos = {
        uso.clave_paquete: uso
        for uso in pedido.empaques_usados
        .select_related("insumo")
        .prefetch_related("complementos__insumo")
        .all()
    }
    opciones = insumos_empaque_disponibles()

    for paquete in paquetes:
        paquete["unidades_contenido"] = _unidades_paquete(paquete)
        regla = sugerir_regla_empaque(
            paquete["unidades_contenido"],
            kit=paquete.get("kit"),
            tipo_producto=_tipo_producto_paquete(paquete),
        )
        _aplicar_estimacion_paquete(paquete, regla)
        paquete["empaque_usado"] = usos.get(paquete["clave"])
        paquete["costo_empaque_real"] = (
            _costo_uso_completo(paquete["empaque_usado"])
            if paquete["empaque_usado"]
            else Decimal("0")
        )
        paquete["opciones_empaque"] = opciones

    paquete_sueltos = None
    if productos_sueltos:
        unidades = sum(
            int(item.get("cantidad") or 0)
            for item in productos_sueltos
        )
        productos = [
            item["producto"]
            for item in productos_sueltos
            if item.get("producto")
        ]
        ids = {producto.id for producto in productos}
        ids_tipo = {
            producto.tipo_id
            for producto in productos
            if getattr(producto, "tipo_id", None)
        }
        producto_unico = productos[0] if len(ids) == 1 else None
        tipo_producto = productos[0].tipo if len(ids_tipo) == 1 else None

        regla = sugerir_regla_empaque(
            unidades,
            producto=producto_unico,
            tipo_producto=tipo_producto,
        )
        paquete_sueltos = {
            "clave": "sueltos",
            "descripcion": "Productos fuera de kits",
            "unidades_contenido": unidades,
            "productos": productos_sueltos,
            "empaque_usado": usos.get("sueltos"),
            "opciones_empaque": opciones,
        }
        paquete_sueltos["costo_empaque_real"] = (
            _costo_uso_completo(paquete_sueltos["empaque_usado"])
            if paquete_sueltos["empaque_usado"]
            else Decimal("0")
        )
        _aplicar_estimacion_paquete(paquete_sueltos, regla)

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


def _creditos_uso(uso):
    creditos = {}
    if not uso:
        return creditos

    creditos[uso.insumo_id] = (
        creditos.get(uso.insumo_id, Decimal("0"))
        + Decimal(str(uso.cantidad or 0))
    )
    for complemento in uso.complementos.all():
        creditos[complemento.insumo_id] = (
            creditos.get(complemento.insumo_id, Decimal("0"))
            + Decimal(str(complemento.cantidad or 0))
        )
    return creditos


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

    regla = paquete.get("regla_empaque")
    requeridos = {insumo.id: cantidad}
    complementos_requeridos = []
    if regla:
        for complemento in regla.complementos.select_related("insumo").all():
            if not complemento.insumo.activo:
                continue
            cantidad_comp = Decimal(str(complemento.cantidad or 0))
            if cantidad_comp <= 0:
                continue
            if complemento.insumo_id == insumo.id:
                messages.error(
                    request,
                    (
                        f"{complemento.insumo.nombre} está configurado como "
                        "empaque principal y complementario en la misma regla."
                    ),
                )
                return redirect("pedidos:detalle", pedido_id=pedido.id)
            requeridos[complemento.insumo_id] = (
                requeridos.get(complemento.insumo_id, Decimal("0"))
                + cantidad_comp
            )
            complementos_requeridos.append(
                (complemento.insumo_id, cantidad_comp)
            )

    existente = (
        PedidoEmpaque.objects
        .select_for_update()
        .select_related("insumo")
        .prefetch_related("complementos__insumo")
        .filter(pedido=pedido, clave_paquete=clave)
        .first()
    )
    creditos = _creditos_uso(existente)

    ids_bloqueo = set(requeridos) | set(creditos)
    bloqueados = {
        item.id: item
        for item in Insumo.objects
        .select_for_update()
        .filter(id__in=ids_bloqueo)
    }

    for requerido_id, requerido in requeridos.items():
        item = bloqueados[requerido_id]
        disponible = (
            Decimal(str(item.stock or 0))
            + creditos.get(requerido_id, Decimal("0"))
        )
        if disponible < requerido:
            messages.error(
                request,
                (
                    f"Stock insuficiente de {item.nombre}: "
                    f"necesitás {requerido} y hay {disponible}."
                ),
            )
            return redirect("pedidos:detalle", pedido_id=pedido.id)

    for item_id, credito in creditos.items():
        item = bloqueados[item_id]
        item.stock = Decimal(str(item.stock or 0)) + credito

    for item_id, requerido in requeridos.items():
        item = bloqueados[item_id]
        item.stock = Decimal(str(item.stock or 0)) - requerido

    for item in bloqueados.values():
        item.save(update_fields=["stock"])

    principal = bloqueados[insumo.id]
    costo_unitario = Decimal(str(principal.costo_unitario_aplicado or 0))
    costo_total = costo_unitario * cantidad
    descripcion = (
        paquete.get("descripcion")
        or paquete.get("nombre_kit")
        or f"Paquete {paquete.get('numero', '')}"
    )

    uso, _ = PedidoEmpaque.objects.update_or_create(
        pedido=pedido,
        clave_paquete=clave,
        defaults={
            "descripcion": descripcion[:200],
            "unidades_contenido": int(
                paquete.get("unidades_contenido") or 0
            ),
            "insumo": principal,
            "cantidad": cantidad,
            "costo_unitario_snapshot": costo_unitario,
            "costo_total_snapshot": costo_total,
        },
    )

    uso.complementos.all().delete()
    complementos_creados = []
    for complemento_id, cantidad_comp in complementos_requeridos:
        item = bloqueados[complemento_id]
        costo_comp = Decimal(str(item.costo_unitario_aplicado or 0))
        PedidoEmpaqueComplemento.objects.create(
            pedido_empaque=uso,
            insumo=item,
            cantidad=cantidad_comp,
            costo_unitario_snapshot=costo_comp,
            costo_total_snapshot=costo_comp * cantidad_comp,
        )
        complementos_creados.append(
            f"{cantidad_comp} × {item.nombre}"
        )

    detalle_complementos = (
        " + " + " + ".join(complementos_creados)
        if complementos_creados
        else ""
    )
    messages.success(
        request,
        (
            f"Empaque registrado: {cantidad} × {principal.nombre}"
            f"{detalle_complementos}. El stock fue descontado."
        ),
    )
    return redirect("pedidos:detalle", pedido_id=pedido.id)


def _restaurar_uso_empaque(uso):
    consumos = {
        uso.insumo_id: Decimal(str(uso.cantidad or 0))
    }
    for complemento in uso.complementos.all():
        consumos[complemento.insumo_id] = (
            consumos.get(complemento.insumo_id, Decimal("0"))
            + Decimal(str(complemento.cantidad or 0))
        )

    bloqueados = {
        item.id: item
        for item in Insumo.objects
        .select_for_update()
        .filter(id__in=consumos)
    }
    for item_id, cantidad in consumos.items():
        item = bloqueados[item_id]
        item.stock = Decimal(str(item.stock or 0)) + cantidad
        item.save(update_fields=["stock"])


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
        .select_related("insumo")
        .prefetch_related("complementos__insumo")
        .filter(pedido=pedido, clave_paquete=clave)
        .first()
    )
    if not uso:
        messages.info(request, "Ese paquete no tenía empaque registrado.")
        return redirect("pedidos:detalle", pedido_id=pedido.id)

    nombre = uso.insumo.nombre
    _restaurar_uso_empaque(uso)
    uso.delete()

    messages.success(
        request,
        f"Se liberó el empaque {nombre} y todos sus insumos volvieron al stock.",
    )
    return redirect("pedidos:detalle", pedido_id=pedido.id)


@transaction.atomic
def reglas(request):
    editar_id = request.GET.get("editar")
    regla_editar = (
        ReglaEmpaque.objects
        .select_related(
            "insumo",
            "kit",
            "producto",
            "tipo_producto",
        )
        .prefetch_related("complementos__insumo")
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
        tipo_producto_id = (
            request.POST.get("tipo_producto_id") or ""
        ).strip()

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
            activo=True,
        ).first()
        if not insumo:
            errores.append("Seleccioná un insumo de tipo Empaque.")

        producto = None
        kit = None
        tipo_producto = None
        if alcance == "PRODUCTO":
            producto = Producto.objects.filter(id=producto_id).first()
            if not producto:
                errores.append("Seleccioná el producto específico.")
        elif alcance == "KIT":
            kit = Kit.objects.filter(id=kit_id).first()
            if not kit:
                errores.append("Seleccioná el kit específico.")
        elif alcance == "CATEGORIA":
            tipo_producto = TipoProducto.objects.filter(
                id=tipo_producto_id,
                activo=True,
            ).first()
            if not tipo_producto:
                errores.append("Seleccioná la categoría de producto.")
        elif alcance != "GENERAL":
            alcance = "GENERAL"

        if not nombre:
            errores.append("Ingresá un nombre para la regla.")
        if cantidad is None or cantidad <= 0:
            errores.append("La cantidad de empaque debe ser mayor a cero.")

        complementos = []
        ids_vistos = set()
        for complemento_id in request.POST.getlist("complemento_id"):
            complemento_id = str(complemento_id or "").strip()
            if not complemento_id or complemento_id in ids_vistos:
                continue
            ids_vistos.add(complemento_id)
            complementos_actuales_ids = set(
                regla.complementos.values_list("insumo_id", flat=True)
            ) if regla.pk else set()
            complemento = (
                Insumo.objects
                .filter(
                    id=complemento_id,
                    tipo_uso="EMPAQUE",
                    activo=True,
                )
                .filter(
                    Q(disponible_como_complementario=True)
                    | Q(id__in=complementos_actuales_ids)
                )
                .first()
            )
            if not complemento:
                errores.append(
                    "Ese insumo no está habilitado como complementario."
                )
                continue
            if insumo and complemento.id == insumo.id:
                errores.append(
                    "El empaque principal no puede repetirse como complementario."
                )
                continue
            cantidad_comp = _decimal(
                request.POST.get(
                    f"complemento_cantidad_{complemento.id}"
                ),
                Decimal("1"),
            )
            if cantidad_comp is None or cantidad_comp <= 0:
                errores.append(
                    f"La cantidad de {complemento.nombre} debe ser mayor a cero."
                )
                continue
            complementos.append((complemento, cantidad_comp))

        if errores:
            for error in errores:
                messages.error(request, error)
        else:
            regla.nombre = nombre
            regla.insumo = insumo
            regla.alcance = alcance
            regla.producto = producto
            regla.kit = kit
            regla.tipo_producto = tipo_producto
            regla.desde_unidades = desde
            regla.hasta_unidades = hasta
            regla.cantidad_insumo = cantidad
            regla.prioridad = prioridad
            regla.activo = request.POST.get("activo") == "on"
            regla.save()

            regla.complementos.all().delete()
            ReglaEmpaqueComplemento.objects.bulk_create(
                [
                    ReglaEmpaqueComplemento(
                        regla=regla,
                        insumo=item,
                        cantidad=cantidad_item,
                    )
                    for item, cantidad_item in complementos
                ]
            )

            messages.success(request, "Regla de empaque guardada.")
            return redirect("pedidos:reglas_empaque")

    reglas_qs = (
        ReglaEmpaque.objects
        .select_related(
            "insumo",
            "kit",
            "producto",
            "tipo_producto",
        )
        .prefetch_related("complementos__insumo")
        .order_by("prioridad", "desde_unidades", "id")
    )
    insumos_form = list(
        Insumo.objects.filter(
            tipo_uso="EMPAQUE",
            activo=True,
        ).order_by("nombre")
    )
    complementos_edicion = {
        item.insumo_id: item.cantidad
        for item in (
            regla_editar.complementos.all()
            if regla_editar
            else []
        )
    }
    insumos_complementarios = list(
        Insumo.objects
        .filter(
            tipo_uso="EMPAQUE",
            activo=True,
        )
        .filter(
            Q(disponible_como_complementario=True)
            | Q(id__in=list(complementos_edicion))
        )
        .order_by("nombre")
    )
    for item in insumos_complementarios:
        item.es_complemento_regla = item.id in complementos_edicion
        item.cantidad_complemento_regla = complementos_edicion.get(
            item.id,
            Decimal("1"),
        )

    return render(
        request,
        "pedidos/reglas_empaque.html",
        {
            "reglas": reglas_qs,
            "regla_editar": regla_editar,
            "insumos_empaque": insumos_form,
            "insumos_complementarios": insumos_complementarios,
            "usar_complementarios_inicial": bool(complementos_edicion),
            "productos": Producto.objects.filter(
                activo=True,
                solo_produccion=False,
            ).select_related("tipo").order_by("nombre"),
            "kits": Kit.objects.filter(activo=True).order_by("nombre"),
            "tipos_producto": TipoProducto.objects.filter(
                activo=True,
            ).order_by("nombre"),
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
