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

/* Resumen y guía compartidos de Nuevo / Editar Pedido */
body.dv-pedido-form-page .contenedor{
    width:min(1180px,100%)!important;
}
.dv-order-guide{
    display:grid;
    grid-template-columns:repeat(3,minmax(0,1fr));
    gap:7px;
    margin:-5px 0 14px;
    padding:7px;
    border:1px solid #e1e5ea;
    border-radius:15px;
    background:#fff;
}
.dv-order-guide a,
.dv-order-guide span{
    min-height:46px;
    display:flex;
    align-items:center;
    gap:9px;
    padding:8px 11px;
    border-radius:11px;
    color:#667085;
    text-decoration:none;
    font-size:9px;
    font-weight:900;
}
.dv-order-guide a:hover{background:#f5f7fa}
.dv-order-guide b{
    width:25px;
    height:25px;
    display:grid;
    place-items:center;
    flex:0 0 auto;
    border-radius:50%;
    background:#edf1f5;
    color:#4d5968;
    font-size:9px;
}
.dv-order-guide .is-active{
    background:#eef5ff;
    color:#245a9b;
}
.dv-order-guide .is-active b{
    background:#245a9b;
    color:#fff;
}
.dv-order-data-card{
    scroll-margin-top:14px;
}
#dv-pedido-items{
    scroll-margin-top:14px;
}
body.dv-pedido-form-page .boton-agregar,
body.dv-pedido-form-page .agregar{
    min-height:52px!important;
    border:1px dashed #9db7d8!important;
    border-radius:14px!important;
    background:#f7faff!important;
    color:#245a9b!important;
    font-size:9px!important;
    font-weight:900!important;
    box-shadow:none!important;
}
body.dv-pedido-form-page .boton-agregar:hover,
body.dv-pedido-form-page .agregar:hover{
    background:#eef5ff!important;
}
.dv-order-savebar{
    position:fixed;
    z-index:55;
    left:50%;
    bottom:84px;
    transform:translateX(-50%);
    width:min(940px,calc(100% - 24px));
    display:grid;
    grid-template-columns:minmax(0,1fr) auto auto;
    align-items:center;
    gap:12px;
    padding:10px;
    border:1px solid #dce2ea;
    border-radius:18px;
    background:rgba(255,255,255,.96);
    box-shadow:0 14px 38px rgba(24,34,48,.18);
    backdrop-filter:blur(14px);
}
.dv-order-summary-main{min-width:0;padding-left:4px}
.dv-order-summary-title{
    color:#17233a;
    font-size:11px;
    font-weight:900;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
}
.dv-order-summary-detail{
    margin-top:3px;
    color:#73777f;
    font-size:8px;
    line-height:1.35;
    white-space:nowrap;
    overflow:hidden;
    text-overflow:ellipsis;
}
.dv-order-ready{
    min-height:32px;
    display:inline-flex;
    align-items:center;
    justify-content:center;
    padding:0 10px;
    border-radius:999px;
    background:#fff6dc;
    color:#7a5615;
    font-size:8px;
    font-weight:900;
    white-space:nowrap;
}
.dv-order-ready.ok{
    background:#ecfdf3;
    color:#166534;
}
.dv-order-savebar .dv-order-save{
    position:static!important;
    inset:auto!important;
    transform:none!important;
    width:auto!important;
    min-width:190px!important;
    min-height:50px!important;
    margin:0!important;
    padding:0 18px!important;
    border:0!important;
    border-radius:13px!important;
    background:#24272b!important;
    color:#fff!important;
    font-size:9px!important;
    font-weight:900!important;
    box-shadow:none!important;
}
body.dv-pedido-form-page form > .acciones:empty{
    display:none!important;
}
body.dv-pedido-form-page{
    padding-bottom:calc(180px + env(safe-area-inset-bottom))!important;
}
@media(max-width:760px){
    .dv-order-guide{
        gap:4px;
        padding:5px;
    }
    .dv-order-guide a,
    .dv-order-guide span{
        min-height:42px;
        gap:6px;
        padding:6px;
        font-size:7px;
        justify-content:center;
    }
    .dv-order-guide b{
        width:22px;
        height:22px;
        font-size:8px;
    }
    .dv-order-savebar{
        bottom:76px;
        width:calc(100% - 12px);
        grid-template-columns:minmax(0,1fr) auto;
        gap:7px;
        padding:8px;
        border-radius:15px;
    }
    .dv-order-ready{display:none}
    .dv-order-summary-title{font-size:10px}
    .dv-order-summary-detail{font-size:7px}
    .dv-order-savebar .dv-order-save{
        min-width:138px!important;
        min-height:48px!important;
        padding:0 11px!important;
    }
}
@media(max-width:430px){
    .dv-order-guide a,
    .dv-order-guide span{
        flex-direction:column;
        gap:3px;
        text-align:center;
    }
    .dv-order-summary-detail{
        max-width:170px;
    }
    .dv-order-savebar .dv-order-save{
        min-width:125px!important;
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
            actualizarResumenPedido();
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

    function formularioPedido(){
        return document.querySelector('form[method="post"]');
    }

    function asegurarGuia(){
        if (document.querySelector('.dv-order-guide')) return;

        const form = formularioPedido();
        if (!form) return;

        const primeraCard = Array.from(form.children).find(function(elemento){
            return elemento.classList?.contains('tarjeta')
                || (
                    elemento.classList?.contains('card')
                    && elemento.classList?.contains('grid')
                );
        });
        if (primeraCard){
            primeraCard.id = primeraCard.id || 'dv-pedido-datos';
            primeraCard.classList.add('dv-order-data-card');
        }

        const items = document.getElementById('items');
        if (items){
            const heading = document.querySelector('.dv-items-heading');
            if (heading) heading.id = 'dv-pedido-items';
            else items.id = 'items';
        }

        const guia = document.createElement('div');
        guia.className = 'dv-order-guide';
        guia.innerHTML = `
            <a href="#dv-pedido-datos" class="is-active" data-dv-step="cliente"><b>1</b> Cliente y entrega</a>
            <a href="#dv-pedido-items" data-dv-step="items"><b>2</b> Ítems y precios</a>
            <span data-dv-step="revisar"><b>3</b> Revisar y guardar</span>
        `;
        form.insertAdjacentElement('beforebegin', guia);
    }

    function totalItem(item){
        const indice = indiceDe(item);
        if (!indice) return 0;

        const tipo = item.querySelector(`#tipo_item_${indice}`)?.value || '';
        const cantidad = Math.max(
            Number(item.querySelector(`#cantidad_${indice}`)?.value || 0),
            0
        );

        if (tipo === 'PRODUCTO'){
            const totalGuardado = Number(
                item.querySelector(`#precio_total_producto_${indice}`)?.value || 0
            );
            if (totalGuardado > 0) return totalGuardado;
            const unitario = Number(
                item.querySelector(`#precio_unitario_${indice}`)?.value || 0
            );
            return unitario * cantidad;
        }

        if (tipo === 'KIT'){
            const unitario = Number(
                item.querySelector(`#precio_unitario_kit_${indice}`)?.value || 0
            );
            return unitario * cantidad;
        }

        if (tipo === 'PERSONALIZADO'){
            return Number(
                item.querySelector(`#precio_total_personalizado_${indice}`)?.value || 0
            );
        }

        return 0;
    }

    function nombreCliente(){
        const select = document.querySelector('select[name="cliente"]');
        if (!select || !select.value) return '';
        if (select.value === 'NUEVO'){
            return String(
                document.querySelector('[name="nuevo_cliente_nombre"]')?.value || ''
            ).trim() || 'Nuevo cliente';
        }
        return String(
            select.options[select.selectedIndex]?.textContent || ''
        ).trim();
    }

    function actualizarResumenPedido(){
        const savebar = document.querySelector('.dv-order-savebar');
        if (!savebar) return;

        const items = Array.from(document.querySelectorAll('#items .item'));
        const total = items.reduce(function(acum,item){
            return acum + totalItem(item);
        }, 0);
        const cliente = nombreCliente();
        const titulo = savebar.querySelector('[data-dv-order-summary-title]');
        const detalle = savebar.querySelector('[data-dv-order-summary-detail]');
        const estado = savebar.querySelector('[data-dv-order-ready]');

        textoSiCambio(
            titulo,
            `${items.length} ${items.length === 1 ? 'ítem' : 'ítems'} · ${total > 0 ? '        asegurarEncabezadoItems();
        asegurarGuia();
        asegurarBarraGuardado();
        document.querySelectorAll('#items .item').forEach(function(item){
            prepararKit(item);
        });
        actualizarContador();
        actualizarNotaVolumen();
        actualizarResumenPedido();
    }

    function programar(){
        clearTimeout(timer);
        timer = setTimeout(prepararTodo, 40);
    }

    function iniciar(){
        prepararTodo();

        document.addEventListener('change', function(evento){
            actualizarResumenPedido();
            if (!evento.target?.closest?.('#items')) return;
            programar();
        });
        document.addEventListener('input', function(evento){
            actualizarResumenPedido();
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
            actualizarResumenPedido();
        }).observe(document.body, {
            childList:true,
            subtree:true,
            characterData:true
        });
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
 + moneda(total) : 'total pendiente'}`
        );

        const fecha = document.querySelector('[name="fecha_entrega"]')?.value || '';
        const partes = [];
        if (cliente) partes.push(cliente);
        if (fecha) partes.push('Entrega ' + fecha.split('-').reverse().join('/'));
        textoSiCambio(
            detalle,
            partes.length ? partes.join(' · ') : 'Completá cliente, ítems y precios.'
        );

        let estadoTexto = 'REVISAR';
        let listo = false;
        if (!cliente){
            estadoTexto = 'FALTA CLIENTE';
        } else if (!items.length){
            estadoTexto = 'AGREGÁ ÍTEMS';
        } else if (total <= 0){
            estadoTexto = 'REVISÁ PRECIOS';
        } else {
            estadoTexto = 'LISTO PARA GUARDAR';
            listo = true;
        }

        textoSiCambio(estado, estadoTexto);
        estado?.classList.toggle('ok', listo);

        document.querySelector('[data-dv-step="cliente"]')
            ?.classList.toggle('is-active', !cliente);
        document.querySelector('[data-dv-step="items"]')
            ?.classList.toggle('is-active', !!cliente && !listo);
        document.querySelector('[data-dv-step="revisar"]')
            ?.classList.toggle('is-active', listo);
    }

    function asegurarBarraGuardado(){
        if (document.querySelector('.dv-order-savebar')) return;

        const form = formularioPedido();
        if (!form) return;

        const submit = form.querySelector(
            'button[type="submit"].boton-guardar, button[type="submit"].guardar'
        );
        if (!submit) return;

        const barra = document.createElement('div');
        barra.className = 'dv-order-savebar';
        barra.innerHTML = `
            <div class="dv-order-summary-main">
                <div class="dv-order-summary-title" data-dv-order-summary-title>0 ítems · total pendiente</div>
                <div class="dv-order-summary-detail" data-dv-order-summary-detail>Completá cliente, ítems y precios.</div>
            </div>
            <div class="dv-order-ready" data-dv-order-ready>REVISAR</div>
            <div class="dv-order-save-action"></div>
        `;
        const contenedorAnterior = submit.parentElement;
        form.appendChild(barra);
        submit.classList.add('dv-order-save');
        barra.querySelector('.dv-order-save-action').appendChild(submit);

        if (
            contenedorAnterior
            && contenedorAnterior.classList?.contains('acciones')
        ){
            contenedorAnterior.remove();
        }

        actualizarResumenPedido();
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
