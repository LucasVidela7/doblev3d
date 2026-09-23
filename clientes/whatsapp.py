from decimal import Decimal
from urllib.parse import quote, urlencode

from django.urls import reverse
from django.utils import timezone

from pedidos.models import Pedido, Presupuesto
from productos.models import ConfiguracionCatalogo
from productos.whatsapp import datos_pago_texto

from .telefonos import normalizar_telefono


MOTIVOS_VALIDOS = {
    "GENERICO",
    "PEDIDO_APROBADO",
    "PEDIDO_LISTO",
    "SALDO",
    "PRESUPUESTO",
    "REACTIVACION",
}


class _VariablesWhatsApp(dict):
    def __missing__(self, clave):
        return "{" + clave + "}"


def _dinero(valor):
    numero = Decimal(str(valor or 0))
    return f"{numero:,.0f}".replace(",", ".")


def _fecha(valor):
    if not valor:
        return ""
    try:
        return valor.strftime("%d/%m/%Y")
    except AttributeError:
        return str(valor)


def _primer_nombre(valor, fallback="¿cómo estás?"):
    partes = str(valor or "").strip().split()
    return partes[0] if partes else fallback


def _nombre_detalle_pedido(detalle):
    if detalle.tipo_item == "KIT":
        if detalle.kit:
            return detalle.kit.nombre
        snapshot = detalle.kit_snapshot or {}
        return snapshot.get("nombre") or "Kit"

    if detalle.tipo_item == "PERSONALIZADO":
        nombre = (
            detalle.producto.nombre
            if detalle.producto
            else "Producto"
        )
        return f"{nombre} personalizado"

    if detalle.producto:
        return detalle.producto.nombre

    return detalle.get_tipo_item_display()


def _url_publica_pedido(pedido, request=None):
    ruta = reverse(
        "pedido_publico",
        args=[pedido.public_token],
    )
    if request is not None:
        return request.build_absolute_uri(ruta)
    return ruta


def _cantidad_pagos(pedido):
    return len(list(pedido.pagos.all()))


def _bloque_pedido_whatsapp(pedido, request=None):
    saldo = max(
        Decimal(pedido.saldo_pendiente or 0),
        Decimal("0"),
    )
    pagado = Decimal(pedido.total_pagado or 0)
    cantidad_pagos = _cantidad_pagos(pedido)

    lineas = [
        f"*{pedido.codigo} · {pedido.get_estado_display()}*",
        "Total: $" + _dinero(pedido.total),
    ]

    if cantidad_pagos <= 0:
        lineas.append("Sin pagos registrados")
    elif cantidad_pagos == 1:
        lineas.append(
            "1 pago registrado · Pagado: $"
            + _dinero(pagado)
        )
    else:
        lineas.append(
            f"{cantidad_pagos} pagos registrados · Pagado: $"
            + _dinero(pagado)
        )

    if saldo > 0:
        lineas.append(
            "Saldo pendiente: $" + _dinero(saldo)
        )
    else:
        lineas.append("Pagado ✓")

    url = _url_publica_pedido(
        pedido,
        request=request,
    )
    lineas.append("Ver pedido: " + url)

    return {
        "texto": "\n".join(lineas),
        "saldo": saldo,
        "pagado": pagado,
        "cantidad_pagos": cantidad_pagos,
        "url": url,
    }


def _resumen_pedidos(pedidos, request=None):
    pedidos = list(pedidos)
    bloques = [
        _bloque_pedido_whatsapp(
            pedido,
            request=request,
        )
        for pedido in pedidos
    ]
    return {
        "pedidos": pedidos,
        "bloques": bloques,
        "texto": "\n\n".join(
            bloque["texto"]
            for bloque in bloques
        ),
        "saldo_total": sum(
            (
                bloque["saldo"]
                for bloque in bloques
            ),
            Decimal("0"),
        ),
        "cantidad_listos": sum(
            1
            for pedido in pedidos
            if pedido.estado == "LISTO"
        ),
        "cantidad_con_saldo": sum(
            1
            for bloque in bloques
            if bloque["saldo"] > 0
        ),
    }


