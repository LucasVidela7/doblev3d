import hmac
import json
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from pedidos.push import enviar_push_operativo

from .models import (
    ComandoBambu,
    ConfiguracionProduccion,
    EventoBambu,
    ImpresoraEstadoBambu,
    Produccion,
)


ESTADOS_IMPRIMIENDO = {
    "RUNNING",
    "PAUSE",
    "PREPARE",
}

ESTADOS_FINALIZADOS = {
    "FINISH",
    "COMPLETED",
    "SUCCESS",
}

ESTADOS_CANCELADOS = {
    "FAILED",
    "CANCELLED",
    "CANCELED",
}


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


def _procesar_resultados_comandos(resultados):
    if not isinstance(resultados, list):
        return

    for item in resultados:
        if not isinstance(item, dict):
            continue

        id_comando = str(
            item.get("command_id") or ""
        ).strip()

        if not id_comando:
            continue

        comando = (
            ComandoBambu.objects
            .select_for_update()
            .filter(
                id_comando=id_comando,
                estado="PENDIENTE",
            )
            .select_related(
                "produccion",
            )
            .first()
        )

        if not comando:
            continue

        ok = bool(item.get("ok"))

        comando.estado = (
            "EJECUTADO"
            if ok
            else "ERROR"
        )
        comando.resuelto_en = timezone.now()
        comando.error = (
            ""
            if ok
            else str(
                item.get("error")
                or "No se pudo ejecutar el comando."
            )[:2000]
        )
        comando.save(
            update_fields=[
                "estado",
                "resuelto_en",
                "error",
            ]
        )

        if (
            comando.produccion_id
            and comando.tipo == "STOP"
        ):
            Produccion.objects.filter(
                id=comando.produccion_id,
                estado="IMPRIMIENDO",
            ).update(
                evento_fin_bambu=(
                    "CANCELACION_ENVIADA"
                    if ok
                    else "CANCELACION_ERROR"
                )
            )


def _produccion_activa(estado_bambu):
    if not estado_bambu.impresora_id:
        return None

    return (
        Produccion.objects
        .select_for_update()
        .filter(
            impresora_id=estado_bambu.impresora_id,
            estado="IMPRIMIENDO",
        )
        .select_related(
            "producto",
            "impresora",
        )
        .order_by(
            "-inicio_impresion",
            "-id",
        )
        .first()
    )


def _registrar_evento(
    *,
    tipo,
    estado_bambu,
    produccion,
    item,
):
    if not produccion:
        return False

    clave = f"{tipo}:{produccion.id}"

    _, creado = EventoBambu.objects.get_or_create(
        clave=clave,
        defaults={
            "tipo": tipo,
            "impresora_estado": estado_bambu,
            "produccion": produccion,
            "payload": item,
        },
    )

    return creado


