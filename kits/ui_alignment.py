import json

from productos.models import Producto

from .engine import KitEngine


DASHBOARD_KITS_STYLE = r"""
<style id="dv-dashboard-kits-style">
#dv-dashboard-kits.dv-kits-critico{
    border-color:#e7bcbc;
}
#dv-dashboard-kits.dv-kits-critico .accion-icono{
    background:#fde5e5;
    color:#913434;
}
#dv-dashboard-kits.dv-kits-advertencia:not(.dv-kits-critico){
    border-color:#ead89d;
}
#dv-dashboard-kits.dv-kits-advertencia:not(.dv-kits-critico) .accion-icono{
    background:#fff4cf;
    color:#765b00;
}
#dv-dashboard-kits .dv-kits-aviso{
    margin-top:5px;
    font-size:10px;
    font-weight:900;
    line-height:1.35;
}
#dv-dashboard-kits .dv-kits-aviso.critico{color:#913434}
#dv-dashboard-kits .dv-kits-aviso.advertencia{color:#765b00}
</style>
"""


KIT_ECONOMIA_STYLE = r"""
<style id="dv-kit-economia-style">
.dv-kit-economia{
    grid-column:1/-1;
    margin-top:10px;
    padding:12px;
    border:1px solid #cfe2d5;
    border-radius:12px;
    background:#f0f9f3;
    color:#275c39;
    font-family:Arial,sans-serif;
    font-size:10px;
    line-height:1.45;
}
.dv-kit-economia.dv-kit-advertencia{
    border-color:#ead89d;
    background:#fffaf0;
    color:#765b00;
}
.dv-kit-economia.dv-kit-alerta{
    border-color:#e5b7b7;
    background:#fff0f0;
    color:#8e3434;
}
.dv-kit-economia-titulo{
    margin-bottom:5px;
    font-size:10px;
    font-weight:900;
    letter-spacing:.2px;
}
.dv-kit-economia-datos{
    font-weight:700;
}
.dv-kit-economia-motivo{
    margin-top:5px;
}
.dv-kit-economia-escenarios{
    display:flex;
    gap:6px;
    flex-wrap:wrap;
    margin-top:8px;
}
.dv-kit-economia-chip{
    display:inline-flex;
    align-items:center;
    min-height:27px;
    padding:0 8px;
    border:1px solid rgba(0,0,0,.08);
    border-radius:999px;
    background:rgba(255,255,255,.75);
    color:inherit;
    font-size:8px;
    font-weight:900;
}
.dv-kit-economia-chip.recomendado{
    border-color:#a9cdb5;
    background:#fff;
}
@media(max-width:700px){
    .dv-kit-economia-escenarios{display:grid;grid-template-columns:1fr}
    .dv-kit-economia-chip{justify-content:center}
}
</style>
"""


def _datos_economicos_kits():
    from .models import Kit

    kits = list(
        Kit.objects
        .filter(activo=True)
        .select_related("tipo_producto")
        .prefetch_related("componentes__producto")
        .order_by("nombre")
    )

    tipos_libres = {
        kit.tipo_producto_id
        for kit in kits
        if kit.modalidad == "LIBRE_CATEGORIA"
        and kit.tipo_producto_id
    }
    productos_por_tipo = {}

    if tipos_libres:
        productos = (
            Producto.objects
            .filter(
                tipo_id__in=tipos_libres,
                activo=True,
                solo_produccion=False,
            )
            .order_by("id")
        )
        for producto in productos:
            productos_por_tipo.setdefault(
                producto.tipo_id,
                [],
            ).append(producto)

    datos = {}
    resumen = {
        "criticos": 0,
        "advertencias": 0,
        "sin_datos": 0,
        "total_revision": 0,
    }

    for kit in kits:
        recomendacion = KitEngine.recomendacion(
            kit,
            productos_categoria=(
                productos_por_tipo.get(
                    kit.tipo_producto_id,
                    [],
                )
                if kit.modalidad == "LIBRE_CATEGORIA"
                else None
            ),
        )

        estado = recomendacion["estado"]
        if estado == "REVISAR":
            resumen["criticos"] += 1
        elif estado == "ADVERTENCIA":
            resumen["advertencias"] += 1
        elif estado == "SIN_DATOS":
            resumen["sin_datos"] += 1

        if estado != "OK":
            resumen["total_revision"] += 1

        datos[str(kit.id)] = {
            "nombre": kit.nombre,
            "modalidad": kit.modalidad,
            "precio": str(recomendacion["precio_actual"]),
            "tipo_calculo": recomendacion["tipo_calculo"],
            "costo_estimado": str(recomendacion["costo_estimado"]),
            "costo_peor_caso": str(recomendacion["costo_peor_caso"]),
            "margen_estimado": (
                str(recomendacion["margen_actual"])
                if recomendacion["margen_actual"] is not None
                else None
            ),
            "margen_peor_caso": (
                str(recomendacion["margen_peor_caso"])
                if recomendacion["margen_peor_caso"] is not None
                else None
            ),
            "precio_agresivo": str(
                recomendacion["precio_agresivo"]
            ),
            "precio_recomendado": str(
                recomendacion["precio_recomendado"]
            ),
            "precio_conservador": str(
                recomendacion["precio_conservador"]
            ),
            "margen_minimo": str(recomendacion["margen_piso"]),
            "estado": estado,
            "alerta": estado != "OK",
            "critico": bool(recomendacion["critico"]),
            "disponible": bool(recomendacion["disponible"]),
            "motivo": recomendacion["motivo"],
        }

    return datos, len(kits), resumen