def _cierre_pedidos(resumen):
    cantidad = len(resumen["pedidos"])
    listos = resumen["cantidad_listos"]
    saldo_total = resumen["saldo_total"]

    if listos and saldo_total > 0:
        if cantidad == 1:
            return (
                "Cuando puedas coordinamos el saldo pendiente "
                "y la entrega 😊"
            )
        return (
            "Cuando puedas coordinamos los saldos pendientes "
            "y la entrega de los pedidos que ya están listos 😊"
        )

    if listos:
        if cantidad == 1:
            return "Cuando quieras coordinamos la entrega 😊"
        return (
            "Cuando quieras coordinamos la entrega de los "
            "pedidos que ya están listos 😊"
        )

    if saldo_total > 0:
        return (
            "Cuando puedas coordinamos el pago del saldo "
            "pendiente 😊"
            if cantidad == 1
            else (
                "Cuando puedas coordinamos el pago de los "
                "saldos pendientes 😊"
            )
        )

    return "Si necesitás algo con estos pedidos, escribinos 😊"


def _plantilla_config(config, nombre_campo):
    valor = (
        getattr(config, nombre_campo, "")
        or ""
    ).strip()
    if valor:
        return valor

    campo = ConfiguracionCatalogo._meta.get_field(
        nombre_campo
    )
    default = campo.default
    return (
        default()
        if callable(default)
        else str(default or "")
    )


def _renderizar_plantilla(plantilla, variables):
    try:
        return plantilla.format_map(
            _VariablesWhatsApp(variables)
        )
    except (ValueError, KeyError):
        return plantilla


def _mensaje_pedidos_whatsapp(cliente, pedidos, request=None):
    resumen = _resumen_pedidos(
        pedidos,
        request=request,
    )
    config, _ = ConfiguracionCatalogo.objects.get_or_create(
        pk=1
    )
    plantilla = _plantilla_config(
        config,
        "whatsapp_mensaje_cliente_multiples_pedidos",
    )
    cierre = _cierre_pedidos(resumen)
    datos_pago = (
        datos_pago_texto(config)
        if resumen["saldo_total"] > 0
        else ""
    )
    mensaje = _renderizar_plantilla(
        plantilla,
        {
            "nombre": _primer_nombre(cliente.nombre),
            "cantidad_pedidos": len(resumen["pedidos"]),
            "pedidos": resumen["texto"],
            "saldo_total": _dinero(
                resumen["saldo_total"]
            ),
            "saldo_resumen": (
                "*Saldo total pendiente: $"
                + _dinero(resumen["saldo_total"])
                + "*"
                if resumen["saldo_total"] > 0
                else "*Todos los pedidos están pagos ✓*"
            ),
            "cantidad_listos": resumen["cantidad_listos"],
            "cantidad_con_saldo": resumen[
                "cantidad_con_saldo"
            ],
            "datos_pago": datos_pago,
            "cierre": cierre,
        },
    ).strip()

    # El bloque automático garantiza que cada pedido conserve su URL
    # pública y el resumen real de pagos aunque exista una plantilla
    # personalizada anterior que no use {pedidos}.
    urls = [
        bloque["url"]
        for bloque in resumen["bloques"]
    ]
    if urls and not all(
        url in mensaje
        for url in urls
    ):
        mensaje = (
            mensaje
            + "\n\n"
            + resumen["texto"]
        ).strip()

    if (
        datos_pago
        and datos_pago not in mensaje
    ):
        mensaje = (
            mensaje
            + "\n\n"
            + datos_pago
        ).strip()

    return mensaje


def numero_whatsapp(cliente):
    clave = normalizar_telefono(cliente.telefono)
    if not clave:
        return ""
    return f"549{clave}" if len(clave) == 10 else clave


