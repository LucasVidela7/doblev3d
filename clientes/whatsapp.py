from decimal import Decimal
from urllib.parse import quote, urlencode

from django.urls import reverse

from pedidos.models import Pedido, Presupuesto

from .telefonos import normalizar_telefono


MOTIVOS_VALIDOS = {
    "GENERICO",
    "PEDIDO_LISTO",
    "SALDO",
    "PRESUPUESTO",
    "REACTIVACION",
}


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
    nombre = cliente.nombre.strip() or "¿cómo estás?"

    if motivo == "PEDIDO_LISTO" and pedido:
        return (
            f"Hola {nombre} 👋 Tu pedido {pedido.codigo} de Doble V 3D "
            "ya está listo para entregar. Cuando quieras coordinamos "
            "la entrega. ¡Gracias!"
        )

    if motivo == "SALDO" and pedido:
        saldo = max(
            Decimal(pedido.saldo_pendiente or 0),
            Decimal("0"),
        )
        return (
            f"Hola {nombre} 👋 Te escribo por el pedido {pedido.codigo}. "
            f"Quedó un saldo pendiente de $ {saldo:,.0f}. "
            "Cuando puedas coordinamos el pago. ¡Gracias!"
        )

    if motivo == "PRESUPUESTO" and presupuesto:
        return (
            f"Hola {nombre} 👋 ¿Cómo estás? Te escribo por el presupuesto "
            f"{presupuesto.codigo} de Doble V 3D. Si querés hacer algún "
            "cambio o avanzar con el pedido, avisame y lo revisamos."
        )

    if motivo == "REACTIVACION":
        return (
            f"Hola {nombre} 👋 ¿Cómo estás? Hace un tiempo que no hablamos "
            "y quería consultarte si necesitabas volver a pedir alguno de "
            "nuestros productos de Doble V 3D."
        )

    return (
        f"Hola {nombre} 👋 ¿Cómo estás? Te escribo de Doble V 3D."
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
