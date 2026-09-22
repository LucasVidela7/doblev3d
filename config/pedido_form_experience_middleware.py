"""Mejoras de experiencia compartidas para Nuevo/Editar Pedido.

Esta capa es deliberadamente visual: no modifica precios, payloads ni guardado.
Se ejecuta después de las capas históricas para sumar guía, resumen y una acción
de guardado consistente en desktop, tablet y mobile.
"""


PEDIDO_EXPERIENCE_STYLE = r"""
<style id="dv-pedido-experience-style">
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
.dv-order-data-card,
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
body.dv-pedido-form-page{
    padding-bottom:calc(180px + env(safe-area-inset-bottom))!important;
}
@media(max-width:760px){
    .dv-order-guide{gap:4px;padding:5px}
    .dv-order-guide a,
    .dv-order-guide span{
        min-height:42px;
        gap:6px;
        padding:6px;
        font-size:7px;
        justify-content:center;
    }
    .dv-order-guide b{width:22px;height:22px;font-size:8px}
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
    .dv-order-summary-detail{max-width:170px}
    .dv-order-savebar .dv-order-save{min-width:125px!important}
}
</style>
"""


PEDIDO_EXPERIENCE_SCRIPT = r"""
<script id="dv-pedido-experience-script">
(function(){
    function money(value){
        return new Intl.NumberFormat('es-AR', {
            minimumFractionDigits:0,
            maximumFractionDigits:2
        }).format(Number(value || 0));
    }

    function setText(element, value){
        if (element && element.textContent !== value){
            element.textContent = value;
        }
    }

    function orderForm(){
        return document.querySelector('form[method="post"]');
    }

    function itemIndex(item){
        var input = item.querySelector('input[name="item_indice"]');
        return input ? String(input.value || '') : '';
    }

    function ensureItemsHeading(){
        var items = document.getElementById('items');
        if (!items) return;

        var heading = document.querySelector('.dv-items-heading');
        if (heading){
            heading.id = 'dv-pedido-items';
            return;
        }

        heading = document.createElement('div');
        heading.className = 'dv-items-heading';
        heading.id = 'dv-pedido-items';
        heading.innerHTML =
            '<div><div class="dv-items-heading-main">Ítems del pedido</div>' +
            '<div class="dv-items-heading-help">Elegí tipo, cantidad y precio. Podés combinar productos, kits y personalizados.</div></div>' +
            '<div class="dv-items-count">0 ITEMS</div>';
        items.insertAdjacentElement('beforebegin', heading);
    }

    function ensureGuide(){
        if (document.querySelector('.dv-order-guide')) return;
        var form = orderForm();
        if (!form) return;

        var firstCard = null;
        Array.from(form.children).some(function(element){
            var valid = element.classList && (
                element.classList.contains('tarjeta') ||
                (
                    element.classList.contains('card') &&
                    element.classList.contains('grid')
                )
            );
            if (valid) firstCard = element;
            return valid;
        });

        if (firstCard){
            firstCard.id = firstCard.id || 'dv-pedido-datos';
            firstCard.classList.add('dv-order-data-card');
        }

        ensureItemsHeading();

        var guide = document.createElement('div');
        guide.className = 'dv-order-guide';
        guide.innerHTML =
            '<a href="#dv-pedido-datos" class="is-active" data-dv-step="cliente"><b>1</b> Cliente y entrega</a>' +
            '<a href="#dv-pedido-items" data-dv-step="items"><b>2</b> Ítems y precios</a>' +
            '<span data-dv-step="revisar"><b>3</b> Revisar y guardar</span>';
        form.insertAdjacentElement('beforebegin', guide);
    }

    function itemTotal(item){
        var index = itemIndex(item);
        if (!index) return 0;

        var type = item.querySelector('#tipo_item_' + index);
        type = type ? type.value : '';
        var qtyInput = item.querySelector('#cantidad_' + index);
        var qty = Math.max(Number(qtyInput ? qtyInput.value : 0), 0);

        if (type === 'PRODUCTO'){
            var hidden = item.querySelector('#precio_total_producto_' + index);
            var saved = Number(hidden ? hidden.value : 0);
            if (saved > 0) return saved;
            var unitInput = item.querySelector('#precio_unitario_' + index);
            return Number(unitInput ? unitInput.value : 0) * qty;
        }

        if (type === 'KIT'){
            var kitPrice = item.querySelector('#precio_unitario_kit_' + index);
            return Number(kitPrice ? kitPrice.value : 0) * qty;
        }

        if (type === 'PERSONALIZADO'){
            var customTotal = item.querySelector(
                '#precio_total_personalizado_' + index
            );
            return Number(customTotal ? customTotal.value : 0);
        }

        return 0;
    }

    function clientName(){
        var select = document.querySelector('select[name="cliente"]');
        if (!select || !select.value) return '';

        if (select.value === 'NUEVO'){
            var input = document.querySelector(
                '[name="nuevo_cliente_nombre"]'
            );
            return String(input ? input.value : '').trim() || 'Nuevo cliente';
        }

        var option = select.options[select.selectedIndex];
        return String(option ? option.textContent : '').trim();
    }

    function updateSummary(){
        var bar = document.querySelector('.dv-order-savebar');
        if (!bar) return;

        var items = Array.from(document.querySelectorAll('#items .item'));
        var total = items.reduce(function(sum, item){
            return sum + itemTotal(item);
        }, 0);

        var client = clientName();
        var title = bar.querySelector('[data-dv-order-summary-title]');
        var detail = bar.querySelector('[data-dv-order-summary-detail]');
        var state = bar.querySelector('[data-dv-order-ready]');

        var titleText =
            String(items.length) + ' ' +
            (items.length === 1 ? 'ítem' : 'ítems') +
            ' · ' +
            (total > 0 ? '$' + money(total) : 'total pendiente');
        setText(title, titleText);

        var dateInput = document.querySelector('[name="fecha_entrega"]');
        var dateValue = dateInput ? dateInput.value : '';
        var parts = [];
        if (client) parts.push(client);
        if (dateValue){
            parts.push(
                'Entrega ' + dateValue.split('-').reverse().join('/')
            );
        }
        setText(
            detail,
            parts.length
                ? parts.join(' · ')
                : 'Completá cliente, ítems y precios.'
        );

        var stateText = 'REVISAR';
        var ready = false;
        if (!client){
            stateText = 'FALTA CLIENTE';
        } else if (!items.length){
            stateText = 'AGREGÁ ÍTEMS';
        } else if (total <= 0){
            stateText = 'REVISÁ PRECIOS';
        } else {
            stateText = 'LISTO PARA GUARDAR';
            ready = true;
        }

        setText(state, stateText);
        if (state) state.classList.toggle('ok', ready);

        var stepClient = document.querySelector('[data-dv-step="cliente"]');
        var stepItems = document.querySelector('[data-dv-step="items"]');
        var stepReview = document.querySelector('[data-dv-step="revisar"]');
        if (stepClient) stepClient.classList.toggle('is-active', !client);
        if (stepItems) stepItems.classList.toggle(
            'is-active',
            Boolean(client) && !ready
        );
        if (stepReview) stepReview.classList.toggle('is-active', ready);
    }

    function ensureSavebar(){
        if (document.querySelector('.dv-order-savebar')) return;

        var form = orderForm();
        if (!form) return;

        var submit = form.querySelector(
            'button[type="submit"].boton-guardar, ' +
            'button[type="submit"].guardar'
        );
        if (!submit) return;

        var oldContainer = submit.parentElement;
        var bar = document.createElement('div');
        bar.className = 'dv-order-savebar';
        bar.innerHTML =
            '<div class="dv-order-summary-main">' +
            '<div class="dv-order-summary-title" data-dv-order-summary-title>0 ítems · total pendiente</div>' +
            '<div class="dv-order-summary-detail" data-dv-order-summary-detail>Completá cliente, ítems y precios.</div>' +
            '</div>' +
            '<div class="dv-order-ready" data-dv-order-ready>REVISAR</div>' +
            '<div class="dv-order-save-action"></div>';

        form.appendChild(bar);
        submit.classList.add('dv-order-save');
        bar.querySelector('.dv-order-save-action').appendChild(submit);

        if (
            oldContainer &&
            oldContainer.classList &&
            oldContainer.classList.contains('acciones')
        ){
            oldContainer.remove();
        }

        updateSummary();
    }

    function refresh(){
        document.body.classList.add('dv-pedido-form-page');
        ensureItemsHeading();
        ensureGuide();
        ensureSavebar();
        updateSummary();
    }

    function start(){
        refresh();

        document.addEventListener('input', function(){
            updateSummary();
        });
        document.addEventListener('change', function(){
            updateSummary();
        });

        var items = document.getElementById('items');
        if (items){
            new MutationObserver(function(){
                window.setTimeout(refresh, 40);
            }).observe(items, {
                childList:true,
                subtree:true,
                characterData:true
            });
        }

        new MutationObserver(function(){
            updateSummary();
        }).observe(document.body, {
            childList:true,
            subtree:true,
            characterData:true
        });

        window.setTimeout(refresh, 120);
        window.setTimeout(refresh, 500);
    }

    if (document.readyState === 'loading'){
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();
</script>
"""


class PedidoFormExperienceMiddleware:
    """Inyecta la guía y el resumen visual en Nuevo/Editar Pedido."""

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
        if view_name not in {
            "pedidos:nuevo",
            "pedidos:editar",
            "pedidos:presupuesto_editar",
        }:
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if (
            "dv-pedido-experience-style" not in html
            and "</head>" in html
        ):
            html = html.replace(
                "</head>",
                PEDIDO_EXPERIENCE_STYLE + "\n</head>",
                1,
            )

        if (
            "dv-pedido-experience-script" not in html
            and "</body>" in html
        ):
            html = html.replace(
                "</body>",
                PEDIDO_EXPERIENCE_SCRIPT + "\n</body>",
                1,
            )

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
