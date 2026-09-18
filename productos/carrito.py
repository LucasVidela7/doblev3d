import hashlib
import json
from collections import Counter
from datetime import timedelta
from decimal import Decimal
from urllib import parse, request as urlrequest

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from kits.economia import precio_automatico_kit_libre
from kits.models import Kit
from pedidos.models import (
    SolicitudWeb,
    SolicitudWebItem,
    SolicitudWebKitProducto,
)
from productos.models import Producto


MAX_LINEAS = 20
MAX_CANTIDAD_LINEA = 20
MAX_UNIDADES_TOTALES = 100
MAX_PAYLOAD_BYTES = 30000


def _telefono_normalizado(valor):
    return "".join(ch for ch in (valor or "") if ch.isdigit())[:30]


def _ip_cliente(request):
    forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0]
    return (forwarded or request.META.get("REMOTE_ADDR") or "").strip()


def _ip_hash(request):
    ip = _ip_cliente(request)
    if not ip:
        return ""
    return hashlib.sha256(
        f"{settings.SECRET_KEY}:{ip}".encode("utf-8")
    ).hexdigest()


def _decimal(valor):
    return Decimal(str(valor or 0))


def _parsear_payload(raw):
    if not raw:
        raise ValueError("Tu carrito está vacío.")

    if len(raw.encode("utf-8")) > MAX_PAYLOAD_BYTES:
        raise ValueError("El carrito es demasiado grande.")

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError, json.JSONDecodeError):
        raise ValueError("No pudimos leer el carrito. Actualizá la página e intentá nuevamente.")

    if not isinstance(payload, list) or not payload:
        raise ValueError("Tu carrito está vacío.")

    if len(payload) > MAX_LINEAS:
        raise ValueError(
            f"El carrito admite hasta {MAX_LINEAS} líneas por solicitud."
        )

    return payload


