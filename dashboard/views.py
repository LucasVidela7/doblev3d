import json
from datetime import timedelta
from decimal import Decimal
from html import escape

from django.conf import settings
from django.db.models import Sum
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from pedidos.models import (
    Pedido,
    Pago,
    Presupuesto,
    SolicitudWeb,
    WebPushSubscription,
)
from pedidos.impresiones_stock import obtener_impresiones_por_producto
from produccion import views as produccion_views
from produccion.models import Impresora, Produccion
from productos.models import ConfiguracionCatalogo, Producto
from productos.miniaturas import asignar_miniaturas_productos


def _webpush_habilitado():
    return bool(
        getattr(settings, "WEBPUSH_VAPID_PUBLIC_KEY", "")
        and getattr(settings, "WEBPUSH_VAPID_PRIVATE_KEY", "")
    )


@never_cache
def push_service_worker(request):
    script = r"""
self.addEventListener("install", () => self.skipWaiting());

self.addEventListener("activate", (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener("push", (event) => {
    let data = {};
    try {
        data = event.data ? event.data.json() : {};
    } catch (error) {
        data = {
            title: "Doble V 3D",
            body: event.data ? event.data.text() : "Tenés una novedad.",
        };
    }

    const title = data.title || "Doble V 3D";
    const options = {
        body: data.body || "Tenés una novedad.",
        icon: data.icon || "/static/brand/apple-touch-icon.png",
        badge: data.badge || "/static/brand/favicon.ico",
        tag: data.tag || "doblev3d",
        renotify: true,
        data: {
            url: data.url || "/gestion/",
        },
    };

    event.waitUntil(
        self.registration.showNotification(title, options)
    );
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();
    const target = new URL(
        (event.notification.data && event.notification.data.url) || "/gestion/",
        self.location.origin
    ).href;

    event.waitUntil((async () => {
        const windows = await self.clients.matchAll({
            type: "window",
            includeUncontrolled: true,
        });

        for (const client of windows) {
            if (new URL(client.url).origin === self.location.origin) {
                if ("navigate" in client) {
                    await client.navigate(target);
                }
                return client.focus();
            }
        }

        return self.clients.openWindow(target);
    })());
});
"""
    response = HttpResponse(
        script,
        content_type="application/javascript; charset=utf-8",
    )
    response["Cache-Control"] = "no-store"
    response["Service-Worker-Allowed"] = "/gestion/"
    return response


@require_POST
def push_suscribir(request):
    if not _webpush_habilitado():
        return JsonResponse(
            {"ok": False, "mensaje": "Web Push no está configurado."},
            status=503,
        )

    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return JsonResponse(
            {"ok": False, "mensaje": "Suscripción inválida."},
            status=400,
        )

    endpoint = str(payload.get("endpoint") or "").strip()
    keys = payload.get("keys") or {}
    p256dh = str(keys.get("p256dh") or "").strip()
    auth = str(keys.get("auth") or "").strip()

    if not endpoint or not p256dh or not auth:
        return JsonResponse(
            {"ok": False, "mensaje": "Faltan datos de la suscripción."},
            status=400,
        )

    suscripcion, _ = WebPushSubscription.objects.update_or_create(
        endpoint=endpoint[:1000],
        defaults={
            "user": request.user,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": (
                request.META.get("HTTP_USER_AGENT") or ""
            )[:250],
            "activa": True,
        },
    )

    return JsonResponse(
        {
            "ok": True,
            "id": suscripcion.id,
        }
    )


@require_POST
def push_desuscribir(request):
    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}

    endpoint = str(payload.get("endpoint") or "").strip()
    if endpoint:
        WebPushSubscription.objects.filter(
            endpoint=endpoint,
            user=request.user,
        ).update(activa=False)

    return JsonResponse({"ok": True})


