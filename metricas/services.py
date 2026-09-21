import hashlib
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from kits.models import Kit
from productos.models import Producto

from .models import EventoCatalogo, MetricasConfiguracion


CONFIG_CACHE_KEY = "dv-metricas-config-v1"
CLEANUP_CACHE_KEY = "dv-metricas-cleanup-v1"


def configuracion_metricas():
    config = cache.get(CONFIG_CACHE_KEY)
    if config is None:
        config, _ = MetricasConfiguracion.objects.get_or_create(pk=1)
        cache.set(CONFIG_CACHE_KEY, config, 60)
    return config


def invalidar_configuracion_metricas():
    cache.delete(CONFIG_CACHE_KEY)


def _hash_id(valor):
    valor = str(valor or "").strip()
    if not valor:
        return ""
    return hashlib.sha256(
        f"{settings.SECRET_KEY}:metricas:{valor}".encode("utf-8")
    ).hexdigest()


def _dispositivo(request):
    ua = (request.META.get("HTTP_USER_AGENT") or "").lower()
    if "ipad" in ua or "tablet" in ua:
        return "TABLET"
    if (
        "mobile" in ua
        or "android" in ua
        or "iphone" in ua
        or "ipod" in ua
    ):
        return "MOBILE"
    if ua:
        return "DESKTOP"
    return "OTHER"


def _es_bot(request):
    ua = (request.META.get("HTTP_USER_AGENT") or "").lower()
    marcas = (
        "bot",
        "crawler",
        "spider",
        "slurp",
        "headless",
        "lighthouse",
        "facebookexternalhit",
        "whatsapp",
    )
    return any(marca in ua for marca in marcas)


def _limpiar_antiguas(config):
    if not cache.add(CLEANUP_CACHE_KEY, True, timeout=60 * 60 * 24):
        return
    limite = timezone.now() - timedelta(
        days=max(30, min(int(config.retencion_dias or 180), 365))
    )
    EventoCatalogo.objects.filter(creada_en__lt=limite).delete()


def registrar_evento_request(
    request,
    evento,
    *,
    pagina="",
    contenido_tipo="",
    contenido_id=None,
    ruta="",
    origen="",
):
    config = configuracion_metricas()
    if not config.activas or _es_bot(request):
        return None

    visitor_raw = (
        request.COOKIES.get("dv_visitor_id")
        or ""
    )
    session_raw = (
        request.COOKIES.get("dv_session_id")
        or ""
    )

    if not visitor_raw:
        session_key = getattr(request.session, "session_key", "") or ""
        visitor_raw = session_key
    if not session_raw:
        session_raw = visitor_raw

    visitor_hash = _hash_id(visitor_raw)
    session_hash = _hash_id(session_raw)

    if not visitor_hash and evento != EventoCatalogo.PAGE_VIEW:
        return None

    origen = (origen or request.COOKIES.get("dv_metric_source") or "Directo")
    origen = str(origen).strip()[:120] or "Directo"

    evento_obj = EventoCatalogo.objects.create(
        evento=evento,
        visitor_hash=visitor_hash,
        session_hash=session_hash,
        pagina=str(pagina or "")[:40],
        contenido_tipo=str(contenido_tipo or "").upper()[:20],
        contenido_id=contenido_id if str(contenido_id or "").isdigit() else None,
        dispositivo=_dispositivo(request),
        origen=origen,
        ruta=str(ruta or request.path or "")[:255],
    )

    _limpiar_antiguas(config)
    return evento_obj


def _porcentaje(parte, total):
    if not total:
        return 0
    return round((parte / total) * 100, 1)


