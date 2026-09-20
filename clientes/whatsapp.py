from decimal import Decimal
from urllib.parse import quote, urlencode

from django.urls import reverse
from django.utils import timezone

from pedidos.models import Pedido, Presupuesto
from productos.models import ConfiguracionCatalogo

from .telefonos import normalizar_telefono


MOTIVOS_VALIDOS = {
    "GENERICO",
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
):
    motivo = motivo if motivo in MOTIVOS_VALIDOS else "GENERICO"
    config, _ = ConfiguracionCatalogo.objects.get_or_create(
        pk=1
    )

    nombre = (
        cliente.nombre.strip()
        if cliente.nombre
        else "¿cómo estás?"
    )

    variables = {
        "nombre": nombre,
        "codigo": "",
        "saldo": "",
        "total": "",
        "pagado": "",
        "fecha": "",
        "fecha_entrega": "",
        "dias_sin_actividad": "",
        "ultima_actividad": "",
    }

    campo = "whatsapp_mensaje_cliente_generico"

    if motivo == "PEDIDO_LISTO" and pedido:
        campo = (
            "whatsapp_mensaje_cliente_pedido_listo"
        )
        variables.update(
            {
                "codigo": pedido.codigo,
                "total": _dinero(
                    pedido.total
                ),
                "pagado": _dinero(
                    pedido.total_pagado
                ),
                "saldo": _dinero(
                    pedido.saldo_pendiente
                ),
                "fecha": _fecha(
                    pedido.fecha
                ),
                "fecha_entrega": _fecha(
                    pedido.fecha_entrega
                ),
            }
        )

    elif motivo == "SALDO" and pedido:
        campo = "whatsapp_mensaje_cliente_saldo"
        variables.update(
            {
                "codigo": pedido.codigo,
                "total": _dinero(
                    pedido.total
                ),
                "pagado": _dinero(
                    pedido.total_pagado
                ),
                "saldo": _dinero(
                    max(
                        Decimal(
                            pedido.saldo_pendiente
                            or 0
                        ),
                        Decimal("0"),
                    )
                ),
                "fecha": _fecha(
                    pedido.fecha
                ),
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
    return _renderizar_plantilla(
        plantilla,
        variables,
    )


def enlace_whatsapp(numero, mensaje):
    if not numero:
        return ""
    return f"https://wa.me/{numero}?text={quote(mensaje)}"


def url_contacto(
    cliente,
    motivo="GENERICO",
    *,
    pedido=None,
    presupuesto=None,
):
    params = {
        "motivo": motivo,
    }
    if pedido:
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


def resolver_contexto(cliente, motivo, pedido_id=None, presupuesto_id=None):
    motivo = motivo if motivo in MOTIVOS_VALIDOS else "GENERICO"

    pedido = None
    presupuesto = None

    if pedido_id:
        pedido = (
            Pedido.objects
            .filter(
                id=pedido_id,
                cliente=cliente,
            )
            .prefetch_related("detalles", "pagos")
            .first()
        )

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

    if motivo in {"PEDIDO_LISTO", "SALDO"} and not pedido:
        motivo = "GENERICO"

    if motivo == "PRESUPUESTO" and not presupuesto:
        motivo = "GENERICO"

    mensaje = mensaje_whatsapp(
        cliente,
        motivo,
        pedido=pedido,
        presupuesto=presupuesto,
    )

    referencia = ""
    if pedido:
        referencia = pedido.codigo
    elif presupuesto:
        referencia = presupuesto.codigo

    return {
        "motivo": motivo,
        "pedido": pedido,
        "presupuesto": presupuesto,
        "mensaje": mensaje,
        "referencia": referencia,
    }