DASHBOARD_PRODUCCION_STYLE = r"""
<style id="dv-dashboard-produccion-style">
.dv-produccion-panel{
    display:flex;
    flex-direction:column;
    gap:12px;
}
.dv-produccion-cabecera{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:12px;
}
.dv-produccion-link{
    color:#555b63;
    font-size:9px;
    font-weight:900;
    text-decoration:none;
    white-space:nowrap;
}
.dv-maquinas{
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:8px;
}
.dv-maquina{
    min-width:0;
    padding:11px;
    border:1px solid #e5e7eb;
    border-radius:13px;
    background:#fafafa;
}
.dv-maquina-head{
    display:flex;
    align-items:center;
    justify-content:space-between;
    gap:8px;
    margin-bottom:7px;
}
.dv-maquina-nombre{
    min-width:0;
    overflow:hidden;
    text-overflow:ellipsis;
    white-space:nowrap;
    font-size:11px;
    font-weight:900;
}
.dv-maquina-estado{
    flex:0 0 auto;
    display:inline-flex;
    padding:4px 7px;
    border-radius:999px;
    font-size:7px;
    font-weight:900;
}
.dv-maquina-estado.imprimiendo{
    background:#e3efff;
    color:#245a9b;
}
.dv-maquina-estado.libre{
    background:#dff4e5;
    color:#24633a;
}
.dv-maquina-producto{
    overflow:hidden;
    text-overflow:ellipsis;
    white-space:nowrap;
    font-size:11px;
    font-weight:800;
}
.dv-producto-linea{
    display:grid;
    grid-template-columns:40px minmax(0,1fr);
    gap:8px;
    align-items:center;
    min-width:0;
}
.dv-producto-thumb{
    width:40px;
    height:40px;
    border:1px solid var(--dv-border,#e5e7eb);
    border-radius:9px;
    background:var(--dv-surface-soft,#f2f4f7);
    object-fit:cover;
    display:block;
}
.dv-producto-thumb.vacia{
    display:flex;
    align-items:center;
    justify-content:center;
    color:var(--dv-muted,#73777f);
    font-size:7px;
    font-weight:900;
    letter-spacing:.04em;
}
.dv-maquina-meta{
    margin-top:4px;
    color:#73777f;
    font-size:8px;
    line-height:1.4;
}
.dv-maquina-acciones{
    display:grid;
    grid-template-columns:1fr auto;
    gap:6px;
    margin-top:8px;
}
.dv-maquina-acciones form{
    margin:0;
}
.dv-btn-listo,.dv-btn-cancelar,.dv-btn-iniciar{
    width:100%;
    min-height:31px;
    padding:0 9px;
    border-radius:9px;
    font-family:Arial,sans-serif;
    font-size:8px;
    font-weight:900;
    cursor:pointer;
}
.dv-btn-listo{
    border:0;
    background:#24633a;
    color:#fff;
}
.dv-btn-cancelar{
    border:1px solid #eccaca;
    background:#fff;
    color:#9a3030;
}
.dv-planificaciones{
    padding-top:10px;
    border-top:1px solid #eceef1;
}
.dv-planificaciones-titulo{
    margin-bottom:7px;
    color:#73777f;
    font-size:8px;
    font-weight:900;
    letter-spacing:.35px;
}
.dv-plan{
    display:grid;
    grid-template-columns:minmax(0,1fr) auto;
    gap:8px;
    align-items:center;
    padding:8px 0;
}
.dv-plan + .dv-plan{
    border-top:1px solid #f0f1f3;
}
.dv-plan-producto{
    overflow:hidden;
    text-overflow:ellipsis;
    white-space:nowrap;
    font-size:10px;
    font-weight:900;
}
.dv-plan .dv-producto-linea{
    grid-template-columns:36px minmax(0,1fr);
}
.dv-plan .dv-producto-thumb{
    width:36px;
    height:36px;
    border-radius:8px;
}
.dv-plan-meta{
    margin-top:3px;
    color:#73777f;
    font-size:8px;
    line-height:1.35;
}
.dv-plan-form{
    display:flex;
    align-items:center;
    gap:5px;
    margin:0;
}
.dv-plan-select{
    width:112px;
    min-height:31px;
    padding:4px 6px;
    border:1px solid #d9dce0;
    border-radius:8px;
    background:#fff;
    font-size:8px;
}
.dv-btn-iniciar{
    width:auto;
    border:0;
    background:#24272b;
    color:#fff;
}
.dv-sin-produccion{
    padding:12px 8px;
    color:#73777f;
    text-align:center;
    font-size:9px;
}
@media(max-width:720px){
    .dv-maquinas{grid-template-columns:1fr}
    .dv-plan{grid-template-columns:1fr}
    .dv-plan-form{width:100%}
    .dv-plan-select{flex:1;width:auto}
}
</style>
"""