def _validar_carrito(payload):
    lineas = []
    unidades = 0

    for indice, bruto in enumerate(payload, start=1):
        if not isinstance(bruto, dict):
            raise ValueError(f"El ítem {indice} del carrito no es válido.")

        tipo = str(bruto.get("kind") or "").lower().strip()
        try:
            cantidad = int(bruto.get("qty") or 0)
        except (TypeError, ValueError):
            cantidad = 0

        if cantidad <= 0 or cantidad > MAX_CANTIDAD_LINEA:
            raise ValueError(
                f"Cada línea debe tener entre 1 y {MAX_CANTIDAD_LINEA} unidades."
            )

        unidades += cantidad
        if unidades > MAX_UNIDADES_TOTALES:
            raise ValueError(
                f"Una solicitud admite hasta {MAX_UNIDADES_TOTALES} unidades."
            )

        if tipo == "product":
            try:
                producto_id = int(bruto.get("id"))
            except (TypeError, ValueError):
                raise ValueError("Hay un producto inválido en el carrito.")

            producto = (
                Producto.objects
                .filter(
                    id=producto_id,
                    activo=True,
                    solo_produccion=False,
                )
                .select_related("tipo")
                .first()
            )
            if not producto:
                raise ValueError(
                    "Uno de los productos ya no está disponible en el catálogo."
                )

            precio = _decimal(producto.subtotal)
            if precio <= 0:
                raise ValueError(
                    f"{producto.nombre} no tiene un precio válido actualmente."
                )

            lineas.append(
                {
                    "tipo": "PRODUCTO",
                    "cantidad": cantidad,
                    "producto": producto,
                    "kit": None,
                    "nombre": producto.nombre,
                    "precio_base": precio,
                    "adicional": Decimal("0"),
                    "precio_unitario": precio,
                    "componentes": {},
                    "canonical": {
                        "kind": "product",
                        "id": producto.id,
                        "qty": cantidad,
                    },
                }
            )
            continue

        if tipo == "kit":
            try:
                kit_id = int(bruto.get("id"))
            except (TypeError, ValueError):
                raise ValueError("Hay un kit inválido en el carrito.")

            kit = (
                Kit.objects
                .filter(id=kit_id, activo=True)
                .select_related("tipo_producto")
                .prefetch_related("componentes__producto")
                .first()
            )
            if not kit:
                raise ValueError(
                    "Uno de los kits ya no está disponible en el catálogo."
                )

            componentes = Counter()
            seleccion_ids = []

            if kit.modalidad == "FIJO":
                componentes_fijos = list(kit.componentes.all())
                if not componentes_fijos:
                    raise ValueError(
                        f"{kit.nombre} no tiene una composición disponible."
                    )

                for componente in componentes_fijos:
                    componentes[componente.producto_id] += (
                        int(componente.cantidad) * cantidad
                    )

                precio_unitario = _decimal(kit.precio)
                if precio_unitario <= 0:
                    raise ValueError(
                        f"{kit.nombre} no tiene un precio válido actualmente."
                    )
                adicional = Decimal("0")

            else:
                bruto_selecciones = bruto.get("selections") or []
                if not isinstance(bruto_selecciones, list):
                    raise ValueError(
                        f"La selección de {kit.nombre} no es válida."
                    )

                try:
                    seleccion_ids = [
                        int(item.get("id") if isinstance(item, dict) else item)
                        for item in bruto_selecciones
                    ]
                except (TypeError, ValueError):
                    raise ValueError(
                        f"La selección de {kit.nombre} no es válida."
                    )

                cantidad_requerida = int(kit.cantidad_productos or 0)
                if len(seleccion_ids) != cantidad_requerida:
                    raise ValueError(
                        f"{kit.nombre} necesita exactamente "
                        f"{cantidad_requerida} productos."
                    )

                productos_mapa = {
                    producto.id: producto
                    for producto in (
                        Producto.objects
                        .filter(
                            id__in=set(seleccion_ids),
                            activo=True,
                            solo_produccion=False,
                            tipo_id=kit.tipo_producto_id,
                        )
                        .select_related("tipo")
                    )
                }

                if any(pid not in productos_mapa for pid in seleccion_ids):
                    raise ValueError(
                        f"Una opción elegida ya no está disponible para {kit.nombre}."
                    )

                seleccion = [productos_mapa[pid] for pid in seleccion_ids]
                precio_unitario = _decimal(
                    precio_automatico_kit_libre(kit, seleccion)
                )
                precio_base = _decimal(kit.precio)
                adicional = max(
                    precio_unitario - precio_base,
                    Decimal("0"),
                )

                for producto_id in seleccion_ids:
                    componentes[producto_id] += cantidad

            precio_base = _decimal(kit.precio)
            if precio_base <= 0 or precio_unitario <= 0:
                raise ValueError(
                    f"{kit.nombre} no tiene un precio válido actualmente."
                )

            lineas.append(
                {
                    "tipo": "KIT",
                    "cantidad": cantidad,
                    "producto": None,
                    "kit": kit,
                    "nombre": kit.nombre,
                    "precio_base": precio_base,
                    "adicional": adicional,
                    "precio_unitario": precio_unitario,
                    "componentes": dict(componentes),
                    "canonical": {
                        "kind": "kit",
                        "id": kit.id,
                        "qty": cantidad,
                        "selections": sorted(seleccion_ids),
                    },
                }
            )
            continue

        raise ValueError(
            "El carrito contiene un tipo de producto que no reconocemos."
        )

    return lineas


