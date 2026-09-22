"""UX compartida para Nuevo Pedido y Editar Pedido.

Los templates de ambas pantallas son históricos y tienen estructuras distintas.
Este middleware agrega una capa común sin duplicar formularios: precio acordado
para KIT, jerarquía visual, estados automático/manual y mejoras responsive.
"""

import json

from django.urls import reverse


PEDIDO_FORM_STYLE = r"""
<style id="dv-pedido-form-style">
body.dv-pedido-form-page{
    --dv-ink:#25282d;
    --dv-muted:#727780;
    --dv-line:#e2e5e9;
    --dv-soft:#f7f8fa;
    --dv-blue:#315f9f;
    --dv-blue-bg:#eef5ff;
    --dv-green:#25603c;
    --dv-green-bg:#eef8f2;
    --dv-amber:#7b581c;
    --dv-amber-bg:#fff8e8;
}

body.dv-pedido-form-page form > .tarjeta,
body.dv-pedido-form-page form > .card{
    border-color:#e1e4e8!important;
    box-shadow:0 5px 20px rgba(28,33,40,.055)!important;
}

.dv-items-heading{
    display:flex;
    align-items:flex-end;
    justify-content:space-between;
    gap:16px;
    margin:22px 2px 10px;
}
.dv-items-heading-main{
    font-size:15px;
    font-weight:900;
    color:var(--dv-ink);
}
.dv-items-heading-help{
    margin-top:4px;
    max-width:680px;
    color:var(--dv-muted);
    font-size:10px;
    line-height:1.45;
}
.dv-items-count{
    flex:0 0 auto;
    padding:7px 10px;
    border-radius:999px;
    background:#e9ebee;
    color:#555b63;
    font-size:9px;
    font-weight:900;
}

body.dv-pedido-form-page .item{
    overflow:visible;
    border:1px solid #dfe3e8!important;
    border-left:4px solid #aeb5bf!important;
    border-radius:18px!important;
    background:#fff!important;
    box-shadow:0 3px 14px rgba(28,33,40,.045)!important;
}
body.dv-pedido-form-page .item[data-dv-kind="PRODUCTO"]{
    border-left-color:#6f96c7!important;
}
body.dv-pedido-form-page .item[data-dv-kind="KIT"]{
    border-left-color:#6f9f7f!important;
}
body.dv-pedido-form-page .item[data-dv-kind="PERSONALIZADO"]{
    border-left-color:#9a79bd!important;
}

.dv-item-kind{
    display:inline-flex;
    align-items:center;
    min-height:27px;
    margin-left:7px;
    padding:0 9px;
    border-radius:999px;
    background:#f0f2f4;
    color:#676d75;
    font-size:8px;
    font-weight:900;
    letter-spacing:.2px;
}

body.dv-pedido-form-page input,
body.dv-pedido-form-page select,
body.dv-pedido-form-page textarea{
    transition:border-color .15s ease,box-shadow .15s ease,background .15s ease;
}
body.dv-pedido-form-page input:focus,
body.dv-pedido-form-page select:focus,
body.dv-pedido-form-page textarea:focus{
    outline:none!important;
    border-color:#8fa9c8!important;
    box-shadow:0 0 0 3px rgba(87,124,166,.12)!important;
}

.dv-kit-price-box{
    margin-top:13px;
    padding:15px;
    border:1px solid #cfe1d5;
    border-radius:15px;
    background:#f6fbf8;
}
.dv-kit-price-box.dv-hidden{display:none!important}
.dv-kit-price-head{
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    gap:12px;
    margin-bottom:12px;
}
.dv-kit-price-title{
    font-size:10px;
    font-weight:900;
    color:#294936;
    letter-spacing:.2px;
}
.dv-kit-price-help{
    margin-top:4px;
    color:#65766b;
    font-size:9px;
    line-height:1.45;
}
.dv-kit-price-state{
    flex:0 0 auto;
    padding:6px 9px;
    border-radius:999px;
    background:#e3f1e8;
    color:#356247;
    font-size:8px;
    font-weight:900;
}
.dv-kit-price-state.manual{
    background:#fff0ce;
    color:#765518;
}
.dv-kit-price-grid{
    display:grid;
    grid-template-columns:minmax(190px,240px) minmax(170px,1fr) auto;
    gap:10px;
    align-items:end;
}
.dv-kit-price-total{
    min-height:50px;
    display:flex;
    align-items:center;
    padding:10px 12px;
    border:1px solid #dce5df;
    border-radius:12px;
    background:#fff;
    color:#314238;
    font-size:11px;
    font-weight:900;
}
.dv-kit-auto-btn{
    min-height:50px;
    padding:0 13px;
    border:1px solid #cfd8d2;
    border-radius:12px;
    background:#fff;
    color:#3d5546;
    font-size:8px;
    font-weight:900;
    cursor:pointer;
    white-space:nowrap;
}
.dv-kit-reference{
    margin-top:9px;
    padding:8px 10px;
    border-radius:10px;
    background:#edf4ef;
    color:#50645a;
    font-size:9px;
    line-height:1.4;
}
.dv-kit-reference strong{color:#294936}

.dv-manual-volume-note{
    margin-top:9px;
    padding:9px 11px;
    border:1px solid #e8cf9b;
    border-radius:10px;
    background:#fff8e8;
    color:#6f501d;
    font-size:9px;
    font-weight:800;
    line-height:1.4;
}

body.dv-pedido-form-page .item > .grid{
    align-items:start!important;
}
body.dv-pedido-form-page .kit-box,
body.dv-pedido-form-page .personal-box,
body.dv-pedido-form-page .precio-box,
body.dv-pedido-form-page .componentes-kit,
body.dv-pedido-form-page .selector-personalizado,
body.dv-pedido-form-page .precio-producto-box{
    box-shadow:none!important;
}

@media(min-width:761px){
    body.dv-pedido-form-page .item{
        padding:18px!important;
    }
    body.dv-pedido-form-page .item > .grid{
        column-gap:12px!important;
        row-gap:12px!important;
    }
}

@media(max-width:760px){
    .dv-items-heading{
        align-items:flex-start;
        flex-direction:column;
        gap:8px;
    }
    .dv-kit-price-grid{
        grid-template-columns:1fr;
    }
    .dv-kit-auto-btn{width:100%}
    .dv-kit-price-head{
        flex-direction:column;
        gap:8px;
    }
    body.dv-pedido-form-page .item{
        border-left-width:3px!important;
    }
}
</style>
"""