def _miniatura_producto_dashboard(producto):
    url = escape(
        getattr(
            producto,
            "imagen_produccion_url",
            "",
        )
        or ""
    )

    if url:
        return (
            '<img class="dv-producto-thumb" '
            f'src="{url}" alt="" loading="lazy">'
        )

    return (
        '<span class="dv-producto-thumb vacia">'
        '3D'
        '</span>'
    )


def _panel_produccion_dashboard(
    request,
    impresoras,
    producciones_actuales,
    planificaciones,
):
    csrf_token = escape(get_token(request))
    ahora = timezone.now()

    actuales_por_impresora = {}
    for produccion in producciones_actuales:
        if produccion.impresora_id not in actuales_por_impresora:
            actuales_por_impresora[produccion.impresora_id] = produccion

    impresoras_libres = [
        impresora
        for impresora in impresoras
        if impresora.id not in actuales_por_impresora
    ]

    maquinas_html = []

    for impresora in impresoras:
        produccion = actuales_por_impresora.get(impresora.id)
        nombre = escape(impresora.nombre)

        if produccion:
            producto = escape(produccion.producto.nombre)
            miniatura = _miniatura_producto_dashboard(
                produccion.producto
            )
            fin = produccion.fin_estimado
            fin_texto = (
                timezone.localtime(fin).strftime("%H:%M")
                if fin
                else "—"
            )
            peso = escape(produccion.peso_total_formateado)
            listo_url = escape(
                reverse(
                    "dashboard:produccion_estado",
                    args=[produccion.id],
                )
            )

            maquinas_html.append(
                f"""
                <div class="dv-maquina">
                    <div class="dv-maquina-head">
                        <div class="dv-maquina-nombre">🖨 {nombre}</div>
                        <span class="dv-maquina-estado imprimiendo">IMPRIMIENDO</span>
                    </div>
                    <div class="dv-producto-linea">
                        {miniatura}
                        <div>
                            <div class="dv-maquina-producto">{producto} × {produccion.cantidad}</div>
                            <div class="dv-maquina-meta">
                                Termina {fin_texto} · ⚖ {peso}
                            </div>
                        </div>
                    </div>
                    <div class="dv-maquina-acciones">
                        <form method="post" action="{listo_url}">
                            <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}">
                            <input type="hidden" name="estado" value="LISTO">
                            <button type="submit" class="dv-btn-listo">✓ LISTO</button>
                        </form>
                        <form method="post" action="{listo_url}">
                            <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}">
                            <input type="hidden" name="estado" value="CANCELADO">
                            <button type="submit" class="dv-btn-cancelar" title="Cancelar impresión">×</button>
                        </form>
                    </div>
                </div>
                """
            )
        else:
            maquinas_html.append(
                f"""
                <div class="dv-maquina">
                    <div class="dv-maquina-head">
                        <div class="dv-maquina-nombre">🖨 {nombre}</div>
                        <span class="dv-maquina-estado libre">LIBRE</span>
                    </div>
                    <div class="dv-maquina-meta">Libre para tomar el siguiente trabajo de la cola.</div>
                </div>
                """
            )

    if not maquinas_html:
        maquinas_html.append(
            '<div class="dv-sin-produccion">No hay impresoras activas configuradas.</div>'
        )

    planes_html = []

    for produccion in planificaciones:
        producto = escape(produccion.producto.nombre)
        miniatura = _miniatura_producto_dashboard(
            produccion.producto
        )
        peso = escape(produccion.peso_total_formateado)
        inicio = produccion.inicio_impresion

        if inicio and inicio <= ahora:
            inicio_texto = "Disponible ahora"
        elif inicio:
            inicio_texto = timezone.localtime(inicio).strftime(
                "%d/%m · %H:%M"
            )
        else:
            inicio_texto = "Sin horario"

        iniciar_url = escape(
            reverse(
                "dashboard:produccion_iniciar",
                args=[produccion.id],
            )
        )

        if impresoras_libres:
            opciones = "".join(
                (
                    f'<option value="{impresora.id}">'
                    f'{escape(impresora.nombre)}</option>'
                )
                for impresora in impresoras_libres
            )

            accion = f"""
                <form method="post" action="{iniciar_url}" class="dv-plan-form">
                    <input type="hidden" name="csrfmiddlewaretoken" value="{csrf_token}">
                    <select name="impresora" class="dv-plan-select" required>
                        <option value="">Impresora…</option>
                        {opciones}
                    </select>
                    <button type="submit" class="dv-btn-iniciar">▶</button>
                </form>
            """
        else:
            accion = (
                '<span class="dv-maquina-estado imprimiendo">SIN MÁQUINA LIBRE</span>'
            )

        planes_html.append(
            f"""
            <div class="dv-plan">
                <div class="dv-producto-linea">
                    {miniatura}
                    <div>
                        <div class="dv-plan-producto">{producto} × {produccion.cantidad}</div>
                        <div class="dv-plan-meta">
                            {inicio_texto} · {escape(produccion.tiempo_impresion_formateado)} · ⚖ {peso}
                        </div>
                    </div>
                </div>
                {accion}
            </div>
            """
        )

    if not planes_html:
        planes_html.append(
            '<div class="dv-sin-produccion">La cola está vacía.</div>'
        )

    produccion_url = escape(reverse("produccion:lista"))

    return f"""
    <div class="panel dv-produccion-panel">
        <div class="dv-produccion-cabecera">
            <div>
                <h3 class="panel-titulo">Ahora y cola</h3>
                <div class="panel-subtitulo" style="margin-bottom:0">
                    Impresoras y próximos trabajos
                </div>
            </div>
            <a class="dv-produccion-link" href="{produccion_url}">VER TODO →</a>
        </div>

        <div class="dv-maquinas">
            {''.join(maquinas_html)}
        </div>

        <div class="dv-planificaciones">
            <div class="dv-planificaciones-titulo">COLA · PRÓXIMOS TRABAJOS</div>
            {''.join(planes_html)}
        </div>
    </div>
    """


