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


def _contexto_legal(**extra):
    contexto = {
        "config": _config(),
        "hoy": timezone.localdate(),
    }
    contexto.update(extra)
    return contexto


@never_cache
def terminos_compra(request):
    return render(
        request,
        "productos/legal_terminos.html",
        _contexto_legal(),
    )


@never_cache
def privacidad(request):
    return render(
        request,
        "productos/legal_privacidad.html",
        _contexto_legal(),
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
        else:
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
            solicitud=solicitud,
        ),
    )