def _fingerprint(telefono, lineas):
    lineas_canonicas = [linea["canonical"] for linea in lineas]
    lineas_canonicas.sort(
        key=lambda item: json.dumps(
            item,
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    canonical = {
        "telefono": telefono,
        "lineas": lineas_canonicas,
    }
    raw = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validar_turnstile(request):
    secret = getattr(settings, "TURNSTILE_SECRET_KEY", "")
    if not secret:
        return True

    token = request.POST.get("cf-turnstile-response", "").strip()
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


def _contexto_checkout(error=""):
    return {
        "error": error,
        "turnstile_site_key": getattr(
            settings,
            "TURNSTILE_SITE_KEY",
            "",
        ),
    }


@never_cache
@transaction.atomic
def carrito_checkout(request):
    if request.method != "POST":
        return render(
            request,
            "productos/catalogo_checkout.html",
            _contexto_checkout(),
        )

    # Honeypot: los usuarios reales nunca completan este campo.
    if request.POST.get("website", "").strip():
        request.session["solicitud_web_spam"] = True
        request.session.pop("solicitud_web_ultima_id", None)
        return redirect("catalogo_carrito_gracias")

    nombre = request.POST.get("nombre", "").strip()
    telefono = request.POST.get("telefono", "").strip()
    telefono_norm = _telefono_normalizado(telefono)
    email = request.POST.get("email", "").strip()
    observaciones = request.POST.get("observaciones", "").strip()[:2000]

    if len(nombre) < 2:
        return render(
            request,
            "productos/catalogo_checkout.html",
            _contexto_checkout("Ingresá tu nombre."),
        )

    if len(telefono_norm) < 8:
        return render(
            request,
            "productos/catalogo_checkout.html",
            _contexto_checkout(
                "Ingresá un número de WhatsApp válido."
            ),
        )

    if email:
        try:
            validate_email(email)
        except ValidationError:
            return render(
                request,
                "productos/catalogo_checkout.html",
                _contexto_checkout("El email no es válido."),
            )

    if not _validar_turnstile(request):
        return render(
            request,
            "productos/catalogo_checkout.html",
            _contexto_checkout(
                "No pudimos validar la solicitud. Intentá nuevamente."
            ),
        )

    try:
        payload = _parsear_payload(
            request.POST.get("cart_payload", "")
        )
        lineas = _validar_carrito(payload)
    except ValueError as error:
        return render(
            request,
            "productos/catalogo_checkout.html",
            _contexto_checkout(str(error)),
        )

    ahora = timezone.now()
    ip_hash = _ip_hash(request)

    if ip_hash:
        por_hora = SolicitudWeb.objects.filter(
            ip_hash=ip_hash,
            creada_en__gte=ahora - timedelta(hours=1),
        ).count()
        por_dia = SolicitudWeb.objects.filter(
            ip_hash=ip_hash,
            creada_en__gte=ahora - timedelta(hours=24),
        ).count()

        if por_hora >= 5 or por_dia >= 10:
            return render(
                request,
                "productos/catalogo_checkout.html",
                _contexto_checkout(
                    "Recibimos varias solicitudes desde esta conexión. "
                    "Esperá un rato antes de enviar otra."
                ),
            )

    por_telefono = SolicitudWeb.objects.filter(
        telefono_normalizado=telefono_norm,
        creada_en__gte=ahora - timedelta(hours=2),
    ).count()
    if por_telefono >= 3:
        return render(
            request,
            "productos/catalogo_checkout.html",
            _contexto_checkout(
                "Ya recibimos varias solicitudes con este WhatsApp. "
                "Esperá un rato o escribinos directamente."
            ),
        )

    fingerprint = _fingerprint(telefono_norm, lineas)
    duplicada = (
        SolicitudWeb.objects
        .filter(
            fingerprint=fingerprint,
            creada_en__gte=ahora - timedelta(minutes=15),
        )
        .order_by("-id")
        .first()
    )
    if duplicada:
        request.session["solicitud_web_ultima_id"] = duplicada.id
        request.session.pop("solicitud_web_spam", None)
        return redirect("catalogo_carrito_gracias")

    solicitud = SolicitudWeb.objects.create(
        nombre=nombre[:150],
        telefono=telefono[:40],
        telefono_normalizado=telefono_norm,
        email=email,
        observaciones=observaciones,
        estado="NUEVA",
        ip_hash=ip_hash,
        fingerprint=fingerprint,
        user_agent=(request.META.get("HTTP_USER_AGENT") or "")[:250],
    )

    for linea in lineas:
        item = SolicitudWebItem.objects.create(
            solicitud=solicitud,
            tipo_item=linea["tipo"],
            producto=linea["producto"],
            kit=linea["kit"],
            cantidad=linea["cantidad"],
            nombre_snapshot=linea["nombre"][:200],
            precio_base_unitario=linea["precio_base"],
            adicional_unitario=linea["adicional"],
            precio_unitario=linea["precio_unitario"],
        )

        for producto_id, cantidad in linea["componentes"].items():
            SolicitudWebKitProducto.objects.create(
                item=item,
                producto_id=producto_id,
                cantidad=cantidad,
            )

    request.session["solicitud_web_ultima_id"] = solicitud.id
    request.session.pop("solicitud_web_spam", None)
    return redirect("catalogo_carrito_gracias")


@never_cache
def carrito_gracias(request):
    solicitud = None
    if not request.session.get("solicitud_web_spam"):
        solicitud_id = request.session.get("solicitud_web_ultima_id")
        if solicitud_id:
            solicitud = (
                SolicitudWeb.objects
                .filter(id=solicitud_id)
                .prefetch_related("items")
                .first()
            )

    return render(
        request,
        "productos/catalogo_gracias.html",
        {
            "solicitud": solicitud,
        },
    )
