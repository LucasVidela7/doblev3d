import gzip
import io
import secrets

from django.conf import settings
from django.core.management import call_command
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseNotFound
from django.views.decorators.http import require_GET


@require_GET
def export_database(request):
    """Exportación temporal y autenticada para clonar producción hacia QA."""
    if settings.APP_ENV not in {"prod", "production"}:
        return HttpResponseNotFound()

    esperado = settings.DB_SYNC_TOKEN
    recibido = request.headers.get("X-DB-Sync-Token", "")
    if not esperado or not secrets.compare_digest(recibido, esperado):
        return HttpResponseForbidden("Token inválido.")

    salida = io.StringIO()
    call_command(
        "dumpdata",
        format="json",
        indent=None,
        exclude=[
            "sessions.session",
            "pedidos.webpushsubscription",
        ],
        stdout=salida,
        verbosity=0,
    )

    comprimido = gzip.compress(salida.getvalue().encode("utf-8"), compresslevel=6)
    respuesta = HttpResponse(comprimido, content_type="application/gzip")
    respuesta["Content-Disposition"] = 'attachment; filename="doblev3d-production.json.gz"'
    respuesta["Cache-Control"] = "no-store"
    return respuesta
