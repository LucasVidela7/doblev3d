from decimal import Decimal
from urllib.parse import quote

from django.urls import reverse
from django.utils import timezone


PORCENTAJE_SENIA = Decimal("0.30")


def _primer_nombre(valor):
    partes = str(valor or "").strip().split()
    return partes[0] if partes else ""


PLACEHOLDERS_SOLICITUD = (
    "{nombre}",
    "{codigo}",
    "{detalle}",
    "{total}",
    "{senia}",
    "{datos_pago}",
    "{fecha_hoy}",
    "{observaciones}",
    "{url}",
)




def datos_pago_texto(config):
    if config is None:
        return ""

    alias = str(
        getattr(config, "whatsapp_pago_alias", "") or ""
    ).strip()
    titular = str(
        getattr(config, "whatsapp_pago_titular", "") or ""
    ).strip()

    if alias and titular:
        return f"Alias: {alias} - {titular}"
    if alias:
        return f"Alias: {alias}"
    if titular:
        return f"Titular: {titular}"
    return ""

def _moneda(valor):
    try:
        numero = Decimal(str(valor or 0))
    except Exception:
        numero = Decimal("0")
    return "$ " + f"{numero:,.0f}".replace(",", ".")


def detalle_solicitud_texto(solicitud):
    lineas = []

    for item in solicitud.items.all():
        linea = f"• {item.cantidad}× {item.nombre_snapshot}"

        if item.tipo_item == "KIT":
            componentes = list(item.productos_kit.all())
            if componentes:
                seleccion = ", ".join(
                    f"{componente.cantidad}× {componente.producto.nombre}"
                    for componente in componentes
                )
                linea += f"\n  Selección: {seleccion}"

        precio_lista = (
            Decimal(str(item.precio_base_unitario or 0))
            + Decimal(str(item.adicional_unitario or 0))
        )
        precio_final = Decimal(str(item.precio_unitario or 0))

        if precio_final < precio_lista:
            linea += (
                f"\n  Precio final: {_moneda(precio_final)} c/u "
                f"(lista {_moneda(precio_lista)})"
            )

        lineas.append(linea)

    return "\n".join(lineas) or "Sin productos."


def contexto_mensaje_solicitud(
    solicitud,
    request=None,
    config=None,
):
    ruta_publica = reverse(
        "solicitud_publica",
        args=[solicitud.public_token],
    )
    url_publica = (
        request.build_absolute_uri(ruta_publica)
        if request is not None
        else ruta_publica
    )
    return {
        "{nombre}": _primer_nombre(solicitud.nombre),
        "{codigo}": solicitud.codigo,
        "{detalle}": detalle_solicitud_texto(solicitud),
        "{total}": _moneda(solicitud.total),
        "{senia}": _moneda(
            Decimal(str(solicitud.total or 0)) * PORCENTAJE_SENIA
        ),
        "{datos_pago}": datos_pago_texto(config),
        "{fecha_hoy}": timezone.localdate().strftime("%d/%m/%Y"),
        "{observaciones}": (solicitud.observaciones or "").strip() or "Sin observaciones.",
        "{url}": url_publica,
    }


def renderizar_mensaje_solicitud(
    plantilla,
    solicitud,
    request=None,
    *,
    config=None,
    incluir_datos_pago=False,
):
    mensaje = (plantilla or "").strip()
    contexto = contexto_mensaje_solicitud(
        solicitud,
        request=request,
        config=config,
    )
    if not incluir_datos_pago:
        contexto["{datos_pago}"] = ""

    for marcador, valor in contexto.items():
        mensaje = mensaje.replace(marcador, valor)

    datos_pago = contexto.get("{datos_pago}", "").strip()
    if (
        incluir_datos_pago
        and datos_pago
        and datos_pago not in mensaje
    ):
        mensaje = (mensaje + "\n\n" + datos_pago).strip()

    return mensaje


def whatsapp_url(numero, mensaje):
    numero_limpio = "".join(ch for ch in (numero or "") if ch.isdigit())
    if not numero_limpio:
        return ""

    destino = f"https://wa.me/{numero_limpio}"
    mensaje = (mensaje or "").strip()
    if mensaje:
        destino += f"?text={quote(mensaje)}"
    return destino
