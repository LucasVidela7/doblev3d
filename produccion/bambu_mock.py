import math

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import (
    ComandoBambu,
    Impresora,
    ImpresoraEstadoBambu,
    Produccion,
)


MOCK_PREFIX = "MOCK-A1-QA-"

MOCK_PRINTERS = [
    {
        "name": "A1-QA-01",
        "serial": "MOCK-A1-QA-01",
        "ip": "192.0.2.11",
        "wifi": "-48dBm",
        "slots": [
            ("PLA", "FF6910FF"),
            ("PLA", "F6DA5AFF"),
            ("PLA", "0085D5FF"),
            ("PLA", "FFFFFFFF"),
        ],
        "external": ("PLA", "151515FF"),
    },
    {
        "name": "A1-QA-02",
        "serial": "MOCK-A1-QA-02",
        "ip": "192.0.2.12",
        "wifi": "-55dBm",
        "slots": [
            ("PLA", "E53935FF"),
            ("PLA", "43A047FF"),
            ("PETG", "8E8E93FF"),
            ("PLA", "8E44ADFF"),
        ],
        "external": ("PLA", "F5F5F5FF"),
    },
]

FORCED_ACTIONS = {
    "AUTO",
    "AVAILABLE",
    "PREPARE",
    "RUNNING",
    "PAUSE",
    "ERROR",
    "OFFLINE",
    "FINISH",
}


def enabled():
    return bool(
        getattr(
            settings,
            "BAMBU_MOCK_ENABLED",
            False,
        )
    )


def _require_enabled():
    if not enabled():
        raise RuntimeError(
            "El simulador Bambu está deshabilitado."
        )

    if not getattr(
        settings,
        "IS_QA",
        False,
    ):
        raise RuntimeError(
            "El simulador Bambu solo puede ejecutarse en QA."
        )


def is_mock_state(estado):
    return bool(
        estado
        and str(
            estado.serial or ""
        ).startswith(MOCK_PREFIX)
    )


def _ams_payload(slots):
    trays = []

    for tray_id, (material, color) in enumerate(
        slots
    ):
        trays.append(
            {
                "id": str(tray_id),
                "state": 3,
                "remain": 100,
                "tag_uid": (
                    f"MOCKRFID{tray_id:02d}"
                ),
                "tray_info_idx": "GFL99",
                "tray_type": material,
                "tray_color": color,
                "nozzle_temp_max": "240",
                "nozzle_temp_min": "190",
            }
        )

    return {
        "ams": [
            {
                "id": "0",
                "tray": trays,
            }
        ],
        "ams_exist_bits": "1",
        "tray_exist_bits": "f",
        "tray_is_bbl_bits": "f",
        "tray_tar": "255",
        "tray_now": "255",
        "tray_pre": "255",
    }


def _external_payload(material, color):
    return {
        "id": "254",
        "tray_type": material,
        "tray_color": color,
        "remain": 100,
        "tag_uid": "MOCKEXTERNAL",
    }


def _mock_payload(estado=None):
    payload = (
        dict(estado.payload)
        if (
            estado
            and isinstance(
                estado.payload,
                dict,
            )
        )
        else {}
    )

    mock = payload.get("mock")

    if not isinstance(mock, dict):
        mock = {}

    mock.setdefault("enabled", True)
    mock.setdefault("forced", "")
    mock.setdefault("phase", "idle")
    mock.setdefault("scenario_seconds", 60)

    payload["mock"] = mock

    return payload