PEDIDO_FORM_SCRIPT = r"""
<script id="dv-pedido-form-script">
(function(){
    const cacheKits = new Map();
    let timer = null;

    function moneda(valor){
        return new Intl.NumberFormat('es-AR', {
            minimumFractionDigits: 0,
            maximumFractionDigits: 2
        }).format(Number(valor || 0));
    }

    function textoSiCambio(elemento, texto){
        if (elemento && elemento.textContent !== texto) {
            elemento.textContent = texto;
        }
    }

    function htmlSiCambio(elemento, html){
        if (elemento && elemento.innerHTML !== html) {
            elemento.innerHTML = html;
        }
    }

    function indiceDe(item){
        const campo = item.querySelector('input[name="item_indice"]');
        return campo ? String(campo.value || '') : '';
    }

    function iniciales(){
        const script = document.getElementById('items-iniciales');
        if (!script) return [];
        try { return JSON.parse(script.textContent || '[]'); }
        catch(error){ return []; }
    }

    const inicialPorDetalle = new Map(
        iniciales().filter(Boolean).map(function(item){
            return [String(item.id || ''), item];
        })
    );

    function inicialDelItem(item, indice){
        const hidden = item.querySelector(`[name="detalle_id_${indice}"]`);
        if (!hidden || !hidden.value) return null;
        return inicialPorDetalle.get(String(hidden.value)) || null;
    }

    async function datosKit(kitId){
        const key = String(kitId || '');
        if (!key) return null;
        if (cacheKits.has(key)) return cacheKits.get(key);

        const url = __KIT_PRODUCTOS_ENDPOINT__.replace(
            "999999",
            encodeURIComponent(key)
        );
        const promesa = fetch(url, {
            headers:{'X-Requested-With':'XMLHttpRequest'}
        }).then(function(respuesta){
            if (!respuesta.ok) throw new Error('No se pudo cargar el kit.');
            return respuesta.json();
        });

        cacheKits.set(key, promesa);
        try { return await promesa; }
        catch(error){ cacheKits.delete(key); throw error; }
    }

    function precioAutomaticoKit(item, indice, data){
        const base = Number(data?.kit?.precio || 0);
        let extra = 0;

        if (
            data?.kit?.modalidad === 'LIBRE_CATEGORIA'
            && data?.kit?.proteger_rentabilidad
        ){
            const porId = new Map(
                (data.productos || []).map(function(producto){
                    return [String(producto.id), Number(producto.extra || 0)];
                })
            );

            item.querySelectorAll(
                `select[name="productos_kit_${indice}"]`
            ).forEach(function(select){
                extra += porId.get(String(select.value || '')) || 0;
            });
        }

        return {
            base:base,
            extra:extra,
            total:base + extra
        };
    }

    function actualizarTotal(item, indice){
        const cantidad = Number(
            item.querySelector(`#cantidad_${indice}`)?.value || 0
        );
        const precio = Number(
            item.querySelector(`#precio_unitario_kit_${indice}`)?.value || 0
        );
        const total = item.querySelector(`#dv_kit_total_${indice}`);
        const texto = cantidad > 0 && precio > 0
            ? `Total del kit: $${moneda(cantidad * precio)}`
            : 'Total del kit: —';
        textoSiCambio(total, texto);
    }

    function pintarEstado(item, indice){
        const manual = item.querySelector(`#precio_kit_manual_${indice}`)?.value === '1';
        const estado = item.querySelector(`#dv_kit_estado_${indice}`);
        if (!estado) return;

        textoSiCambio(estado, manual ? 'PRECIO ACORDADO' : 'AUTOMÁTICO');
        estado.classList.toggle('manual', manual);
    }

    function crearCaja(item, indice){
        let caja = item.querySelector(`#dv_kit_price_${indice}`);
        if (caja) return caja;

        caja = document.createElement('div');
        caja.id = `dv_kit_price_${indice}`;
        caja.className = 'dv-kit-price-box bloque-kit dv-hidden';
        caja.innerHTML = `
            <div class="dv-kit-price-head">
                <div>
                    <div class="dv-kit-price-title">PRECIO DEL KIT</div>
                    <div class="dv-kit-price-help">
                        Podés mantener el cálculo automático o escribir el precio unitario acordado con el cliente.
                    </div>
                </div>
                <div class="dv-kit-price-state" id="dv_kit_estado_${indice}">AUTOMÁTICO</div>
            </div>
            <div class="dv-kit-price-grid">
                <div>
                    <label>PRECIO UNITARIO ACORDADO</label>
                    <input
                        type="number"
                        min="0.01"
                        step="0.01"
                        name="precio_unitario_kit_${indice}"
                        id="precio_unitario_kit_${indice}"
                        inputmode="decimal"
                    >
                    <input
                        type="hidden"
                        name="precio_kit_manual_${indice}"
                        id="precio_kit_manual_${indice}"
                        value="0"
                    >
                </div>
                <div>
                    <label>TOTAL DEL ITEM</label>
                    <div class="dv-kit-price-total" id="dv_kit_total_${indice}">Total del kit: —</div>
                </div>
                <button type="button" class="dv-kit-auto-btn" id="dv_kit_auto_${indice}">
                    USAR PRECIO AUTOMÁTICO
                </button>
            </div>
            <div class="dv-kit-reference" id="dv_kit_ref_${indice}">
                Seleccioná un kit para cargar su precio de lista.
            </div>
        `;

        const antes = item.querySelector('.kit-box.bloque-kit, .componentes-kit');
        if (antes) antes.insertAdjacentElement('beforebegin', caja);
        else item.appendChild(caja);

        const precio = caja.querySelector(`#precio_unitario_kit_${indice}`);
        const manual = caja.querySelector(`#precio_kit_manual_${indice}`);
        const boton = caja.querySelector(`#dv_kit_auto_${indice}`);

        precio.addEventListener('input', function(){
            manual.value = '1';
            pintarEstado(item, indice);
            actualizarTotal(item, indice);
            actualizarNotaVolumen();
        });

        boton.addEventListener('click', function(){
            const automatico = Number(caja.dataset.precioAutomatico || 0);
            if (automatico > 0) precio.value = automatico.toFixed(2);
            manual.value = '0';
            pintarEstado(item, indice);
            actualizarTotal(item, indice);
            actualizarNotaVolumen();
        });

        return caja;
    }

    async function prepararKit(item){
        const indice = indiceDe(item);
        if (!indice) return;

        const tipo = item.querySelector(`#tipo_item_${indice}`);
        const selector = item.querySelector(`#kit_${indice}`);
        const caja = crearCaja(item, indice);

        const esKit = !!tipo && tipo.value === 'KIT';
        caja.classList.toggle('dv-hidden', !esKit);

        const kind = tipo?.value || '';
        if (item.dataset.dvKind !== kind) item.dataset.dvKind = kind;
        actualizarBadge(item, kind);

        if (!esKit || !selector || !selector.value){
            return;
        }

        const kitId = String(selector.value);
        const cambioKit = !!caja.dataset.kitId && caja.dataset.kitId !== kitId;

        try{
            const data = await datosKit(kitId);
            if (!data || String(selector.value) !== kitId) return;

            const precioLista = Number(data.kit?.precio || 0);
            const automatico = precioAutomaticoKit(
                item,
                indice,
                data
            );
            caja.dataset.precioLista = String(precioLista || 0);
            caja.dataset.precioAutomatico = String(
                automatico.total || 0
            );

            const precio = caja.querySelector(`#precio_unitario_kit_${indice}`);
            const manual = caja.querySelector(`#precio_kit_manual_${indice}`);
            const referencia = caja.querySelector(`#dv_kit_ref_${indice}`);
            const existente = inicialDelItem(item, indice);
            const coincideInicial = existente && String(existente.kit_id || '') === kitId;

            if (!caja.dataset.kitId || cambioKit){
                manual.value = (
                    coincideInicial
                    && !cambioKit
                    && existente.precio_kit_manual
                ) ? '1' : '0';
                caja.dataset.kitId = kitId;
            }

            if (manual.value !== '1'){
                precio.value = automatico.total > 0
                    ? automatico.total.toFixed(2)
                    : '';
            } else if (!precio.value && coincideInicial) {
                const historico = Number(existente.precio_unitario || 0);
                precio.value = historico > 0
                    ? historico.toFixed(2)
                    : '';
            }

            let refHtml = precioLista > 0
                ? `Precio base del kit: <strong>${moneda(precioLista)}/u</strong>. `
                : 'Este kit no tiene un precio de lista válido.';

            if (
                data.kit?.modalidad === 'LIBRE_CATEGORIA'
                && data.kit?.proteger_rentabilidad
                && automatico.extra > 0
            ){
                refHtml += `Extras por selección: <strong>+${moneda(automatico.extra)}</strong>. Precio automático <strong>${moneda(automatico.total)}/u</strong>. `;
            } else if (
                data.kit?.modalidad === 'LIBRE_CATEGORIA'
                && data.kit?.proteger_rentabilidad
            ){
                refHtml += 'La selección actual está completamente incluida. ';
            }

            refHtml += manual.value === '1'
                ? 'El importe acordado manualmente prevalece.'
                : 'Si el pedido califica por volumen, el sistema puede recalcularlo al guardar.';
            htmlSiCambio(referencia, refHtml);

            pintarEstado(item, indice);
            actualizarTotal(item, indice);
        }catch(error){
            const referencia = caja.querySelector(`#dv_kit_ref_${indice}`);
            textoSiCambio(
                referencia,
                'No se pudo cargar la referencia de precio del kit.'
            );
        }
    }

    function actualizarBadge(item, tipo){
        const head = item.querySelector('.item-encabezado, .item-head');
        if (!head) return;
        let badge = head.querySelector('.dv-item-kind');
        if (!badge){
            badge = document.createElement('span');
            badge.className = 'dv-item-kind';
            const titulo = head.querySelector('.item-numero, .item-title');
            if (titulo) titulo.insertAdjacentElement('afterend', badge);
            else head.prepend(badge);
        }
        const texto = tipo === 'KIT'
            ? 'KIT'
            : (tipo === 'PERSONALIZADO' ? 'PERSONALIZADO' : 'PRODUCTO');
        textoSiCambio(badge, texto);
    }

    function actualizarContador(){
        const contador = document.querySelector('.dv-items-count');
        if (!contador) return;
        const cantidad = document.querySelectorAll('#items .item').length;
        textoSiCambio(
            contador,
            `${cantidad} ${cantidad === 1 ? 'ITEM' : 'ITEMS'}`
        );
    }

    function asegurarEncabezadoItems(){
        const items = document.getElementById('items');
        if (!items || document.querySelector('.dv-items-heading')) return;

        const encabezado = document.createElement('div');
        encabezado.className = 'dv-items-heading';
        encabezado.innerHTML = `
            <div>
                <div class="dv-items-heading-main">Ítems del pedido</div>
                <div class="dv-items-heading-help">
                    Elegí el tipo, la cantidad y el precio acordado. En kits podés conservar el cálculo automático o fijar un importe con el cliente.
                </div>
            </div>
            <div class="dv-items-count">0 ITEMS</div>
        `;
        items.insertAdjacentElement('beforebegin', encabezado);
    }

    function actualizarNotaVolumen(){
        const panel = document.getElementById('dv-kit-volumen-resumen');
        if (!panel) return;

        const manuales = Array.from(
            document.querySelectorAll('input[id^="precio_kit_manual_"]')
        ).filter(function(input){
            const item = input.closest('.item');
            const indice = item ? indiceDe(item) : '';
            const tipo = indice ? item.querySelector(`#tipo_item_${indice}`) : null;
            return input.value === '1' && tipo?.value === 'KIT';
        }).length;

        let nota = panel.querySelector('.dv-manual-volume-note');
        if (manuales > 0){
            if (!nota){
                nota = document.createElement('div');
                nota.className = 'dv-manual-volume-note';
                panel.appendChild(nota);
            }
            const texto = manuales === 1
                ? 'Hay un kit con precio acordado manualmente. Ese importe prevalece al guardar; el cálculo mayorista se mantiene como referencia.'
                : `Hay ${manuales} kits con precio acordado manualmente. Esos importes prevalecen al guardar; el cálculo mayorista se mantiene como referencia.`;
            textoSiCambio(nota, texto);
        } else if (nota){
            nota.remove();
        }
    }

    function prepararTodo(){
        document.body.classList.add('dv-pedido-form-page');
        asegurarEncabezadoItems();
        document.querySelectorAll('#items .item').forEach(function(item){
            prepararKit(item);
        });
        actualizarContador();
        actualizarNotaVolumen();
    }

    function programar(){
        clearTimeout(timer);
        timer = setTimeout(prepararTodo, 40);
    }

    function iniciar(){
        prepararTodo();

        document.addEventListener('change', function(evento){
            if (!evento.target?.closest?.('#items')) return;
            programar();
        });
        document.addEventListener('input', function(evento){
            if (!evento.target?.closest?.('#items')) return;
            const item = evento.target.closest('.item');
            if (item){
                const indice = indiceDe(item);
                if (indice && evento.target.id === `cantidad_${indice}`){
                    actualizarTotal(item, indice);
                }
            }
            programar();
        });

        const items = document.getElementById('items');
        if (items){
            new MutationObserver(programar).observe(items, {
                childList:true,
                subtree:true
            });
        }

        new MutationObserver(function(){
            actualizarNotaVolumen();
        }).observe(document.body, {childList:true, subtree:true});
    }

    if (document.readyState === 'loading'){
        document.addEventListener('DOMContentLoaded', iniciar);
    } else {
        iniciar();
    }
})();
</script>
"""


def _pedido_form_script():
    endpoint = json.dumps(
        reverse("pedidos:productos_kit", args=[999999])
    )
    return PEDIDO_FORM_SCRIPT.replace(
        "__KIT_PRODUCTOS_ENDPOINT__",
        endpoint,
    )


class PedidoFormUIMiddleware:
    """Inyecta UX común sólo en los formularios Nuevo/Editar Pedido."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if (
            getattr(response, "streaming", False)
            or "text/html" not in response.get("Content-Type", "")
        ):
            return response

        resolver = getattr(request, "resolver_match", None)
        view_name = resolver.view_name if resolver else ""
        if view_name not in {"pedidos:nuevo", "pedidos:editar", "pedidos:presupuesto_editar"}:
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if "dv-pedido-form-style" not in html and "</head>" in html:
            html = html.replace(
                "</head>",
                PEDIDO_FORM_STYLE + "\n</head>",
                1,
            )

        if "dv-pedido-form-script" not in html and "</body>" in html:
            html = html.replace(
                "</body>",
                _pedido_form_script() + "\n</body>",
                1,
            )

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
