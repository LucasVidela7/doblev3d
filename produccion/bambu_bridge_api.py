import hmac
import json
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import ImpresoraEstadoBambu


def _numero_entero(valor, minimo=None, maximo=None):
    if valor in (None, ""):
        return None

    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return None

    if minimo is not None:
        numero = max(minimo, numero)
    if maximo is not None:
        numero = min(maximo, numero)

    return numero


def _numero_float(valor):
    if valor in (None, ""):
        return None

    try:
        return float(valor)
    except (TypeError, ValueError):
        return None


def _fecha_epoch(valor):
    if valor in (None, ""):
        return None

    try:
        return datetime.fromtimestamp(
            float(valor),
            tz=dt_timezone.utc,
        )
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _autorizado(request):
    esperado = getattr(
        settings,
        "BAMBU_BRIDGE_TOKEN",
        "",
    )

    if not esperado:
        return False, "not_configured"

    authorization = request.headers.get(
        "Authorization",
        "",
    )

    prefijo = "Bearer "
    if not authorization.startswith(prefijo):
        return False, "invalid"

    recibido = authorization[len(prefijo):].strip()

    if not recibido:
        return False, "invalid"

    return (
        hmac.compare_digest(recibido, esperado),
        "invalid",
    )


@csrf_exempt
@require_POST
def bambu_bridge_sync(request):
    autorizado, motivo = _autorizado(request)

    if not autorizado:
        if motivo == "not_configured":
            return JsonResponse(
                {
                    "ok": False,
                    "detail": "Bambu bridge no configurado.",
                },
                status=503,
            )

        return JsonResponse(
            {
                "ok": False,
                "detail": "No autorizado.",
            },
            status=401,
        )

    try:
        payload = json.loads(
            request.body.decode("utf-8")
        )
    except (UnicodeDecodeError, json.JSONDecodeError):
        return JsonResponse(
            {
                "ok": False,
                "detail": "JSON inválido.",
            },
            status=400,
        )

    if not isinstance(payload, dict):
        return JsonResponse(
            {
                "ok": False,
                "detail": "Payload inválido.",
            },
            status=400,
        )

    impresoras = payload.get("printers")

    if not isinstance(impresoras, list):
        return JsonResponse(
            {
                "ok": False,
                "detail": "printers debe ser una lista.",
            },
            status=400,
        )

    actualizadas = []

    with transaction.atomic():
        for item in impresoras:
            if not isinstance(item, dict):
                continue

            serial = str(
                item.get("serial") or ""
            ).strip()

            if not serial:
                continue

            progreso = _numero_entero(
                item.get("progress"),
                minimo=0,
                maximo=100,
            )

            minutos_restantes = _numero_entero(
                item.get("remaining_minutes"),
                minimo=0,
            )

            defaults = {
                "nombre_bridge": str(
                    item.get("name") or ""
                )[:100],
                "ip": (
                    str(item.get("ip")).strip()
                    if item.get("ip")
                    else None
                ),
                "conectada": bool(
                    item.get("connected")
                ),
                "estado": str(
                    item.get("status") or ""
                )[:50],
                "progreso": progreso,
                "minutos_restantes": minutos_restantes,
                "trabajo": str(
                    item.get("job_name") or ""
                )[:255],
                "temperatura_nozzle": _numero_float(
                    item.get("nozzle_temp")
                ),
                "temperatura_bed": _numero_float(
                    item.get("bed_temp")
                ),
                "wifi": str(
                    item.get("wifi") or ""
                )[:32],
                "ultimo_evento_impresora": _fecha_epoch(
                    item.get("last_update")
                ),
                "payload": item,
            }

            estado, _ = (
                ImpresoraEstadoBambu.objects.update_or_create(
                    serial=serial,
                    defaults=defaults,
                )
            )

            actualizadas.append(
                {
                    "serial": estado.serial,
                    "name": estado.nombre_bridge,
                }
            )

    return JsonResponse(
        {
            "ok": True,
            "updated": len(actualizadas),
            "printers": actualizadas,
            "commands": [],
        }
    )
