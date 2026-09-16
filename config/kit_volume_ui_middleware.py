import json

from django.urls import reverse


KIT_VOLUME_STYLE = r"""
<style id="dv-kit-volume-style">
.dv-kit-volumen-resumen{
    display:none;
    margin-top:16px;
    padding:16px;
    border:1px solid #d9dce2;
    border-radius:16px;
    background:#f7f8fa;
    color:#30343a;
    font-family:Arial,sans-serif;
}
.dv-kit-volumen-resumen.activo{display:block}
.dv-kit-volumen-resumen.elegible{
    border-color:#b8d8c4;
    background:#eef9f2;
    color:#245638;
}
.dv-kit-volumen-resumen.limitado{
    border-color:#e5d0a8;
    background:#fff8e9;
    color:#70511e;
}
.dv-kit-volumen-titulo{
    font-size:10px;
    font-weight:900;
    letter-spacing:.35px;
    text-transform:uppercase;
}
.dv-kit-volumen-principal{
    margin-top:7px;
    font-size:13px;
    font-weight:900;
    line-height:1.45;
}
.dv-kit-volumen-datos{
    display:flex;
    flex-wrap:wrap;
    gap:7px 14px;
    margin-top:8px;
    font-size:10px;
    font-weight:800;
    line-height:1.45;
}
.dv-kit-volumen-ayuda{
    margin-top:8px;
    font-size:10px;
    line-height:1.45;
}
.dv-kit-volumen-lineas{
    display:grid;
    gap:6px;
    margin-top:10px;
}
.dv-kit-volumen-linea{
    padding:8px 10px;
    border-radius:10px;
    background:rgba(255,255,255,.72);
    font-size:10px;
    font-weight:800;
    line-height:1.4;
}
@media(max-width:720px){
    .dv-kit-volumen-resumen{padding:13px}
    .dv-kit-volumen-datos{display:grid;grid-template-columns:1fr 1fr}
}
</style>
"""


