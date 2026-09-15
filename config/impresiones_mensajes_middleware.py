from html import escape

from django.contrib.messages import get_messages


STYLE = r"""
<style id="dv-impresiones-mensajes-style">
.dv-impresiones-mensajes{display:grid;gap:7px;margin:0 0 14px}
.dv-impresiones-mensaje{padding:11px 13px;border:1px solid #d9dde2;border-radius:11px;background:#fff;color:#444;font-size:10px;font-weight:800;line-height:1.4}
.dv-impresiones-mensaje.success{border-color:#c9e4d1;background:#f0f9f3;color:#24633a}
.dv-impresiones-mensaje.error{border-color:#eccaca;background:#fff1f1;color:#923434}
.dv-impresiones-mensaje.warning{border-color:#ead89d;background:#fffaf0;color:#765b00}
</style>
"""


class MensajesImpresionesMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        resolver_match = getattr(request, "resolver_match", None)
        view_name = resolver_match.view_name if resolver_match else ""

        if (
            view_name != "pedidos:impresiones_productos"
            or getattr(response, "streaming", False)
            or "text/html" not in response.get("Content-Type", "")
        ):
            return response

        mensajes = list(get_messages(request))
        if not mensajes:
            return response

        try:
            html = response.content.decode(response.charset or "utf-8")
        except (AttributeError, UnicodeDecodeError):
            return response

        bloques = []
        for mensaje in mensajes:
            tags = (mensaje.tags or "").split()
            clase = (
                "success"
                if "success" in tags
                else "error"
                if "error" in tags
                else "warning"
                if "warning" in tags
                else ""
            )
            bloques.append(
                '<div class="dv-impresiones-mensaje {}">{}</div>'.format(
                    clase,
                    escape(str(mensaje)),
                )
            )

        bloque = (
            '<div class="dv-impresiones-mensajes" id="dv-impresiones-mensajes">'
            + "".join(bloques)
            + "</div>"
        )

        if "</head>" in html and "dv-impresiones-mensajes-style" not in html:
            html = html.replace("</head>", STYLE + "\n</head>", 1)

        ancla = '<div class="tabla-contenedor">'
        if ancla in html:
            html = html.replace(ancla, bloque + "\n" + ancla, 1)
        elif "<body>" in html:
            html = html.replace("<body>", "<body>\n" + bloque, 1)

        encoded = html.encode(response.charset or "utf-8")
        response.content = encoded
        response["Content-Length"] = str(len(encoded))
        return response
