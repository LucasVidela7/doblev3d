class PlanificadorLibreUIMiddleware:
    """
    El planificador de Impresiones por producto usa cantidad libre para placas
    estándar. Los personalizados conservan su máximo porque están vinculados a
    una cantidad exacta del pedido.
    """

    SCRIPT = r"""
<script id="dv-planificador-libre-script">
(function(){
    function ajustar(raiz){
        const scope = raiz && raiz.querySelectorAll ? raiz : document;
        scope.querySelectorAll('.dv-plan-form').forEach(function(form){
            const personalizado = form.querySelector('input[name="personalizado_id"]');
            const cantidad = form.querySelector('input[name="cantidad"]');
            if (!cantidad) return;

            if (!personalizado){
                cantidad.removeAttribute('max');
                cantidad.dataset.dvCantidadLibre = '1';

                const estado = form.querySelector('.dv-plan-tiempo');
                if (estado && !form.querySelector('.dv-stock-extra-aviso')){
                    const aviso = document.createElement('div');
                    aviso.className = 'dv-stock-extra-aviso';
                    aviso.textContent = 'Cantidad libre: podés superar A imprimir; el excedente quedará como stock al finalizar.';
                    estado.parentNode.insertBefore(aviso, estado);
                }
            }
        });

        document.querySelectorAll('.dv-plan-details > summary').forEach(function(summary){
            if (
                summary.textContent.indexOf('PLANIFICAR ESTÁNDAR') !== -1
                && summary.dataset.dvCantidadLibre !== '1'
            ){
                summary.dataset.dvCantidadLibre = '1';
                summary.textContent = summary.textContent.replace(
                    'PLANIFICAR ESTÁNDAR',
                    'PLANIFICAR ESTÁNDAR · CANTIDAD LIBRE'
                );
            }
        });
    }

    function iniciar(){
        ajustar(document);
        const observer = new MutationObserver(function(cambios){
            cambios.forEach(function(cambio){
                cambio.addedNodes.forEach(function(nodo){
                    if (nodo.nodeType === 1) ajustar(nodo);
                });
            });
            ajustar(document);
        });
        observer.observe(document.body, {childList:true, subtree:true});
        setTimeout(function(){ajustar(document);}, 0);
        setTimeout(function(){ajustar(document);}, 250);
    }

    if (document.readyState === 'loading'){
        document.addEventListener('DOMContentLoaded', iniciar);
    } else {
        iniciar();
    }
})();
</script>
<style id="dv-planificador-libre-style">
.dv-stock-extra-aviso{
    grid-column:1/-1;
    padding:7px 8px;
    border-radius:8px;
    background:#eef7ef;
    color:#35613c;
    font-size:7px;
    font-weight:800;
    line-height:1.4;
}
</style>
"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        resolver_match = getattr(request, "resolver_match", None)
        if not resolver_match or resolver_match.view_name != "pedidos:impresiones_productos":
            return response

        content_type = response.get("Content-Type", "")
        if "text/html" not in content_type or getattr(response, "streaming", False):
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if "dv-planificador-libre-script" in html:
            return response

        if "</body>" in html:
            html = html.replace("</body>", self.SCRIPT + "\n</body>", 1)
        else:
            html += self.SCRIPT

        response.content = html.encode(response.charset or "utf-8")
        if response.has_header("Content-Length"):
            response["Content-Length"] = str(len(response.content))

        return response