def resumen_metricas(periodo=30):
    periodo = periodo if periodo in {7, 30, 90} else 30
    hoy = timezone.localdate()
    desde_fecha = hoy - timedelta(days=periodo - 1)
    desde = timezone.make_aware(
        datetime.combine(
            desde_fecha,
            time.min,
        )
    )

    qs = EventoCatalogo.objects.filter(creada_en__gte=desde)

    visitantes = (
        qs.exclude(visitor_hash="")
        .values("visitor_hash")
        .distinct()
        .count()
    )
    sesiones = (
        qs.exclude(session_hash="")
        .values("session_hash")
        .distinct()
        .count()
    )
    vistas = qs.filter(evento=EventoCatalogo.PAGE_VIEW).count()
    agregados = qs.filter(evento=EventoCatalogo.ADD_TO_CART).count()
    checkouts = qs.filter(evento=EventoCatalogo.CHECKOUT_START).count()
    solicitudes = qs.filter(evento=EventoCatalogo.SOLICITUD).count()
    whatsapp = qs.filter(evento=EventoCatalogo.WHATSAPP).count()
    instagram = qs.filter(evento=EventoCatalogo.INSTAGRAM).count()

    sesiones_detalle = (
        qs.filter(
            evento=EventoCatalogo.PAGE_VIEW,
            contenido_tipo__in=["PRODUCTO", "KIT"],
        )
        .exclude(session_hash="")
        .values("session_hash")
        .distinct()
        .count()
    )
    sesiones_carrito = (
        qs.filter(evento=EventoCatalogo.ADD_TO_CART)
        .exclude(session_hash="")
        .values("session_hash")
        .distinct()
        .count()
    )
    sesiones_checkout = (
        qs.filter(evento=EventoCatalogo.CHECKOUT_START)
        .exclude(session_hash="")
        .values("session_hash")
        .distinct()
        .count()
    )
    sesiones_solicitud = (
        qs.filter(evento=EventoCatalogo.SOLICITUD)
        .exclude(session_hash="")
        .values("session_hash")
        .distinct()
        .count()
    )

    base_funnel = max(sesiones, 1)
    funnel = [
        {
            "label": "Visitas",
            "valor": sesiones,
            "pct": 100 if sesiones else 0,
        },
        {
            "label": "Vieron producto / kit",
            "valor": sesiones_detalle,
            "pct": _porcentaje(sesiones_detalle, sesiones),
        },
        {
            "label": "Agregaron al carrito",
            "valor": sesiones_carrito,
            "pct": _porcentaje(sesiones_carrito, sesiones),
        },
        {
            "label": "Llegaron al checkout",
            "valor": sesiones_checkout,
            "pct": _porcentaje(sesiones_checkout, sesiones),
        },
        {
            "label": "Enviaron solicitud",
            "valor": sesiones_solicitud,
            "pct": _porcentaje(sesiones_solicitud, sesiones),
        },
    ]
    for item in funnel:
        item["ancho"] = max(
            4 if item["valor"] else 0,
            round((item["valor"] / base_funnel) * 100, 1),
        )

    diarios_raw = (
        qs.annotate(dia=TruncDate("creada_en"))
        .values("dia")
        .annotate(
            sesiones=Count(
                "session_hash",
                distinct=True,
                filter=~Q(session_hash=""),
            ),
            solicitudes=Count(
                "id",
                filter=Q(evento=EventoCatalogo.SOLICITUD),
            ),
        )
        .order_by("dia")
    )
    diarios_map = {
        fila["dia"]: fila
        for fila in diarios_raw
    }

    diarios = []
    max_diario = 1
    for offset in range(periodo):
        dia = desde_fecha + timedelta(days=offset)
        fila = diarios_map.get(dia, {})
        visitas_dia = int(fila.get("sesiones") or 0)
        solicitudes_dia = int(fila.get("solicitudes") or 0)
        max_diario = max(max_diario, visitas_dia)
        paso_label = 1 if periodo == 7 else (5 if periodo == 30 else 15)
        diarios.append(
            {
                "dia": dia,
                "sesiones": visitas_dia,
                "solicitudes": solicitudes_dia,
                "mostrar_label": (
                    offset == 0
                    or offset == periodo - 1
                    or offset % paso_label == 0
                ),
            }
        )

    for fila in diarios:
        fila["alto"] = max(
            3 if fila["sesiones"] else 0,
            round((fila["sesiones"] / max_diario) * 100, 1),
        )
        fila["alto_solicitudes"] = max(
            4 if fila["solicitudes"] else 0,
            round((fila["solicitudes"] / max_diario) * 100, 1),
        )

    dispositivos_raw = list(
        qs.filter(evento=EventoCatalogo.PAGE_VIEW)
        .values("dispositivo")
        .annotate(total=Count("id"))
        .order_by("-total")
    )
    total_dispositivos = sum(int(x["total"]) for x in dispositivos_raw) or 1
    etiquetas_dispositivo = {
        "MOBILE": "Móvil",
        "TABLET": "Tablet",
        "DESKTOP": "PC",
        "OTHER": "Otro",
    }
    dispositivos = [
        {
            "label": etiquetas_dispositivo.get(x["dispositivo"], "Otro"),
            "total": int(x["total"]),
            "pct": _porcentaje(int(x["total"]), total_dispositivos),
        }
        for x in dispositivos_raw
    ]

    origenes_raw = list(
        qs.exclude(session_hash="")
        .values("origen")
        .annotate(total=Count("session_hash", distinct=True))
        .order_by("-total")[:6]
    )
    origenes = [
        {
            "label": x["origen"] or "Directo",
            "total": int(x["total"]),
            "pct": _porcentaje(int(x["total"]), max(sesiones, 1)),
        }
        for x in origenes_raw
    ]

    ranking_raw = list(
        qs.filter(
            contenido_tipo__in=["PRODUCTO", "KIT"],
            contenido_id__isnull=False,
        )
        .values("contenido_tipo", "contenido_id")
        .annotate(
            vistas=Count(
                "id",
                filter=Q(evento=EventoCatalogo.PAGE_VIEW),
            ),
            agregados=Count(
                "id",
                filter=Q(evento=EventoCatalogo.ADD_TO_CART),
            ),
        )
        .order_by("-vistas", "-agregados")[:12]
    )

    producto_ids = [
        x["contenido_id"]
        for x in ranking_raw
        if x["contenido_tipo"] == "PRODUCTO"
    ]
    kit_ids = [
        x["contenido_id"]
        for x in ranking_raw
        if x["contenido_tipo"] == "KIT"
    ]
    nombres_productos = dict(
        Producto.objects.filter(id__in=producto_ids)
        .values_list("id", "nombre")
    )
    nombres_kits = dict(
        Kit.objects.filter(id__in=kit_ids)
        .values_list("id", "nombre")
    )

    ranking = []
    for fila in ranking_raw:
        es_producto = fila["contenido_tipo"] == "PRODUCTO"
        nombre = (
            nombres_productos.get(fila["contenido_id"])
            if es_producto
            else nombres_kits.get(fila["contenido_id"])
        ) or f'{fila["contenido_tipo"].title()} #{fila["contenido_id"]}'
        ranking.append(
            {
                "tipo": "Producto" if es_producto else "Kit",
                "nombre": nombre,
                "vistas": int(fila["vistas"]),
                "agregados": int(fila["agregados"]),
                "tasa": _porcentaje(
                    int(fila["agregados"]),
                    int(fila["vistas"]),
                ),
            }
        )

    return {
        "periodo": periodo,
        "desde": desde_fecha,
        "hasta": hoy,
        "visitantes": visitantes,
        "sesiones": sesiones,
        "vistas": vistas,
        "agregados": agregados,
        "checkouts": checkouts,
        "solicitudes": solicitudes,
        "whatsapp": whatsapp,
        "instagram": instagram,
        "conversion": _porcentaje(sesiones_solicitud, sesiones),
        "tasa_carrito": _porcentaje(sesiones_carrito, sesiones),
        "funnel": funnel,
        "diarios": diarios,
        "dispositivos": dispositivos,
        "origenes": origenes,
        "ranking": ranking,
        "total_eventos": qs.count(),
    }
