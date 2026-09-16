from django.http import HttpResponse
from django.test import SimpleTestCase, override_settings

from config.environment_ui_middleware import EnvironmentVisualMiddleware


HTML_BASE = """<!doctype html>
<html lang=\"es\">
<head>
    <title>Doble V 3D</title>
</head>
<body>
    <main>Contenido</main>
</body>
</html>
"""


class EnvironmentVisualMiddlewareTests(SimpleTestCase):
    def _response(self, content=HTML_BASE, content_type="text/html; charset=utf-8"):
        middleware = EnvironmentVisualMiddleware(
            lambda request: HttpResponse(content, content_type=content_type)
        )
        return middleware(object())

    @override_settings(IS_QA=True)
    def test_qa_marca_toda_respuesta_html(self):
        response = self._response()
        html = response.content.decode("utf-8")

        self.assertIn('data-dv-env="qa"', html)
        self.assertIn('id="dv-qa-banner"', html)
        self.assertIn("ENTORNO DE PRUEBAS", html)
        self.assertIn("[QA] Doble V 3D", html)
        self.assertIn('id="dv-qa-favicon"', html)
        self.assertIn('id="dv-qa-environment-style"', html)

    @override_settings(IS_QA=False)
    def test_produccion_no_se_modifica(self):
        response = self._response()
        html = response.content.decode("utf-8")

        self.assertNotIn('data-dv-env="qa"', html)
        self.assertNotIn('id="dv-qa-banner"', html)
        self.assertNotIn("[QA]", html)
        self.assertNotIn('id="dv-qa-favicon"', html)

    @override_settings(IS_QA=True)
    def test_respuestas_no_html_no_se_modifican(self):
        response = self._response(
            content='{"ok":true}',
            content_type="application/json",
        )

        self.assertEqual(response.content, b'{"ok":true}')

    @override_settings(IS_QA=True)
    def test_no_duplica_marca_si_se_procesa_dos_veces(self):
        primera = self._response()
        html_primera = primera.content.decode("utf-8")

        middleware = EnvironmentVisualMiddleware(
            lambda request: HttpResponse(
                html_primera,
                content_type="text/html; charset=utf-8",
            )
        )
        segunda = middleware(object())
        html_segunda = segunda.content.decode("utf-8")

        self.assertEqual(html_segunda.count('id="dv-qa-banner"'), 1)
        self.assertEqual(html_segunda.count('id="dv-qa-environment-style"'), 1)
        self.assertEqual(html_segunda.count("[QA] Doble V 3D"), 1)
