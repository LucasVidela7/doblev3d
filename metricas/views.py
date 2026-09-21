import json
from urllib.parse import urlparse

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import EventoCatalogo
from .services import registrar_evento_request


EVENTOS_PUBLICOS = {
    EventoCatalogo.PAGE_VIEW,
    EventoCatalogo.ADD_TO_CART,
    EventoCatalogo.CHECKOUT_START,
}


def _origen_valido(request):
    origin = (request.META.get("HTTP_ORIGIN") or "").strip()
    if not origin:
        return True
    try:
        return urlparse(origin).netloc == request.get_host()
    except ValueError:
        return False


@csrf_exempt
@require_POST
def registrar(request):
    if not _origen_valido(request):
        return HttpResponse(status=403)

    if len(request.body or b"") > 4096:
        return HttpResponse(status=413)

    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return HttpResponse(status=400)

    evento = str(payload.get("evento") or "").upper().strip()
    if evento not in EVENTOS_PUBLICOS:
        return HttpResponse(status=400)

    contenido_tipo = str(
        payload.get("contenido_tipo") or ""
    ).upper().strip()
    if contenido_tipo not in {"", "PRODUCTO", "KIT"}:
        contenido_tipo = ""

    contenido_id = payload.get("contenido_id")
    if not str(contenido_id or "").isdigit():
        contenido_id = None

    registrar_evento_request(
        request,
        evento,
        pagina=str(payload.get("pagina") or "")[:40],
        contenido_tipo=contenido_tipo,
        contenido_id=contenido_id,
        ruta=str(payload.get("ruta") or request.path)[:255],
        origen=str(payload.get("origen") or "")[:120],
    )
    return HttpResponse(status=204)