@transaction.atomic
def ensure_printers():
    _require_enabled()

    estados = []

    for definition in MOCK_PRINTERS:
        impresora, _ = (
            Impresora.objects.get_or_create(
                nombre=definition["name"],
                defaults={
                    "activa": True,
                },
            )
        )

        if not impresora.activa:
            impresora.activa = True
            impresora.save(
                update_fields=["activa"]
            )

        estado, created = (
            ImpresoraEstadoBambu.objects
            .get_or_create(
                serial=definition["serial"],
                defaults={
                    "impresora": impresora,
                    "nombre_bridge": definition[
                        "name"
                    ],
                    "ip": definition["ip"],
                    "conectada": True,
                    "estado": "FINISH",
                    "progreso": 100,
                    "minutos_restantes": 0,
                    "trabajo": "",
                    "temperatura_nozzle": 24,
                    "temperatura_bed": 23,
                    "wifi": definition["wifi"],
                    "ams": _ams_payload(
                        definition["slots"]
                    ),
                    "carrete_externo":
                        _external_payload(
                            *definition["external"]
                        ),
                    "payload": {
                        "mock": {
                            "enabled": True,
                            "forced": "",
                            "phase": "idle",
                            "scenario_seconds": 60,
                        },
                        "print_error": 0,
                        "fail_reason": None,
                    },
                },
            )
        )

        fields = []

        if estado.impresora_id != impresora.id:
            estado.impresora = impresora
            fields.append("impresora")

        if estado.nombre_bridge != definition["name"]:
            estado.nombre_bridge = definition["name"]
            fields.append("nombre_bridge")

        if str(estado.ip or "") != definition["ip"]:
            estado.ip = definition["ip"]
            fields.append("ip")

        # Solo inicializamos AMS/payload si todavía no era un mock.
        payload = _mock_payload(estado)
        was_mock = bool(
            isinstance(
                estado.payload,
                dict,
            )
            and isinstance(
                estado.payload.get("mock"),
                dict,
            )
            and estado.payload.get(
                "mock",
                {}
            ).get("enabled")
        )

        if created or not was_mock:
            estado.ams = _ams_payload(
                definition["slots"]
            )
            estado.carrete_externo = (
                _external_payload(
                    *definition["external"]
                )
            )
            estado.payload = payload
            estado.conectada = True
            estado.estado = "FINISH"
            estado.progreso = 100
            estado.minutos_restantes = 0
            estado.trabajo = ""
            estado.temperatura_nozzle = 24
            estado.temperatura_bed = 23
            estado.wifi = definition["wifi"]

            fields.extend(
                [
                    "ams",
                    "carrete_externo",
                    "payload",
                    "conectada",
                    "estado",
                    "progreso",
                    "minutos_restantes",
                    "trabajo",
                    "temperatura_nozzle",
                    "temperatura_bed",
                    "wifi",
                ]
            )

        if fields:
            estado.save(
                update_fields=list(
                    dict.fromkeys(fields)
                )
            )

        estados.append(estado)

    return estados


def _active_production(estado):
    if not estado.impresora_id:
        return None

    return (
        Produccion.objects
        .filter(
            impresora_id=estado.impresora_id,
            estado="IMPRIMIENDO",
        )
        .order_by(
            "-inicio_impresion",
            "-id",
        )
        .first()
    )


def _finish_production(
    produccion,
    *,
    event="FINALIZADA_MOCK",
):
    if not produccion:
        return

    if produccion.estado in {
        "PENDIENTE",
        "IMPRIMIENDO",
    }:
        produccion.estado = "CONTROL"
        produccion.fin_impresion_detectado = (
            timezone.now()
        )
        produccion.evento_fin_bambu = event
        produccion.resultado_control = ""
        produccion.save(
            update_fields=[
                "estado",
                "fin_impresion_detectado",
                "evento_fin_bambu",
                "resultado_control",
            ]
        )


def _apply_forced(
    estado,
    forced,
    payload,
):
    now = timezone.now()
    produccion = _active_production(
        estado
    )

    estado.wifi = estado.wifi or "-50dBm"
    estado.ultimo_evento_impresora = now

    payload["print_error"] = 0
    payload["fail_reason"] = None

    if forced == "OFFLINE":
        estado.conectada = False
        estado.estado = ""
        estado.progreso = None
        estado.minutos_restantes = None
        estado.temperatura_nozzle = None
        estado.temperatura_bed = None

    elif forced == "ERROR":
        estado.conectada = True
        estado.estado = "FAILED"
        estado.progreso = (
            estado.progreso
            if estado.progreso is not None
            else 42
        )
        estado.minutos_restantes = 0
        estado.temperatura_nozzle = 205
        estado.temperatura_bed = 55
        payload["print_error"] = 999001
        payload["fail_reason"] = (
            "Error simulado de QA"
        )
        _finish_production(
            produccion,
            event="ERROR_MOCK",
        )

    elif forced == "PAUSE":
        estado.conectada = True
        estado.estado = "PAUSE"
        estado.progreso = (
            estado.progreso
            if estado.progreso is not None
            else 42
        )
        estado.minutos_restantes = 3
        estado.temperatura_nozzle = 220
        estado.temperatura_bed = 60
        estado.trabajo = (
            estado.trabajo
            or "MOCK_demo.gcode.3mf"
        )

    elif forced == "PREPARE":
        estado.conectada = True
        estado.estado = "PREPARE"
        estado.progreso = 0
        estado.minutos_restantes = 5
        estado.temperatura_nozzle = 150
        estado.temperatura_bed = 45
        estado.trabajo = (
            estado.trabajo
            or "MOCK_demo.gcode.3mf"
        )

    elif forced == "RUNNING":
        estado.conectada = True
        estado.estado = "RUNNING"
        estado.progreso = 42
        estado.minutos_restantes = 3
        estado.temperatura_nozzle = 220
        estado.temperatura_bed = 60
        estado.trabajo = (
            estado.trabajo
            or "MOCK_demo.gcode.3mf"
        )

    elif forced == "FINISH":
        estado.conectada = True
        estado.estado = "FINISH"
        estado.progreso = 100
        estado.minutos_restantes = 0
        estado.temperatura_nozzle = 35
        estado.temperatura_bed = 30
        _finish_production(
            produccion,
        )

    else:
        # AVAILABLE
        estado.conectada = True
        estado.estado = "FINISH"
        estado.progreso = 100
        estado.minutos_restantes = 0
        estado.trabajo = ""
        estado.temperatura_nozzle = 24
        estado.temperatura_bed = 23

    payload["mock"]["phase"] = (
        forced.lower()
    )