def _inyectar_panel_produccion(response, panel_html):
    try:
        html = response.content.decode(response.charset or "utf-8")
    except (AttributeError, UnicodeDecodeError):
        return response

    if "dv-dashboard-produccion-style" not in html and "</head>" in html:
        html = html.replace(
            "</head>",
            DASHBOARD_PRODUCCION_STYLE + "\n</head>",
            1,
        )

    panel_json = json.dumps(
        panel_html,
        ensure_ascii=False,
    ).replace("</", "<\\/")

    script = f"""
<script id="dv-dashboard-produccion-script">
(function(){{
    function reemplazarPanel(){{
        var paneles = Array.from(document.querySelectorAll('.paneles .panel'));
        var objetivo = paneles.find(function(panel){{
            var titulo = panel.querySelector('.panel-titulo');
            return titulo && titulo.textContent.trim() === 'Pedidos por estado';
        }});

        if (!objetivo) return;

        var plantilla = document.createElement('template');
        plantilla.innerHTML = {panel_json}.trim();
        var nuevo = plantilla.content.firstElementChild;
        if (nuevo) objetivo.replaceWith(nuevo);
    }}

    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', reemplazarPanel);
    }} else {{
        reemplazarPanel();
    }}
}})();
</script>
"""

    if "dv-dashboard-produccion-script" not in html and "</body>" in html:
        html = html.replace(
            "</body>",
            script + "\n</body>",
            1,
        )

    encoded = html.encode(response.charset or "utf-8")
    response.content = encoded
    response["Content-Length"] = str(len(encoded))
    return response