def _dashboard_kits_html(total_kits, resumen):
    from django.urls import reverse

    kits_url = reverse("kits:lista")
    criticos = int(resumen.get("criticos", 0))
    advertencias = int(resumen.get("advertencias", 0))
    sin_datos = int(resumen.get("sin_datos", 0))

    clases = []
    avisos = []

    if criticos or sin_datos:
        clases.append("dv-kits-critico")
        partes = []
        if criticos:
            partes.append(
                f"{criticos} por debajo de Agresivo"
            )
        if sin_datos:
            partes.append(
                f"{sin_datos} sin datos de costo"
            )
        avisos.append(
            '<div class="dv-kits-aviso critico">⚠ '
            + " · ".join(partes)
            + "</div>"
        )

    if advertencias:
        clases.append("dv-kits-advertencia")
        avisos.append(
            '<div class="dv-kits-aviso advertencia">● '
            f"{advertencias} "
            f'{"kit" if advertencias == 1 else "kits"} '
            "por debajo de Recomendado</div>"
        )

    clase = "" if not clases else " " + " ".join(clases)
    aviso = "".join(avisos)
    descripcion = (
        f"{total_kits} "
        f'{"kit activo" if total_kits == 1 else "kits activos"}. '
        "Precios según la calculadora."
    )

    return f"""
<script id="dv-dashboard-kits-script">
(function(){{
    function agregarKits(){{
        var acciones = document.querySelector('.acciones');
        if (!acciones || document.getElementById('dv-dashboard-kits')) return;

        var enlace = document.createElement('a');
        enlace.id = 'dv-dashboard-kits';
        enlace.href = {json.dumps(kits_url)};
        enlace.className = 'accion{clase}';
        enlace.innerHTML = `
            <div class="accion-icono">🧰</div>
            <div>
                <div class="accion-titulo">Kits</div>
                <div class="accion-texto">{descripcion}</div>
                {aviso}
            </div>
        `;
        acciones.appendChild(enlace);
    }}

    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', agregarKits);
    }} else {{
        agregarKits();
    }}
}})();
</script>
"""