def mensaje_whatsapp(
    cliente,
    motivo,
    *,
    pedido=None,
    presupuesto=None,
    request=None,
):
    motivo = motivo if motivo in MOTIVOS_VALIDOS else "GENERICO"
    config, _ = ConfiguracionCatalogo.objects.get_or_create(
        pk=1
    )

    nombre = _primer_nombre(cliente.nombre)

    variables = {
        "nombre": nombre,
        "codigo": "",
        "saldo": "",
        "total": "",
        "pagado": "",
        "cantidad_pagos": "",
        "pedido": "",
        "url": "",
        "datos_pago": "",
        "cierre": "",
        "fecha": "",
        "fecha_entrega": "",
        "dias_sin_actividad": "",
        "ultima_actividad": "",
    }

    campo = "whatsapp_mensaje_cliente_generico"
    bloque_pedido = None

    if motivo == "PEDIDO_APROBADO" and pedido:
        campo = (
            "whatsapp_mensaje_cliente_pedido_aprobado"
        )
        variables.update(
            {
                "codigo": pedido.codigo,
                "url": _url_publica_pedido(
                    pedido,
                    request=request,
                ),
                "total": _dinero(pedido.total),
                "pagado": _dinero(pedido.total_pagado),
                "saldo": _dinero(pedido.saldo_pendiente),
                "fecha": _fecha(pedido.fecha),
                "fecha_entrega": _fecha(
                    pedido.fecha_entrega
                ),
            }
        )

    elif motivo in {"PEDIDO_LISTO", "SALDO"} and pedido:
        bloque_pedido = _bloque_pedido_whatsapp(
            pedido,
            request=request,
        )
        resumen = _resumen_pedidos(
            [pedido],
            request=request,
        )
        cierre = _cierre_pedidos(resumen)
        datos_pago = (
            datos_pago_texto(config)
            if bloque_pedido["saldo"] > 0
            else ""
        )

        if motivo == "PEDIDO_LISTO":
            campo = (
                "whatsapp_mensaje_cliente_pedido_listo_saldo"
                if bloque_pedido["saldo"] > 0
                else "whatsapp_mensaje_cliente_pedido_listo"
            )
        else:
            campo = "whatsapp_mensaje_cliente_saldo"

        variables.update(
            {
                "codigo": pedido.codigo,
                "url": bloque_pedido["url"],
                "total": _dinero(pedido.total),
                "pagado": _dinero(
                    bloque_pedido["pagado"]
                ),
                "saldo": _dinero(
                    bloque_pedido["saldo"]
                ),
                "cantidad_pagos": (
                    bloque_pedido["cantidad_pagos"]
                ),
                "pedido": bloque_pedido["texto"],
                "datos_pago": datos_pago,
                "cierre": cierre,
                "fecha": _fecha(pedido.fecha),
                "fecha_entrega": _fecha(
                    pedido.fecha_entrega
                ),
            }
        )

    elif motivo == "PRESUPUESTO" and presupuesto:
        campo = (
            "whatsapp_mensaje_cliente_presupuesto"
        )
        variables.update(
            {
                "codigo": presupuesto.codigo,
                "total": _dinero(
                    presupuesto.total
                ),
                "fecha": _fecha(
                    presupuesto.fecha
                ),
            }
        )

    elif motivo == "REACTIVACION":
        campo = (
            "whatsapp_mensaje_cliente_reactivacion"
        )

        ultima_pedido = (
            Pedido.objects
            .filter(cliente=cliente)
            .order_by("-fecha", "-id")
            .values_list("fecha", flat=True)
            .first()
        )
        ultima_presupuesto = (
            Presupuesto.objects
            .filter(cliente=cliente)
            .order_by("-fecha", "-id")
            .values_list("fecha", flat=True)
            .first()
        )
        fechas = [
            valor
            for valor in (
                ultima_pedido,
                ultima_presupuesto,
            )
            if valor
        ]
        ultima = max(fechas) if fechas else None
        dias = (
            (timezone.localdate() - ultima).days
            if ultima
            else ""
        )
        variables.update(
            {
                "dias_sin_actividad": dias,
                "ultima_actividad": _fecha(
                    ultima
                ),
            }
        )

    plantilla = _plantilla_config(
        config,
        campo,
    )
    mensaje = _renderizar_plantilla(
        plantilla,
        variables,
    ).strip()

    # Para mensajes de pedido, la URL pública y el detalle financiero
    # son obligatorios. Si una plantilla vieja/custom no los incluyó,
    # se agregan automáticamente sin romper esa configuración.
    if (
        bloque_pedido
        and bloque_pedido["url"] not in mensaje
    ):
        mensaje = (
            mensaje
            + "\n\n"
            + bloque_pedido["texto"]
        ).strip()

    if (
        bloque_pedido
        and bloque_pedido["saldo"] > 0
        and variables.get("datos_pago")
        and variables["datos_pago"] not in mensaje
    ):
        mensaje = (
            mensaje
            + "\n\n"
            + variables["datos_pago"]
        ).strip()

    return mensaje