def _process_stop(
    estado,
    payload,
    now,
):
    comando = (
        ComandoBambu.objects
        .filter(
            impresora_estado=estado,
            tipo="STOP",
            estado="PENDIENTE",
        )
        .select_related("produccion")
        .order_by(
            "creado_en",
            "id",
        )
        .first()
    )

    if not comando:
        return False

    elapsed = (
        now - comando.creado_en
    ).total_seconds()

    payload["mock"]["phase"] = (
        "stopping"
    )

    if elapsed < 2:
        return True

    comando.estado = "EJECUTADO"
    comando.resuelto_en = now
    comando.error = ""
    comando.save(
        update_fields=[
            "estado",
            "resuelto_en",
            "error",
        ]
    )

    produccion = comando.produccion

    if (
        produccion
        and produccion.estado
        == "IMPRIMIENDO"
    ):
        produccion.estado = "CANCELADO"
        produccion.fin_impresion_detectado = now
        produccion.evento_fin_bambu = (
            "CANCELADA_USUARIO_MOCK"
        )
        produccion.save(
            update_fields=[
                "estado",
                "fin_impresion_detectado",
                "evento_fin_bambu",
            ]
        )

    estado.conectada = True
    estado.estado = "CANCELLED"
    estado.progreso = (
        estado.progreso
        if estado.progreso is not None
        else 0
    )
    estado.minutos_restantes = 0
    estado.temperatura_nozzle = 80
    estado.temperatura_bed = 40

    return True