def _kit_economia_html(datos_kits):
    datos_json = json.dumps(
        datos_kits,
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")

    return f"""
<script id="dv-kit-economia-script">
(function(){{
    const datosKits = {datos_json};

    function moneda(valor){{
        return new Intl.NumberFormat('es-AR', {{
            maximumFractionDigits: 0
        }}).format(Number(valor || 0));
    }}

    function porcentaje(valor){{
        if (valor === null || valor === undefined || valor === '') return '—';
        return new Intl.NumberFormat('es-AR', {{
            minimumFractionDigits: 1,
            maximumFractionDigits: 1
        }}).format(Number(valor)) + '%';
    }}

    function escapar(texto){{
        const div = document.createElement('div');
        div.textContent = texto || '';
        return div.innerHTML;
    }}

    function tipoDelItem(select){{
        const item = select.closest('.item');
        if (!item) return 'KIT';
        const tipo = item.querySelector('select[id^="tipo_item_"]');
        return tipo ? tipo.value : 'KIT';
    }}

    function cajaPara(select){{
        const item = select.closest('.item');
        if (!item) return null;

        let caja = item.querySelector(
            `.dv-kit-economia[data-kit-select="${{select.id}}"]`
        );
        if (caja) return caja;

        caja = document.createElement('div');
        caja.className = 'dv-kit-economia';
        caja.dataset.kitSelect = select.id;
        caja.hidden = true;

        const ancla =
            select.closest('.selector-kit')
            || select.closest('.full.bloque-kit')
            || select.parentElement;
        if (ancla) ancla.insertAdjacentElement('afterend', caja);
        return caja;
    }}

    function tituloEstado(info){{
        if (info.estado === 'REVISAR') return '⚠ REVISAR PRECIO DEL KIT';
        if (info.estado === 'ADVERTENCIA') return '● BAJO RECOMENDADO';
        if (info.estado === 'SIN_DATOS') return '⚠ SIN DATOS DE COSTO';
        return '✓ PRECIO DEL KIT OK';
    }}

    function actualizar(select){{
        const caja = cajaPara(select);
        if (!caja) return;

        if (tipoDelItem(select) !== 'KIT' || !select.value){{
            caja.hidden = true;
            return;
        }}

        const info = datosKits[String(select.value)];
        if (!info){{
            caja.hidden = true;
            return;
        }}

        caja.hidden = false;
        caja.classList.toggle(
            'dv-kit-alerta',
            info.estado === 'REVISAR' || info.estado === 'SIN_DATOS'
        );
        caja.classList.toggle(
            'dv-kit-advertencia',
            info.estado === 'ADVERTENCIA'
        );

        let datos;
        if (info.modalidad === 'FIJO'){{
            datos =
                `Precio $${{moneda(info.precio)}} · `
                + `costo actual $${{moneda(info.costo_estimado)}} · `
                + `margen ${{porcentaje(info.margen_estimado)}}`;
        }} else {{
            datos =
                `Precio $${{moneda(info.precio)}} · `
                + `costo promedio $${{moneda(info.costo_estimado)}} · `
                + `margen promedio ${{porcentaje(info.margen_estimado)}} · `
                + `peor caso ${{porcentaje(info.margen_peor_caso)}}`;
        }}

        let html =
            `<div class="dv-kit-economia-titulo">${{tituloEstado(info)}}</div>`
            + `<div class="dv-kit-economia-datos">${{datos}}</div>`;

        if (info.motivo){{
            html +=
                `<div class="dv-kit-economia-motivo">${{escapar(info.motivo)}}</div>`;
        }}

        if (info.disponible){{
            html += `
                <div class="dv-kit-economia-escenarios">
                    <span class="dv-kit-economia-chip">AGRESIVO $${{moneda(info.precio_agresivo)}}</span>
                    <span class="dv-kit-economia-chip recomendado">RECOMENDADO $${{moneda(info.precio_recomendado)}}</span>
                    <span class="dv-kit-economia-chip">CONSERVADOR $${{moneda(info.precio_conservador)}}</span>
                </div>
            `;
        }}

        if (caja.innerHTML !== html) caja.innerHTML = html;
    }}

    function instalar(select){{
        if (!select || select.dataset.dvKitEconomia === '1'){{
            if (select) actualizar(select);
            return;
        }}
        select.dataset.dvKitEconomia = '1';
        select.addEventListener('change', function(){{actualizar(select);}});
        actualizar(select);
    }}

    function buscarEn(nodo){{
        if (!nodo || nodo.nodeType !== 1) return;
        if (nodo.matches && nodo.matches('select[id^="kit_"]')) instalar(nodo);
        if (nodo.querySelectorAll){{
            nodo.querySelectorAll('select[id^="kit_"]').forEach(instalar);
        }}
    }}

    function iniciar(){{
        document.querySelectorAll('select[id^="kit_"]').forEach(instalar);

        document.addEventListener('change', function(evento){{
            const objetivo = evento.target;
            if (!objetivo || !objetivo.matches) return;
            if (objetivo.matches('select[id^="tipo_item_"]')){{
                const item = objetivo.closest('.item');
                if (!item) return;
                const kitSelect = item.querySelector('select[id^="kit_"]');
                if (kitSelect) actualizar(kitSelect);
            }}
        }});

        const observador = new MutationObserver(function(mutaciones){{
            mutaciones.forEach(function(mutacion){{
                mutacion.addedNodes.forEach(buscarEn);
            }});
        }});
        observador.observe(document.body, {{childList:true, subtree:true}});
    }}

    if (document.readyState === 'loading'){{
        document.addEventListener('DOMContentLoaded', iniciar);
    }} else {{
        iniciar();
    }}
}})();
</script>
"""


def aplicar():
    import config.ui_middleware as ui

    if getattr(ui, "_kits_ui_alineado", False):
        return

    ui._datos_economicos_kits = _datos_economicos_kits
    ui._dashboard_kits_html = _dashboard_kits_html
    ui._kit_economia_html = _kit_economia_html
    ui.DASHBOARD_KITS_STYLE = DASHBOARD_KITS_STYLE
    ui.KIT_ECONOMIA_STYLE = KIT_ECONOMIA_STYLE
    ui._kits_ui_alineado = True