def _payload_push(
    *,
    tipo,
    estado_bambu,
    produccion,
    minutos=None,
):
    impresora = (
        produccion.impresora.nombre
        if produccion and produccion.impresora
        else (
            estado_bambu.nombre_bridge
            or estado_bambu.serial
        )
    )

    producto = (
        produccion.producto.nombre
        if produccion
        else (
            estado_bambu.trabajo
            or "Impresión"
        )
    )

    if tipo == "PROXIMO_FIN":
        title = "Impresión por terminar"
        body = (
            f"{impresora} · {producto} · "
            f"quedan aprox. {minutos} min."
        )
        tag = (
            f"bambu-proximo-fin-"
            f"{produccion.id if produccion else estado_bambu.id}"
        )
    elif tipo == "FINALIZADA":
        title = "Impresión finalizada"
        body = (
            f"{impresora} · {producto}. "
            "Pendiente de control de calidad; "
            "todavía no se agregó stock."
        )
        tag = (
            f"bambu-finalizada-"
            f"{produccion.id if produccion else estado_bambu.id}"
        )
    else:
        title = "Impresión interrumpida"
        body = (
            f"{impresora} · {producto}. "
            "Revisá la pieza antes de decidir si reimprimir."
        )
        tag = (
            f"bambu-cancelada-"
            f"{produccion.id if produccion else estado_bambu.id}"
        )

    return {
        "title": title,
        "body": body,
        "url": reverse("produccion:lista") + "#prod-control",
        "tag": tag,
        "icon": "/static/brand/apple-touch-icon.png",
        "badge": "/static/brand/favicon.ico",
    }


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

    command_results = payload.get(
        "command_results",
        []
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
    notificaciones = []

    with transaction.atomic():
        config, _ = (
            ConfiguracionProduccion.objects
            .get_or_create(pk=1)
        )

        _procesar_resultados_comandos(
            command_results
        )

        for item in impresoras:
            if not isinstance(item, dict):
                continue

            serial = str(
                item.get("serial") or ""
            ).strip()

            if not serial:
                continue

            existente = (
                ImpresoraEstadoBambu.objects
                .select_for_update()
                .filter(serial=serial)
                .first()
            )

            estado_anterior = (
                (existente.estado or "").strip().upper()
                if existente
                else ""
            )

            progreso = _numero_entero(
                item.get("progress"),
                minimo=0,
                maximo=100,
            )

            minutos_restantes = _numero_entero(
                item.get("remaining_minutes"),
                minimo=0,
            )

            estado_actual = str(
                item.get("status") or ""
            ).strip().upper()[:50]

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
                "estado": estado_actual,
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
                "ams": (
                    item.get("ams")
                    if isinstance(item.get("ams"), (dict, list))
                    else {}
                ),
                "carrete_externo": (
                    item.get("external_spool")
                    if isinstance(
                        item.get("external_spool"),
                        dict,
                    )
                    else {}
                ),
                "payload": item,
            }

            estado, _ = (
                ImpresoraEstadoBambu.objects.update_or_create(
                    serial=serial,
                    defaults=defaults,
                )
            )

            produccion = _produccion_activa(
                estado
            )

            if produccion:
                cancelacion_solicitada = (
                    produccion.evento_fin_bambu
                    in {
                        "CANCELACION_SOLICITADA",
                        "CANCELACION_ENVIADA",
                    }
                )

                if (
                    cancelacion_solicitada
                    and estado_actual
                    and estado_actual
                    not in ESTADOS_IMPRIMIENDO
                ):
                    produccion.estado = "CANCELADO"
                    produccion.fin_impresion_detectado = (
                        timezone.now()
                    )
                    produccion.evento_fin_bambu = (
                        "CANCELADA_USUARIO"
                    )
                    produccion.resultado_control = ""
                    produccion.save(
                        update_fields=[
                            "estado",
                            "fin_impresion_detectado",
                            "evento_fin_bambu",
                            "resultado_control",
                        ]
                    )

                    if (
                        config.avisos_impresion_activos
                        and config.avisar_cancelacion
                        and _registrar_evento(
                            tipo="CANCELADA",
                            estado_bambu=estado,
                            produccion=produccion,
                            item=item,
                        )
                    ):
                        notificaciones.append(
                            _payload_push(
                                tipo="CANCELADA",
                                estado_bambu=estado,
                                produccion=produccion,
                            )
                        )

                elif (
                    estado_actual in ESTADOS_FINALIZADOS
                    and produccion.estado == "IMPRIMIENDO"
                ):
                    produccion.estado = "CONTROL"
                    produccion.fin_impresion_detectado = (
                        timezone.now()
                    )
                    produccion.evento_fin_bambu = (
                        "FINALIZADA"
                    )
                    produccion.resultado_control = ""
                    produccion.save(
                        update_fields=[
                            "estado",
                            "fin_impresion_detectado",
                            "evento_fin_bambu",
                            "resultado_control",
                        ]
                    )

                    if (
                        config.avisos_impresion_activos
                        and config.avisar_finalizacion
                        and _registrar_evento(
                            tipo="FINALIZADA",
                            estado_bambu=estado,
                            produccion=produccion,
                            item=item,
                        )
                    ):
                        notificaciones.append(
                            _payload_push(
                                tipo="FINALIZADA",
                                estado_bambu=estado,
                                produccion=produccion,
                            )
                        )

                elif (
                    estado_actual in ESTADOS_CANCELADOS
                    and produccion.estado == "IMPRIMIENDO"
                ):
                    produccion.estado = (
                        "CANCELADO"
                        if cancelacion_solicitada
                        else "CONTROL"
                    )
                    produccion.fin_impresion_detectado = (
                        timezone.now()
                    )
                    produccion.evento_fin_bambu = (
                        "CANCELADA_USUARIO"
                        if cancelacion_solicitada
                        else "CANCELADA"
                    )
                    produccion.resultado_control = ""
                    produccion.save(
                        update_fields=[
                            "estado",
                            "fin_impresion_detectado",
                            "evento_fin_bambu",
                            "resultado_control",
                        ]
                    )

                    if (
                        config.avisos_impresion_activos
                        and config.avisar_cancelacion
                        and _registrar_evento(
                            tipo="CANCELADA",
                            estado_bambu=estado,
                            produccion=produccion,
                            item=item,
                        )
                    ):
                        notificaciones.append(
                            _payload_push(
                                tipo="CANCELADA",
                                estado_bambu=estado,
                                produccion=produccion,
                            )
                        )

                elif (
                    estado_actual in ESTADOS_IMPRIMIENDO
                    and minutos_restantes is not None
                    and minutos_restantes > 0
                    and minutos_restantes
                    <= max(
                        int(
                            config.minutos_aviso_finalizacion
                            or 15
                        ),
                        1,
                    )
                    and config.avisos_impresion_activos
                    and config.avisar_antes_finalizar
                    and _registrar_evento(
                        tipo="PROXIMO_FIN",
                        estado_bambu=estado,
                        produccion=produccion,
                        item=item,
                    )
                ):
                    notificaciones.append(
                        _payload_push(
                            tipo="PROXIMO_FIN",
                            estado_bambu=estado,
                            produccion=produccion,
                            minutos=minutos_restantes,
                        )
                    )

            actualizadas.append(
                {
                    "serial": estado.serial,
                    "name": estado.nombre_bridge,
                    "previous_status": estado_anterior,
                    "status": estado.estado,
                }
            )

    for aviso in notificaciones:
        enviar_push_operativo(aviso)

    seriales = [
        item["serial"]
        for item in actualizadas
    ]

    comandos = list(
        ComandoBambu.objects
        .filter(
            estado="PENDIENTE",
            impresora_estado__serial__in=seriales,
        )
        .select_related(
            "impresora_estado",
            "produccion",
        )
        .order_by(
            "creado_en",
            "id",
        )[:20]
    )

    return JsonResponse(
        {
            "ok": True,
            "updated": len(actualizadas),
            "printers": actualizadas,
            "notifications": len(notificaciones),
            "commands": [
                {
                    "command_id": str(
                        comando.id_comando
                    ),
                    "type": comando.tipo,
                    "printer": (
                        comando.impresora_estado.nombre_bridge
                    ),
                    "serial": (
                        comando.impresora_estado.serial
                    ),
                    "production_id": (
                        comando.produccion_id
                    ),
                }
                for comando in comandos
            ],
        }
    )
