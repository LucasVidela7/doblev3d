import json
from datetime import timedelta
from urllib import parse, request as urlrequest

from django.conf import settings
from django.db import transaction
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from pedidos.push import enviar_push

from .models import ConfiguracionCatalogo, SolicitudArrepentimiento


def _config():
    return (
        ConfiguracionCatalogo.objects.first()
        or ConfiguracionCatalogo()
    )


def _ip_cliente(request):
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0]
    return (forwarded or request.META.get("REMOTE_ADDR") or "").strip()


def _validar_turnstile(request):
    secret = getattr(settings, "TURNSTILE_SECRET_KEY", "")
    site_key = getattr(settings, "TURNSTILE_SITE_KEY", "")
    if not secret or not site_key:
        return True

    token = (request.POST.get("cf-turnstile-response") or "").strip()
    if not token:
        return False

    body = parse.urlencode(
        {
            "secret": secret,
            "response": token,
            "remoteip": _ip_cliente(request),
        }
    ).encode("utf-8")

    try:
        req = urlrequest.Request(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data=body,
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=4) as response:
            resultado = json.loads(response.read().decode("utf-8"))
        return bool(resultado.get("success"))
    except Exception:
        return False


def _contexto_legal(request=None, **extra):
    contexto = {
        "config": _config(),
        "hoy": timezone.localdate(),
        "turnstile_site_key": getattr(settings, "TURNSTILE_SITE_KEY", ""),
    }

    if request is not None:
        nombre = getattr(
            getattr(request, "resolver_match", None),
            "url_name",
            "",
        )
        metadata = {
            "catalogo_terminos": {
                "description": (
                    "Términos de compra de Doble V 3D: funcionamiento "
                    "del catálogo, presupuestos, pedidos, entrega y "
                    "derechos del consumidor."
                ),
                "route": "catalogo_terminos",
                "robots": "index,follow",
            },
            "catalogo_privacidad": {
                "description": (
                    "Política de privacidad de Doble V 3D: qué datos "
                    "se utilizan al navegar, consultar o enviar una "
                    "solicitud y cómo se protegen."
                ),
                "route": "catalogo_privacidad",
                "robots": "index,follow",
            },
            "catalogo_arrepentimiento": {
                "description": (
                    "Formulario de Doble V 3D para solicitar el "
                    "arrepentimiento de una compra a distancia."
                ),
                "route": "catalogo_arrepentimiento",
                "robots": "noindex,follow",
            },
            "catalogo_arrepentimiento_gracias": {
                "description": (
                    "Confirmación de recepción de una solicitud de "
                    "arrepentimiento en Doble V 3D."
                ),
                "route": "catalogo_arrepentimiento_gracias",
                "robots": "noindex,nofollow",
            },
        }.get(nombre)

        if metadata:
            contexto["seo_description"] = metadata["description"]
            contexto["seo_canonical_url"] = (
                request.build_absolute_uri(
                    reverse(metadata["route"])
                )
            )
            contexto["seo_robots"] = metadata["robots"]

    contexto.update(extra)
    return contexto


@never_cache
def terminos_compra(request):
    return render(
        request,
        "productos/legal_terminos.html",
        _contexto_legal(request),
    )


@never_cache
def privacidad(request):
    return render(
        request,
        "productos/legal_privacidad.html",
        _contexto_legal(request),
    )


@never_cache
@transaction.atomic
def arrepentimiento(request):
    error = ""

    if request.method == "POST":
        # Honeypot simple para evitar formularios automatizados.
        if (request.POST.get("website") or "").strip():
            return redirect("catalogo_arrepentimiento_gracias")

        nombre = (request.POST.get("nombre") or "").strip()[:150]
        contacto = (request.POST.get("contacto") or "").strip()[:180]
        referencia = (request.POST.get("referencia") or "").strip()[:80]
        detalle = (request.POST.get("detalle") or "").strip()[:3000]

        if len(contacto) < 5:
            error = (
                "Indicá un WhatsApp o email para poder identificar "
                "y responder tu solicitud."
            )
        elif not _validar_turnstile(request):
            error = (
                "No pudimos validar la solicitud. "
                "Actualizá la página e intentá nuevamente."
            )
        else:
            ahora = timezone.now()
            recientes = SolicitudArrepentimiento.objects.filter(
                contacto__iexact=contacto,
                creada_en__gte=ahora - timedelta(hours=2),
            )
            duplicada = recientes.filter(
                referencia=referencia,
                detalle=detalle,
                creada_en__gte=ahora - timedelta(minutes=15),
            ).order_by("-id").first()

            if duplicada:
                request.session["arrepentimiento_ultimo_id"] = duplicada.id
                return redirect("catalogo_arrepentimiento_gracias")

            if recientes.count() >= 3:
                error = (
                    "Ya recibimos varias solicitudes con este contacto. "
                    "Esperá un rato antes de enviar otra."
                )
                return render(
                    request,
                    "productos/legal_arrepentimiento.html",
                    _contexto_legal(request, error=error),
                )

            solicitud = SolicitudArrepentimiento.objects.create(
                nombre=nombre,
                contacto=contacto,
                referencia=referencia,
                detalle=detalle,
            )
            request.session["arrepentimiento_ultimo_id"] = solicitud.id

            def _avisar():
                enviar_push(
                    {
                        "title": "Solicitud de arrepentimiento",
                        "body": (
                            f"{solicitud.codigo} · "
                            f"{solicitud.nombre or solicitud.contacto}"
                        ),
                        "url": (
                            reverse("dashboard:configuracion")
                            + "#legal"
                        ),
                        "tag": f"arrepentimiento-{solicitud.id}",
                        "icon": "/static/brand/apple-touch-icon.png",
                        "badge": "/static/brand/favicon.ico",
                    }
                )

            transaction.on_commit(_avisar)
            return redirect("catalogo_arrepentimiento_gracias")

    return render(
        request,
        "productos/legal_arrepentimiento.html",
        _contexto_legal(
            request,
            error=error,
        ),
    )


@never_cache
def arrepentimiento_gracias(request):
    solicitud = None
    solicitud_id = request.session.get(
        "arrepentimiento_ultimo_id"
    )
    if solicitud_id:
        solicitud = (
            SolicitudArrepentimiento.objects
            .filter(id=solicitud_id)
            .first()
        )

    return render(
        request,
        "productos/legal_arrepentimiento_gracias.html",
        _contexto_legal(
            request,
            solicitud=solicitud,
        ),
    )