def enlace_whatsapp(numero, mensaje):
    if not numero:
        return ""
    return f"https://wa.me/{numero}?text={quote(mensaje)}"


def url_contacto(
    cliente,
    motivo="GENERICO",
    *,
    pedido=None,
    pedidos=None,
    presupuesto=None,
):
    params = {
        "motivo": motivo,
    }

    if pedidos:
        ids = []
        for item in pedidos:
            valor = getattr(item, "id", item)
            try:
                valor = int(valor)
            except (TypeError, ValueError):
                continue
            if valor > 0 and valor not in ids:
                ids.append(valor)
        if ids:
            params["pedidos"] = ",".join(
                str(valor)
                for valor in ids
            )
    elif pedido:
        params["pedido"] = pedido.id

    if presupuesto:
        params["presupuesto"] = presupuesto.id

    return (
        reverse(
            "clientes:whatsapp",
            args=[cliente.id],
        )
        + "?"
        + urlencode(params)
    )


def _normalizar_ids_pedidos(valor):
    if not valor:
        return []

    if isinstance(valor, (list, tuple, set)):
        partes = valor
    else:
        partes = str(valor).split(",")

    ids = []
    for parte in partes:
        try:
            pedido_id = int(str(parte).strip())
        except (TypeError, ValueError):
            continue
        if pedido_id > 0 and pedido_id not in ids:
            ids.append(pedido_id)

    return ids


def resolver_contexto(
    cliente,
    motivo,
    pedido_id=None,
    pedidos_ids=None,
    presupuesto_id=None,
    request=None,
):
    motivo = (
        motivo
        if motivo in MOTIVOS_VALIDOS
        else "GENERICO"
    )

    pedidos = []
    ids = _normalizar_ids_pedidos(
        pedidos_ids
    )

    if ids:
        consulta = (
            Pedido.objects
            .filter(
                id__in=ids,
                cliente=cliente,
            )
            .select_related("cliente")
            .prefetch_related(
                "detalles__producto",
                "detalles__kit",
                "pagos",
            )
        )
        por_id = {
            pedido.id: pedido
            for pedido in consulta
        }
        pedidos = [
            por_id[pedido_id]
            for pedido_id in ids
            if pedido_id in por_id
        ]

    if not pedidos and pedido_id:
        pedido = (
            Pedido.objects
            .filter(
                id=pedido_id,
                cliente=cliente,
            )
            .select_related("cliente")
            .prefetch_related(
                "detalles__producto",
                "detalles__kit",
                "pagos",
            )
            .first()
        )
        if pedido:
            pedidos = [pedido]

    presupuesto = None
    if presupuesto_id:
        presupuesto = (
            Presupuesto.objects
            .filter(
                id=presupuesto_id,
                cliente=cliente,
            )
            .prefetch_related("detalles")
            .first()
        )

    if (
        motivo in {"PEDIDO_APROBADO", "PEDIDO_LISTO", "SALDO"}
        and not pedidos
    ):
        motivo = "GENERICO"

    if (
        motivo == "PRESUPUESTO"
        and not presupuesto
    ):
        motivo = "GENERICO"

    pedido = (
        pedidos[0]
        if len(pedidos) == 1
        else None
    )

    if len(pedidos) > 1:
        mensaje = _mensaje_pedidos_whatsapp(
            cliente,
            pedidos,
            request=request,
        )
    else:
        mensaje = mensaje_whatsapp(
            cliente,
            motivo,
            pedido=pedido,
            presupuesto=presupuesto,
            request=request,
        )

    referencia = ""
    if pedidos:
        referencia = ", ".join(
            pedido.codigo
            for pedido in pedidos
        )[:40]
    elif presupuesto:
        referencia = presupuesto.codigo

    return {
        "motivo": motivo,
        "pedido": pedido,
        "pedidos": pedidos,
        "presupuesto": presupuesto,
        "mensaje": mensaje,
        "referencia": referencia,
    }
