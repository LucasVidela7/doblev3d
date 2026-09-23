import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import EventoCatalogo, MetricasConfiguracion
from .services import invalidar_configuracion_metricas


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CATALOGO_MANTENIMIENTO=False,
)
class MetricasCatalogoTests(TestCase):
    def setUp(self):
        self.config, _ = MetricasConfiguracion.objects.get_or_create(pk=1)
        self.config.activas = True
        self.config.retencion_dias = 180
        self.config.save()
        invalidar_configuracion_metricas()

        self.client.cookies["dv_visitor_id"] = "visitor-prueba-123"
        self.client.cookies["dv_session_id"] = "session-prueba-123"
        self.client.cookies["dv_metric_source"] = "instagram.com"

    def _evento(self, **extra):
        payload = {
            "evento": "PAGE_VIEW",
            "pagina": "inicio",
            "ruta": "/",
            "origen": "instagram.com",
        }
        payload.update(extra)
        return self.client.post(
            reverse("metricas:evento"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_USER_AGENT=(
                "Mozilla/5.0 (Linux; Android 16; Mobile) "
                "AppleWebKit/537.36"
            ),
        )

    def test_endpoint_registra_evento_anonimo_sin_guardar_id_crudo(self):
        response = self._evento()

        self.assertEqual(response.status_code, 204)
        evento = EventoCatalogo.objects.get()
        self.assertEqual(evento.evento, "PAGE_VIEW")
        self.assertEqual(evento.dispositivo, "MOBILE")
        self.assertEqual(evento.origen, "instagram.com")
        self.assertNotEqual(
            evento.visitor_hash,
            "visitor-prueba-123",
        )
        self.assertEqual(len(evento.visitor_hash), 64)
        self.assertEqual(len(evento.session_hash), 64)

    def test_metricas_se_pueden_apagar_desde_configuracion(self):
        self.config.activas = False
        self.config.save(update_fields=["activas"])
        invalidar_configuracion_metricas()

        response = self._evento()

        self.assertEqual(response.status_code, 204)
        self.assertFalse(EventoCatalogo.objects.exists())

    def test_usuario_gestion_logueado_no_registra_eventos(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="operador_metricas",
            password="clave-segura",
        )
        self.client.force_login(user)

        response = self._evento()

        self.assertEqual(response.status_code, 204)
        self.assertFalse(EventoCatalogo.objects.exists())

    def test_tracker_no_se_inyecta_para_usuario_logueado(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="operador_catalogo",
            password="clave-segura",
        )
        self.client.force_login(user)

        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "data-dv-metrics-script")

    def test_tracker_se_inyecta_en_catalogo_publico(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-dv-metrics-script")
        self.assertContains(
            response,
            "metricas/catalog_metrics.js",
        )
        self.assertContains(
            response,
            'data-page-kind="inicio"',
        )

    def test_detalle_informa_tipo_e_id_al_tracker(self):
        from productos.models import Producto, TipoProducto

        tipo = TipoProducto.objects.create(
            nombre="Sensorial",
            activo=True,
        )
        producto = Producto.objects.create(
            nombre="Producto métrica",
            categoria="PRODUCTO",
            tipo=tipo,
            horas=1,
            peso_gramos=10,
            margen_ganancia=30,
            activo=True,
        )

        response = self.client.get(
            reverse(
                "catalogo_producto_detalle",
                args=[producto.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'data-content-kind="PRODUCTO"',
        )
        self.assertContains(
            response,
            f'data-content-id="{producto.id}"',
        )

    def test_configuracion_muestra_tablero_y_guarda_retencion(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="admin_metricas",
            password="clave-segura",
        )
        self.client.force_login(user)

        EventoCatalogo.objects.create(
            evento="PAGE_VIEW",
            visitor_hash="v1",
            session_hash="s1",
            pagina="inicio",
            dispositivo="DESKTOP",
            origen="Directo",
            ruta="/",
        )
        EventoCatalogo.objects.create(
            evento="SOLICITUD",
            visitor_hash="v1",
            session_hash="s1",
            pagina="checkout",
            dispositivo="DESKTOP",
            origen="Directo",
            ruta="/carrito/",
        )

        response = self.client.get(
            reverse("dashboard:configuracion"),
            {"periodo": "30"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Métricas del catálogo")
        self.assertContains(response, "Embudo de compra")
        self.assertContains(response, "CONVERSIÓN")
        self.assertContains(response, "100.0%")

        post = self.client.post(
            reverse("dashboard:configuracion"),
            {
                "metricas_activas": "on",
                "metricas_retencion_dias": "90",
            },
        )
        self.assertEqual(post.status_code, 302)
        self.config.refresh_from_db()
        self.assertEqual(self.config.retencion_dias, 90)