def inicio(request):
    hoy = timezone.localdate()
    fin_semana = hoy + timedelta(days=7)

    pedidos_activos_qs = (
        Pedido.objects
        .exclude(
            estado__in=[
                "ENTREGADO",
                "CANCELADO",
            ]
        )
    )

    pedidos_activos = pedidos_activos_qs.count()

    pedidos_pendientes = (
        pedidos_activos_qs
        .filter(estado="PENDIENTE")
        .count()
    )

    pedidos_preparando = (
        pedidos_activos_qs
        .filter(estado="PREPARANDO")
        .count()
    )

    pedidos_listos = (
        pedidos_activos_qs
        .filter(estado="LISTO")
        .count()
    )

    pedidos_hoy = (
        pedidos_activos_qs
        .filter(fecha_entrega=hoy)
        .count()
    )

    pedidos_atrasados = (
        pedidos_activos_qs
        .filter(fecha_entrega__lt=hoy)
        .count()
    )

    producciones_pendientes = (
        Produccion.objects
        .filter(estado="PENDIENTE")
        .count()
    )

    producciones_imprimiendo = (
        Produccion.objects
        .filter(estado="IMPRIMIENDO")
        .count()
    )

    unidades_en_produccion = (
        Produccion.objects
        .filter(
            estado__in=[
                "PENDIENTE",
                "IMPRIMIENDO",
            ]
        )
        .aggregate(total=Sum("cantidad"))
        .get("total")
        or 0
    )

    impresoras_dashboard = list(
        Impresora.objects
        .filter(activa=True)
        .order_by("nombre")
    )

    producciones_actuales_dashboard = list(
        Produccion.objects
        .filter(
            estado="IMPRIMIENDO",
            impresora__isnull=False,
        )
        .select_related(
            "producto",
            "impresora",
        )
        .order_by(
            "inicio_impresion",
            "id",
        )
    )

    planificaciones_dashboard = list(
        Produccion.objects
        .filter(estado="PENDIENTE")
        .select_related("producto")
        .order_by(
            "inicio_impresion",
            "id",
        )[:4]
    )

    # Próximas entregas: primero atrasadas y luego las más cercanas.
    proximas_entregas = (
        pedidos_activos_qs
        .filter(
            fecha_entrega__isnull=False,
            fecha_entrega__lte=fin_semana,
        )
        .select_related("cliente")
        .order_by(
            "fecha_entrega",
            "id",
        )[:8]
    )

    # ==========================================================
    # QUÉ IMPRIMIR
    # ==========================================================
    # El dashboard usa exactamente la misma fuente que el Centro de
    # producción para evitar que ambas pantallas indiquen faltantes distintos.
    necesidad_impresion = [
        item
        for item in obtener_impresiones_por_producto()
        if int(item.get("falta_iniciar") or 0) > 0
    ]

    total_a_imprimir = sum(
        max(int(item.get("falta_iniciar") or 0), 0)
        for item in necesidad_impresion
    )

    top_impresion = necesidad_impresion[:5]

    productos_dashboard = [
        produccion.producto
        for produccion in (
            producciones_actuales_dashboard
            + planificaciones_dashboard
        )
    ]
    productos_dashboard.extend(
        item["producto"]
        for item in top_impresion
        if item.get("producto")
    )
    asignar_miniaturas_productos(
        productos_dashboard
    )

    # Productos activos sin stock. Es una alerta simple y útil;
    # no supone un "stock mínimo" porque ese campo aún no existe.
    productos_sin_stock = (
        Producto.objects
        .filter(
            activo=True,
            stock__lte=0,
        )
        .count()
    )

    # ==========================================================
    # PRESUPUESTOS
    # ==========================================================

    solicitudes_web_qs = (
        SolicitudWeb.objects
        .filter(
            estado__in=["NUEVA", "CONTACTADA"],
        )
        .prefetch_related("items")
        .order_by("-id")
    )
    solicitudes_web_activas = list(
        solicitudes_web_qs[:6]
    )
    solicitudes_web_nuevas = (
        SolicitudWeb.objects
        .filter(estado="NUEVA")
        .count()
    )
    solicitudes_web_contactadas = (
        SolicitudWeb.objects
        .filter(estado="CONTACTADA")
        .count()
    )
    solicitudes_web_pendientes = (
        solicitudes_web_nuevas
        + solicitudes_web_contactadas
    )

    for solicitud in solicitudes_web_activas:
        solicitud.unidades_dashboard = sum(
            int(item.cantidad or 0)
            for item in solicitud.items.all()
        )

    presupuestos_pendientes_qs = (
        Presupuesto.objects
        .filter(estado="PENDIENTE")
        .prefetch_related("detalles")
        .order_by("-id")
    )

    presupuestos_pendientes_lista = list(
        presupuestos_pendientes_qs
    )

    presupuestos_pendientes = len(
        presupuestos_pendientes_lista
    )

    monto_presupuestado_pendiente = sum(
        (
            presupuesto.total
            for presupuesto in presupuestos_pendientes_lista
        ),
        Decimal("0"),
    )

    # ==========================================================
    # PAGOS
    # ==========================================================

    inicio_mes = hoy.replace(day=1)

    saldo_a_cobrar = Decimal("0")

    pedidos_con_saldo_qs = (
        Pedido.objects
        .exclude(estado="CANCELADO")
        .prefetch_related(
            "detalles",
            "pagos",
        )
    )

    pedidos_con_saldo = 0

    for pedido in pedidos_con_saldo_qs:
        saldo = pedido.saldo_pendiente

        if saldo > 0:
            saldo_a_cobrar += saldo
            pedidos_con_saldo += 1

    cobrado_mes = (
        Pago.objects
        .filter(
            fecha__date__gte=inicio_mes,
        )
        .aggregate(total=Sum("monto"))
        .get("total")
        or Decimal("0")
    )

    response = render(
        request,
        "dashboard/inicio.html",
        {
            "hoy": hoy,
            "pedidos_activos": pedidos_activos,
            "pedidos_pendientes": pedidos_pendientes,
            "pedidos_preparando": pedidos_preparando,
            "pedidos_listos": pedidos_listos,
            "pedidos_hoy": pedidos_hoy,
            "pedidos_atrasados": pedidos_atrasados,
            "producciones_pendientes": producciones_pendientes,
            "producciones_imprimiendo": producciones_imprimiendo,
            "unidades_en_produccion": unidades_en_produccion,
            "total_a_imprimir": total_a_imprimir,
            "productos_sin_stock": productos_sin_stock,
            "proximas_entregas": proximas_entregas,
            "top_impresion": top_impresion,
            "saldo_a_cobrar": saldo_a_cobrar,
            "pedidos_con_saldo": pedidos_con_saldo,
            "cobrado_mes": cobrado_mes,
            "presupuestos_pendientes": presupuestos_pendientes,
            "monto_presupuestado_pendiente": monto_presupuestado_pendiente,
            "solicitudes_web_activas": solicitudes_web_activas,
            "solicitudes_web_nuevas": solicitudes_web_nuevas,
            "solicitudes_web_contactadas": solicitudes_web_contactadas,
            "solicitudes_web_pendientes": solicitudes_web_pendientes,
            "webpush_habilitado": _webpush_habilitado(),
            "webpush_public_key": getattr(
                settings,
                "WEBPUSH_VAPID_PUBLIC_KEY",
                "",
            ),
        },
    )

    panel_html = _panel_produccion_dashboard(
        request,
        impresoras_dashboard,
        producciones_actuales_dashboard,
        planificaciones_dashboard,
    )

    return _inyectar_panel_produccion(
        response,
        panel_html,
    )


