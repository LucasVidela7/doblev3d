from urllib.parse import quote

from django.http import Http404, HttpResponseRedirect

from auditoria.context import obtener_contexto
from auditoria.models import RegistroAuditoria

from .models import ConfiguracionCatalogo


CANALES = {
    "instagram": "Instagram",
    "whatsapp": "WhatsApp",
}


def _destino_contacto(config, canal):
    if canal == "instagram":
        usuario = (config.instagram_usuario or "").strip().lstrip("@")
        if not config.mostrar_instagram or not usuario:
            return ""
        return f"https://www.instagram.com/{quote(usuario, safe='')}/"

    if canal == "whatsapp":
        numero = "".join(ch for ch in (config.whatsapp_numero or "") if ch.isdigit())
        if not config.mostrar_whatsapp or not numero:
            return ""

        destino = f"https://wa.me/{numero}"
        mensaje = (config.whatsapp_mensaje or "").strip()
        if mensaje:
            destino += f"?text={quote(mensaje)}"
        return destino

    return ""


def _registrar_click(config, canal):
    contexto = obtener_contexto()
    etiqueta = CANALES[canal]

    # Estos eventos pertenecen al catálogo público, no a la actividad interna
    # de un usuario autenticado. Incluso si un administrador prueba el enlace
    # con una sesión abierta, lo registramos como interacción de visitante.
    RegistroAuditoria.objects.create(
        usuario=None,
        usuario_nombre="Visitante",
        accion="CLICK_CONTACTO_CATALOGO",
        app_label="productos",
        modelo="configuracioncatalogo",
        objeto_id=str(config.pk or ""),
        objeto_representacion=f"Catálogo · {etiqueta}",
        cambios={"canal": etiqueta},
        ruta=contexto["ruta"],
        metodo=contexto["metodo"],
        ip=contexto["ip"],
    )


def catalogo_contacto(request, canal):
    canal = (canal or "").strip().lower()
    if canal not in CANALES:
        raise Http404("Canal de contacto inexistente")

    config = ConfiguracionCatalogo.objects.first() or ConfiguracionCatalogo()
    destino = _destino_contacto(config, canal)
    if not destino:
        raise Http404("Canal de contacto no disponible")

    # HEAD puede ser usado por navegadores/bots para comprobar el enlace; sólo
    # contamos una interacción humana cuando realmente se solicita con GET.
    if request.method == "GET":
        _registrar_click(config, canal)

    return HttpResponseRedirect(destino)
