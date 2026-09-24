from decimal import Decimal

from django.apps import apps


def _decimal(valor):
    return Decimal(str(valor or 0))


def _tipo_producto_comun(productos):
    productos = [
        producto
        for producto in (productos or [])
        if producto is not None
        and getattr(producto, "tipo_id", None)
    ]
    ids = {producto.tipo_id for producto in productos}
    if len(ids) != 1:
        return None
    return productos[0].tipo


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


def _seleccionar_regla(
    unidades,
    *,
    kit=None,
    tipo_producto=None,
):
    ReglaEmpaque = apps.get_model(
        "pedidos",
        "ReglaEmpaque",
    )

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
            "tipo_producto",
        )
        .prefetch_related("complementos__insumo")
    )

    candidatos = []
    for regla in reglas:
        if not _regla_aplica_rango(regla, unidades):
            continue

        if regla.alcance == "KIT":
            if (
                not kit
                or not getattr(kit, "pk", None)
                or regla.kit_id != kit.pk
            ):
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
            # Las reglas de PRODUCTO son para productos sueltos,
            # no para la unidad comercial Kit.
            continue

        amplitud = (
            regla.hasta_unidades - regla.desde_unidades
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


def _detalle_regla(regla):
    items = []

    principal = regla.insumo
    cantidad_principal = _decimal(
        regla.cantidad_insumo or 1
    )
    costo_unitario = _decimal(
        principal.costo_unitario_aplicado
    )
    items.append(
        {
            "insumo": principal,
            "nombre": principal.nombre,
            "cantidad": cantidad_principal,
            "costo_unitario": costo_unitario,
            "costo_total": (
                costo_unitario
                * cantidad_principal
            ),
            "principal": True,
        }
    )

    for complemento in regla.complementos.all():
        if not complemento.insumo.activo:
            continue
        cantidad = _decimal(
            complemento.cantidad or 1
        )
        costo = _decimal(
            complemento.insumo.costo_unitario_aplicado
        )
        items.append(
            {
                "insumo": complemento.insumo,
                "nombre": complemento.insumo.nombre,
                "cantidad": cantidad,
                "costo_unitario": costo,
                "costo_total": costo * cantidad,
                "principal": False,
            }
        )

    return items


def costo_empaque_kit(
    *,
    kit=None,
    unidades,
    tipo_producto=None,
    productos=None,
):
    """Costo comercial de empaque para una unidad de kit.

    Prioridad: regla específica del kit, categoría, general.
    Si no existe ninguna regla aplicable, usa la provisión global
    configurada para conservar un respaldo comercial.
    """
    unidades = max(int(unidades or 0), 1)

    if tipo_producto is None and kit is not None:
        tipo_producto = getattr(
            kit,
            "tipo_producto",
            None,
        )

    if tipo_producto is None:
        tipo_producto = _tipo_producto_comun(
            productos or []
        )

    regla = _seleccionar_regla(
        unidades,
        kit=kit,
        tipo_producto=tipo_producto,
    )

    if regla is not None:
        items = _detalle_regla(regla)
        costo = sum(
            (
                item["costo_total"]
                for item in items
            ),
            Decimal("0"),
        )
        return {
            "costo": costo,
            "fuente": "REGLA",
            "regla": regla,
            "regla_id": regla.id,
            "regla_nombre": regla.nombre,
            "empaque": regla.insumo,
            "empaque_nombre": regla.insumo.nombre,
            "items": items,
            "complementarios": [
                item
                for item in items
                if not item["principal"]
            ],
            "unidades": unidades,
            "tipo_producto": tipo_producto,
        }

    # Import local para evitar ciclos entre productos, kits y pedidos.
    from productos.models import (
        provision_empaque_unitaria_actual,
    )

    provision = _decimal(
        provision_empaque_unitaria_actual()
    )
    return {
        "costo": provision,
        "fuente": (
            "PROVISION"
            if provision > 0
            else "SIN_CONFIGURACION"
        ),
        "regla": None,
        "regla_id": None,
        "regla_nombre": "",
        "empaque": None,
        "empaque_nombre": "",
        "items": [],
        "complementarios": [],
        "unidades": unidades,
        "tipo_producto": tipo_producto,
    }