def _process_print(
    estado,
    payload,
    now,
):
    comando = (
        ComandoBambu.objects
        .filter(
            impresora_estado=estado,
            tipo="PRINT",
            estado__in=[
                "PENDIENTE",
                "EJECUTADO",
            ],
            produccion__estado__in=[
                "PENDIENTE",
                "IMPRIMIENDO",
            ],
        )
        .select_related(
            "produccion",
        )
        .order_by(
            "-creado_en",
            "-id",
        )
        .first()
    )

    if not comando:
        payload["mock"]["phase"] = "idle"

        if estado.estado not in {
            "FAILED",
            "CANCELLED",
        }:
            estado.conectada = True
            estado.estado = "FINISH"
            estado.progreso = 100
            estado.minutos_restantes = 0
            estado.trabajo = ""
            estado.temperatura_nozzle = 24
            estado.temperatura_bed = 23

        return

    produccion = comando.produccion

    elapsed = max(
        0.0,
        (
            now - comando.creado_en
        ).total_seconds(),
    )

    remote_name = (
        comando.trabajo_bambu_esperado
        or (
            f"MOCK_{produccion.codigo}.gcode.3mf"
            if produccion
            else "MOCK_print.gcode.3mf"
        )
    )

    estado.conectada = True
    estado.trabajo = remote_name

    if elapsed < 4:
        payload["mock"]["phase"] = "waiting"
        estado.estado = "FINISH"
        estado.progreso = 0
        estado.minutos_restantes = 1
        estado.temperatura_nozzle = 24
        estado.temperatura_bed = 23
        return

    if elapsed < 14:
        payload["mock"]["phase"] = "transferring"
        estado.estado = "FINISH"
        estado.progreso = 0
        estado.minutos_restantes = 1
        estado.temperatura_nozzle = 24
        estado.temperatura_bed = 23
        return

    if comando.estado == "PENDIENTE":
        comando.estado = "EJECUTADO"
        comando.resuelto_en = now
        comando.error = ""
        comando.save(
            update_fields=[
                "estado",
                "resuelto_en",
                "error",
            ]
        )

        if produccion:
            produccion.bambu_trabajo = (
                remote_name[:255]
            )
            produccion.save(
                update_fields=[
                    "bambu_trabajo",
                ]
            )

    if elapsed < 20:
        payload["mock"]["phase"] = "confirming"
        estado.estado = "PREPARE"
        estado.progreso = 0
        estado.minutos_restantes = 1
        estado.temperatura_nozzle = 150
        estado.temperatura_bed = 45
        return

    if produccion and produccion.estado == "PENDIENTE":
        produccion.estado = "IMPRIMIENDO"
        produccion.inicio_impresion = now
        produccion.bambu_trabajo = (
            remote_name[:255]
        )
        produccion.save(
            update_fields=[
                "estado",
                "inicio_impresion",
                "bambu_trabajo",
            ]
        )

    if elapsed < 60:
        payload["mock"]["phase"] = "printing"

        progreso = int(
            max(
                0,
                min(
                    99,
                    (
                        (elapsed - 20)
                        / 40
                    )
                    * 100,
                ),
            )
        )

        estado.estado = "RUNNING"
        estado.progreso = progreso
        estado.minutos_restantes = max(
            1,
            int(
                math.ceil(
                    (60 - elapsed)
                    / 10
                )
            ),
        )
        estado.temperatura_nozzle = 220
        estado.temperatura_bed = 60
        return

    payload["mock"]["phase"] = "finished"

    estado.estado = "FINISH"
    estado.progreso = 100
    estado.minutos_restantes = 0
    estado.temperatura_nozzle = 35
    estado.temperatura_bed = 30

    _finish_production(
        produccion,
    )


@transaction.atomic
def tick():
    if not enabled():
        return []

    _require_enabled()

    estados = ensure_printers()
    now = timezone.now()

    for estado in estados:
        estado = (
            ImpresoraEstadoBambu.objects
            .select_for_update()
            .get(pk=estado.pk)
        )

        payload = _mock_payload(estado)
        forced = str(
            payload.get(
                "mock",
                {},
            ).get(
                "forced",
                "",
            )
            or ""
        ).strip().upper()

        if forced:
            _apply_forced(
                estado,
                forced,
                payload,
            )
        else:
            if not _process_stop(
                estado,
                payload,
                now,
            ):
                _process_print(
                    estado,
                    payload,
                    now,
                )

        estado.payload = payload
        estado.ultimo_evento_impresora = now

        estado.save(
            update_fields=[
                "conectada",
                "estado",
                "progreso",
                "minutos_restantes",
                "trabajo",
                "temperatura_nozzle",
                "temperatura_bed",
                "wifi",
                "payload",
                "ultimo_evento_impresora",
            ]
        )

    return estados


@transaction.atomic
def set_forced_state(
    serial,
    action,
):
    _require_enabled()

    action = str(
        action or ""
    ).strip().upper()

    if action not in FORCED_ACTIONS:
        raise ValueError(
            "Estado mock no válido."
        )

    ensure_printers()

    estado = (
        ImpresoraEstadoBambu.objects
        .select_for_update()
        .filter(
            serial=serial,
        )
        .first()
    )

    if not is_mock_state(estado):
        raise ValueError(
            "La impresora indicada no es un mock de QA."
        )

    payload = _mock_payload(estado)

    payload["mock"]["forced"] = (
        ""
        if action == "AUTO"
        else action
    )

    if action == "AUTO":
        payload["mock"]["phase"] = "auto"

    estado.payload = payload
    estado.save(
        update_fields=["payload"]
    )

    tick()

    return estado


def summary():
    if not enabled():
        return []

    estados = tick()
    result = []

    for estado in estados:
        payload = _mock_payload(estado)
        mock = payload.get(
            "mock",
            {},
        )

        result.append(
            {
                "id": estado.id,
                "serial": estado.serial,
                "name": (
                    estado.nombre_bridge
                    or estado.serial
                ),
                "connected": estado.conectada,
                "state": estado.estado or "OFFLINE",
                "progress": estado.progreso,
                "job": estado.trabajo,
                "forced": (
                    mock.get("forced")
                    or "AUTO"
                ),
                "phase": (
                    mock.get("phase")
                    or "idle"
                ),
            }
        )

    return result
