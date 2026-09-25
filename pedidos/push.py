import json
import logging

from django.conf import settings
from django.urls import reverse

from pywebpush import WebPushException, webpush

from productos.models import ConfiguracionCatalogo

from .models import WebPushSubscription


logger = logging.getLogger(__name__)


def webpush_habilitado():
    return bool(
        getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "")
        and getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "")
    )


def _enviar_push_suscripciones(payload):
    if not webpush_habilitado():
        return 0

    enviados = 0
    suscripciones = list(
        WebPushSubscription.objects.filter(activa=True)
    )

    for suscripcion in suscripciones:
        try:
            webpush(
                subscription_info={
                    "endpoint": suscripcion.endpoint,
                    "keys": {
                        "p256dh": suscripcion.p256dh,
                        "auth": suscripcion.auth,
                    },
                },
                data=json.dumps(
                    payload,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                vapid_private_key=settings.WEBPUSH_VAPID_PRIVATE_KEY,
                vapid_claims={
                    "sub": settings.WEBPUSH_VAPID_SUBJECT,
                },
                ttl=60 * 60,
                timeout=5,
            )
            enviados += 1
        except WebPushException as error:
            status = getattr(
                getattr(error, "response", None),
                "status_code",
                None,
            )
            if status in {404, 410}:
                suscripcion.activa = False
                suscripcion.save(
                    update_fields=["activa", "actualizada_en"]
                )
            else:
                logger.warning(
                    "No se pudo enviar Web Push a %s: %s",
                    suscripcion.id,
                    error,
                )
        except Exception:
            logger.exception(
                "Error inesperado enviando Web Push a %s",
                suscripcion.id,
            )

    return enviados


def enviar_push(payload):
    config = ConfiguracionCatalogo.objects.first()
    if config and not config.notificaciones_pedidos_web_activas:
        return 0

    return _enviar_push_suscripciones(payload)


def enviar_push_operativo(payload):
    """
    Avisos internos de Gestión (producción, impresoras, etc.).
    No dependen del switch de pedidos web.
    """
    return _enviar_push_suscripciones(payload)


def notificar_nueva_solicitud_web(solicitud_id):
    from .models import SolicitudWeb

    solicitud = (
        SolicitudWeb.objects
        .filter(id=solicitud_id)
        .prefetch_related("items")
        .first()
    )
    if not solicitud:
        return 0

    unidades = sum(
        item.cantidad
        for item in solicitud.items.all()
    )
    total = solicitud.total
    total_texto = f"{total:,.0f}".replace(",", ".")

    return enviar_push(
        {
            "title": "Nuevo pedido web",
            "body": (
                f"{solicitud.nombre} · "
                + "$"
                + total_texto
                + " · "
                + f"{unidades} unidad{'es' if unidades != 1 else ''}"
            ),
            "url": reverse(
                "pedidos:solicitud_web_detalle",
                args=[solicitud.id],
            ),
            "tag": f"solicitud-web-{solicitud.id}",
            "icon": "/static/brand/apple-touch-icon.png",
            "badge": "/static/brand/favicon.ico",
        }
    )
