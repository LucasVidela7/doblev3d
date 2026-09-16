from types import SimpleNamespace

from django.contrib.messages.storage.fallback import FallbackStorage
from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from productos.models import Producto, TipoProducto

from config.production_experience_middleware import (
    PLANIFICACION_SCRIPT,
    ProductionExperienceMiddleware,
    _impresoras_ocupadas,
)
from produccion.models import Impresora, Produccion
from produccion.views import iniciar_produccion


class ExperienciaProduccionTests(TestCase):
    def setUp(self):
        tipo = TipoProducto.objects.create(nombre="Tipo producción UI")
        self.producto = Producto.objects.create(
            nombre="Producto UI",
            categoria="PRODUCTO",
            tipo=tipo,
            horas=1,
            minutos=15,
            requiere_impresion=True,
            activo=True,
        )
        self.ocupada = Impresora.objects.create(nombre="Bambu ocupada")
        self.libre = Impresora.objects.create(nombre="Bambu libre")
        self.trabajo_ocupado = Produccion.objects.create(
            producto=self.producto,
            cantidad=2,
            impresora=self.ocupada,
            destino="STOCK",
            estado="IMPRIMIENDO",
            tiempo_impresion_minutos=75,
        )
        self.factory = RequestFactory()

    def _request(self, view_name, path="/"):
        request = self.factory.get(path)
        request.resolver_match = SimpleNamespace(view_name=view_name)
        return request

    def test_detecta_impresora_ocupada_para_el_selector(self):
        ocupadas = _impresoras_ocupadas()

        self.assertIn(str(self.ocupada.id), ocupadas)
        self.assertNotIn(str(self.libre.id), ocupadas)
        self.assertEqual(
            ocupadas[str(self.ocupada.id)]["codigo"],
            self.trabajo_ocupado.codigo,
        )

    def test_backend_impide_iniciar_en_impresora_ocupada(self):
        pendiente = Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            destino="STOCK",
            estado="PENDIENTE",
            tiempo_impresion_minutos=75,
        )
        request = self.factory.post(
            "/produccion/iniciar/",
            {"impresora": str(self.ocupada.id)},
        )
        request.session = {}
        request._messages = FallbackStorage(request)

        response = iniciar_produccion(request, pendiente.id)

        self.assertEqual(response.status_code, 302)
        pendiente.refresh_from_db()
        self.assertEqual(pendiente.estado, "PENDIENTE")
        self.assertIsNone(pendiente.impresora_id)

    def test_middleware_inyecta_bloqueo_y_separacion_de_finalizadas(self):
        html = """
        <html><head></head><body>
            <div class="tabla-contenedor"><table>
                <thead><tr><th>TRABAJO</th></tr></thead>
                <tbody>
                    <tr><td><span class="estado-IMPRIMIENDO">IMPRIMIENDO</span></td></tr>
                    <tr><td><span class="estado-LISTO">LISTO</span></td></tr>
                </tbody>
            </table></div>
            <form class="inicio-produccion-form">
                <select class="selector-impresora-inicio">
                    <option value="">Elegir</option>
                    <option value="%s">Ocupada</option>
                    <option value="%s">Libre</option>
                </select>
                <button class="btn-iniciar">INICIAR</button>
            </form>
        </body></html>
        """ % (self.ocupada.id, self.libre.id)

        middleware = ProductionExperienceMiddleware(
            lambda request: HttpResponse(html)
        )
        response = middleware(self._request("produccion:lista"))
        contenido = response.content.decode()

        self.assertIn("dv-produccion-experiencia-style", contenido)
        self.assertIn("dv-produccion-experiencia-script", contenido)
        self.assertIn(self.trabajo_ocupado.codigo, contenido)
        self.assertIn("opcion.disabled = true", contenido)
        self.assertIn("FINALIZADAS", contenido)
        self.assertIn("detalles.open = true", contenido)
        self.assertIn("EN CURSO", contenido)

    def test_planificacion_estandar_quita_maximo_pero_personalizado_no(self):
        self.assertIn("cantidad.removeAttribute('max')", PLANIFICACION_SCRIPT)
        self.assertIn(
            "!form.querySelector('input[name=\"personalizado_id\"]')",
            PLANIFICACION_SCRIPT,
        )

    def test_middleware_compacta_planificador_por_producto(self):
        html = "<html><head></head><body><div class='tabla-contenedor'></div></body></html>"
        middleware = ProductionExperienceMiddleware(
            lambda request: HttpResponse(html)
        )
        response = middleware(
            self._request("pedidos:impresiones_productos")
        )
        contenido = response.content.decode()

        self.assertIn("dv-planificacion-experiencia-style", contenido)
        self.assertIn("dv-planificacion-experiencia-script", contenido)
        self.assertIn(".dv-personalizados", contenido)
        self.assertIn("grid-template-columns:110px", contenido)