def _script_precio_kits():
    endpoint = json.dumps(reverse("pedidos:precio_kits_volumen"))

    return rf"""
<script id="dv-kit-volume-script">
(function(){{
    const endpoint = {endpoint};
    let timer = null;
    let secuencia = 0;

    function moneda(valor){{
        return new Intl.NumberFormat('es-AR', {{
            maximumFractionDigits: 2
        }}).format(Number(valor || 0));
    }}

    function porcentaje(valor){{
        return new Intl.NumberFormat('es-AR', {{
            minimumFractionDigits: 1,
            maximumFractionDigits: 1
        }}).format(Number(valor || 0)) + '%';
    }}

    function escapar(texto){{
        const div = document.createElement('div');
        div.textContent = String(texto || '');
        return div.innerHTML;
    }}

    function asegurarPanel(){{
        let panel = document.getElementById('dv-kit-volumen-resumen');
        if (panel) return panel;

        const items = document.getElementById('items');
        if (!items) return null;

        const tarjeta = items.closest('.tarjeta');
        if (!tarjeta) return null;

        panel = document.createElement('div');
        panel.id = 'dv-kit-volumen-resumen';
        panel.className = 'dv-kit-volumen-resumen';

        const agregar = tarjeta.querySelector('.boton-agregar');
        if (agregar){{
            agregar.insertAdjacentElement('afterend', panel);
        }} else {{
            tarjeta.appendChild(panel);
        }}

        return panel;
    }}

    function obtenerIndice(item){{
        const hidden = item.querySelector('input[name="item_indice"]');
        return hidden ? String(hidden.value || '') : '';
    }}

    function recolectar(){{
        const items = [];

        document.querySelectorAll('#items .item').forEach(function(item){{
            const indice = obtenerIndice(item);
            if (!indice) return;

            const tipo = item.querySelector(`#tipo_item_${{indice}}`);
            const kit = item.querySelector(`#kit_${{indice}}`);
            const cantidad = item.querySelector(`#cantidad_${{indice}}`);

            if (!tipo || tipo.value !== 'KIT' || !kit || !kit.value) return;

            const productos = Array.from(
                item.querySelectorAll(`select[name="productos_kit_${{indice}}"]`)
            ).map(function(select){{
                return select.value;
            }}).filter(Boolean);

            items.push({{
                key: indice,
                kit_id: Number(kit.value),
                cantidad: Math.max(Number(cantidad && cantidad.value || 1), 1),
                productos: productos
            }});
        }});

        return items;
    }}

    function mostrarError(panel, mensaje){{
        panel.className = 'dv-kit-volumen-resumen activo';
        panel.innerHTML = `
            <div class="dv-kit-volumen-titulo">Precio por volumen de kits</div>
            <div class="dv-kit-volumen-ayuda">${{escapar(mensaje)}}</div>
        `;
    }}

    function renderizar(panel, datos){{
        panel.className = 'dv-kit-volumen-resumen activo';

        if (!datos.elegible){{
            panel.innerHTML = `
                <div class="dv-kit-volumen-titulo">Precio por volumen de kits</div>
                <div class="dv-kit-volumen-principal">
                    ${{datos.total_kits}} ${{datos.total_kits === 1 ? 'kit' : 'kits'}} ·
                    ${{datos.total_piezas}} piezas agrupadas
                </div>
                <div class="dv-kit-volumen-ayuda">
                    El precio de lista se mantiene. Desde ${{datos.cantidad_minima_kits}} kits,
                    el sistema evalúa automáticamente el volumen real de piezas para calcular
                    un precio mayorista rentable.
                </div>
            `;
            return;
        }}

        const tieneAhorro = Number(datos.ahorro || 0) > 0;
        const limitado = !!datos.limitado_por_margen;
        const ajustadoMercado = !!datos.ajustado_por_precio_real;

        panel.classList.add(tieneAhorro ? 'elegible' : 'limitado');
        if (limitado) panel.classList.add('limitado');

        let principal;
        if (tieneAhorro){{
            principal = `
                Precio lista $${{moneda(datos.precio_lista_total)}} →
                <strong>$${{moneda(datos.precio_final_total)}}</strong>
            `;
        }} else {{
            principal = 'Volumen mayorista detectado · se mantiene el precio actual';
        }}

        const lineas = (datos.lineas || [])
            .filter(function(linea){{ return Number(linea.ahorro || 0) > 0; }})
            .map(function(linea){{
                return `
                    <div class="dv-kit-volumen-linea">
                        ${{escapar(linea.kit_nombre)}} · ${{linea.cantidad}} kits ·
                        $${{moneda(linea.precio_unitario_lista)}}/u →
                        $${{moneda(linea.precio_unitario_final)}}/u
                        · ${{porcentaje(linea.descuento_porcentaje)}}
                    </div>
                `;
            }}).join('');

        let ayuda;
        if (tieneAhorro){{
            ayuda =
                `El precio se aplica automáticamente al guardar. `
                + `El descuento usa las piezas reales contenidas en todos los kits y `
                + `no permite bajar del margen mínimo de ${{porcentaje(datos.margen_minimo)}}.`;

            if (ajustadoMercado){{
                ayuda +=
                    ` El porcentaje de volumen se calcula con la referencia técnica, `
                    + `pero se aplica sobre el precio real que configuraste para el kit, `
                    + `conservando su posicionamiento de mercado.`;
            }}
        }} else {{
            ayuda =
                `La cantidad habilita precio por volumen, pero los precios actuales ya están `
                + `en el nivel recomendado o no tienen margen suficiente para reducirse más.`;
        }}

        if (limitado && tieneAhorro){{
            ayuda += ' El ahorro fue limitado para proteger la rentabilidad.';
        }}

        const referenciaMercado = ajustadoMercado
            ? `<span>Referencia técnica $${{moneda(datos.precio_referencia_conservador_total)}}</span>`
            : '';

        panel.innerHTML = `
            <div class="dv-kit-volumen-titulo">Compra mayorista de kits</div>
            <div class="dv-kit-volumen-principal">${{principal}}</div>
            <div class="dv-kit-volumen-datos">
                <span>${{datos.total_kits}} kits</span>
                <span>${{datos.total_piezas}} piezas agrupadas</span>
                <span>Margen objetivo ${{porcentaje(datos.margen_objetivo)}}</span>
                <span>Margen final ${{porcentaje(datos.margen_real)}}</span>
                <span>Ahorro $${{moneda(datos.ahorro)}} (${{porcentaje(datos.descuento_porcentaje)}})</span>
                ${{referenciaMercado}}
            </div>
            <div class="dv-kit-volumen-ayuda">${{ayuda}}</div>
            ${{lineas ? `<div class="dv-kit-volumen-lineas">${{lineas}}</div>` : ''}}
        `;
    }}

    async function actualizar(){{
        const panel = asegurarPanel();
        if (!panel) return;

        const items = recolectar();
        if (!items.length){{
            panel.className = 'dv-kit-volumen-resumen';
            panel.innerHTML = '';
            return;
        }}

        const csrf = document.querySelector('input[name="csrfmiddlewaretoken"]');
        if (!csrf || !csrf.value){{
            mostrarError(panel, 'No se pudo validar la sesión para calcular el precio.');
            return;
        }}

        const miSecuencia = ++secuencia;
        panel.className = 'dv-kit-volumen-resumen activo';
        panel.innerHTML = `
            <div class="dv-kit-volumen-titulo">Precio por volumen de kits</div>
            <div class="dv-kit-volumen-ayuda">Calculando volumen real de piezas…</div>
        `;

        try{{
            const respuesta = await fetch(endpoint, {{
                method: 'POST',
                headers: {{
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrf.value,
                    'X-Requested-With': 'XMLHttpRequest'
                }},
                body: JSON.stringify({{items: items}})
            }});

            const datos = await respuesta.json();
            if (miSecuencia !== secuencia) return;

            if (!respuesta.ok || !datos.ok){{
                throw new Error(datos.mensaje || 'No se pudo calcular el precio por volumen.');
            }}

            renderizar(panel, datos);
        }}catch(error){{
            if (miSecuencia !== secuencia) return;
            mostrarError(panel, error.message || 'No se pudo calcular el precio por volumen.');
        }}
    }}

    function programar(){{
        clearTimeout(timer);
        timer = setTimeout(actualizar, 280);
    }}

    function iniciar(){{
        asegurarPanel();

        document.addEventListener('change', function(evento){{
            const objetivo = evento.target;
            if (!objetivo || !objetivo.closest || !objetivo.closest('#items')) return;
            programar();
        }});

        document.addEventListener('input', function(evento){{
            const objetivo = evento.target;
            if (!objetivo || !objetivo.closest || !objetivo.closest('#items')) return;
            if (objetivo.matches('input[id^="cantidad_"]')) programar();
        }});

        const items = document.getElementById('items');
        if (items){{
            const observador = new MutationObserver(programar);
            observador.observe(items, {{childList:true, subtree:true}});
        }}

        programar();
    }}

    if (document.readyState === 'loading'){{
        document.addEventListener('DOMContentLoaded', iniciar);
    }} else {{
        iniciar();
    }}
}})();
</script>
"""


class KitVolumeUIMiddleware:
    """Agrega la vista previa mayorista únicamente a Nuevo/Editar Pedido."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if getattr(response, "streaming", False):
            return response

        if "text/html" not in response.get("Content-Type", ""):
            return response

        resolver = getattr(request, "resolver_match", None)
        view_name = resolver.view_name if resolver else ""
        if view_name not in {"pedidos:nuevo", "pedidos:editar"}:
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if "</head>" in html and "dv-kit-volume-style" not in html:
            html = html.replace(
                "</head>",
                KIT_VOLUME_STYLE + "\n</head>",
                1,
            )

        if "</body>" in html and "dv-kit-volume-script" not in html:
            html = html.replace(
                "</body>",
                _script_precio_kits() + "\n</body>",
                1,
            )

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
