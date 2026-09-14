NAV_STYLE = r"""
<style id="dv-nav-actions-style">
.dv-nav-action{
    min-height:50px!important;
    height:auto!important;
    padding:0 18px!important;
    border-radius:14px!important;
    font-family:Arial,sans-serif!important;
    font-size:11px!important;
    font-weight:900!important;
    line-height:1!important;
    display:inline-flex!important;
    align-items:center!important;
    justify-content:center!important;
    text-decoration:none!important;
    cursor:pointer!important;
    box-sizing:border-box!important;
    white-space:nowrap!important;
    transition:background .15s ease,border-color .15s ease,color .15s ease!important;
}
.dv-nav-back{
    border:1px solid #e5e7eb!important;
    background:#fff!important;
    color:#24272b!important;
    box-shadow:none!important;
}
.dv-nav-home{
    border:1px solid #24272b!important;
    background:#24272b!important;
    color:#fff!important;
    box-shadow:none!important;
}
@media(hover:hover){
    .dv-nav-back:hover{background:#f0f1f3!important}
    .dv-nav-home:hover{background:#16191d!important;border-color:#16191d!important}
}
@media(max-width:720px){
    .dv-nav-action{min-height:50px!important}
}
</style>
"""

NAV_SCRIPT = r"""
<script id="dv-nav-actions-script">
(function(){
    function normalizar(texto){
        return (texto || '').replace(/\s+/g, ' ').trim().toUpperCase();
    }

    function aplicar(){
        document.querySelectorAll('a, button').forEach(function(el){
            var texto = normalizar(el.textContent);

            if (texto === '← VOLVER' || texto === 'VOLVER') {
                el.classList.add('dv-nav-action', 'dv-nav-back');
            }

            if (texto === 'INICIO') {
                el.classList.add('dv-nav-action', 'dv-nav-home');
            }
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', aplicar);
    } else {
        aplicar();
    }
})();
</script>
"""


class NormalizarNavegacionMiddleware:
    """Normaliza visualmente VOLVER e INICIO en todas las pantallas HTML.

    Se hace en un único punto para evitar que cada template termine con
    tamaños, bordes o colores distintos. No toca la navbar inferior porque
    sus enlaces contienen también el icono y no coinciden con el texto exacto.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if getattr(response, "streaming", False):
            return response

        content_type = response.get("Content-Type", "")
        if "text/html" not in content_type:
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        if "</head>" in html and "dv-nav-actions-style" not in html:
            html = html.replace(
                "</head>",
                NAV_STYLE + "\n</head>",
                1,
            )

        if "</body>" in html and "dv-nav-actions-script" not in html:
            html = html.replace(
                "</body>",
                NAV_SCRIPT + "\n</body>",
                1,
            )

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