@never_cache
def configuracion(request):
    config, _ = ConfiguracionCatalogo.objects.get_or_create(
        pk=1
    )

    campos_texto = {
        "mensaje_mantenimiento": 240,
        "mensaje_plazo_entrega": 300,
        "instagram_usuario": 100,
        "whatsapp_numero": 30,
        "whatsapp_mensaje": 240,
        "whatsapp_mensaje_respuesta_solicitud": 4000,
        "whatsapp_mensaje_post_solicitud": 4000,
        "whatsapp_mensaje_cliente_generico": 2000,
        "whatsapp_mensaje_cliente_pedido_listo": 2000,
        "whatsapp_mensaje_cliente_saldo": 2000,
        "whatsapp_mensaje_cliente_presupuesto": 2000,
        "whatsapp_mensaje_cliente_reactivacion": 2000,
    }
    campos_booleanos = [
        "catalogo_activo",
        "notificaciones_pedidos_web_activas",
        "mostrar_instagram",
        "mostrar_whatsapp",
    ]

    if request.method == "POST":
        actualizados = []

        for campo in campos_booleanos:
            setattr(
                config,
                campo,
                request.POST.get(campo) == "on",
            )
            actualizados.append(campo)

        for campo, limite in campos_texto.items():
            valor = (
                request.POST.get(campo)
                or ""
            ).strip()[:limite]
            setattr(config, campo, valor)
            actualizados.append(campo)

        config.save(
            update_fields=actualizados,
        )
        return redirect(
            reverse("dashboard:configuracion")
            + "?guardado=1"
        )

    whatsapp_defaults = {}
    for campo in [
        "whatsapp_mensaje_cliente_generico",
        "whatsapp_mensaje_cliente_pedido_listo",
        "whatsapp_mensaje_cliente_saldo",
        "whatsapp_mensaje_cliente_presupuesto",
        "whatsapp_mensaje_cliente_reactivacion",
        "whatsapp_mensaje_respuesta_solicitud",
        "whatsapp_mensaje_post_solicitud",
    ]:
        default = (
            ConfiguracionCatalogo
            ._meta
            .get_field(campo)
            .default
        )
        whatsapp_defaults[campo] = (
            default()
            if callable(default)
            else default
        )

    webpush_habilitado = _webpush_habilitado()

    return render(
        request,
        "dashboard/configuracion.html",
        {
            "config": config,
            "webpush_configurado": webpush_habilitado,
            "webpush_habilitado": webpush_habilitado,
            "webpush_public_key": getattr(
                settings,
                "WEBPUSH_VAPID_PUBLIC_KEY",
                "",
            ),
            "dispositivos_push_activos": (
                WebPushSubscription.objects
                .filter(activa=True)
                .count()
            ),
            "whatsapp_defaults": whatsapp_defaults,
        },
    )


def iniciar_produccion_dashboard(
    request,
    produccion_id,
):
    produccion_views.iniciar_produccion(
        request,
        produccion_id,
    )
    return redirect("dashboard:inicio")


def cambiar_estado_produccion_dashboard(
    request,
    produccion_id,
):
    produccion_views.cambiar_estado(
        request,
        produccion_id,
    )
    return redirect("dashboard:inicio")
