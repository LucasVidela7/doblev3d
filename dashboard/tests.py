from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from pedidos.models import (
    DetallePresupuesto,
    Presupuesto,
    SolicitudWeb,
    SolicitudWebItem,
)
from produccion.models import Impresora, Produccion
from productos.models import Producto, TipoProducto
from productos.image_models import ProductoImagen


class DashboardProduccionTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="dashboard-test",
            password="test-pass-123",
        )
        self.client.force_login(usuario)

        tipo = TipoProducto.objects.create(
            nombre="Dashboard producción",
            activo=True,
        )

        self.producto = Producto.objects.create(
            nombre="Pieza dashboard",
            categoria="PRODUCTO",
            tipo=tipo,
            horas=1,
            minutos=30,
            peso_gramos=Decimal("125.50"),
            requiere_impresion=True,
            activo=True,
        )

        self.impresora_a = Impresora.objects.create(
            nombre="A1 dashboard",
            activa=True,
        )
        self.impresora_b = Impresora.objects.create(
            nombre="P1S dashboard",
            activa=True,
        )

    def test_dashboard_carga_tema_global_y_selector_en_configuracion(self):
        respuesta = self.client.get(
            reverse("dashboard:inicio")
        )

        self.assertEqual(respuesta.status_code, 200)
        contenido = respuesta.content.decode()
        self.assertRegex(
            contenido,
            r"/static/shared/theme(?:\.[0-9a-f]+)?\.css",
        )
        self.assertRegex(
            contenido,
            r"/static/shared/theme(?:\.[0-9a-f]+)?\.js",
        )
        self.assertNotContains(
            respuesta,
            'id="dvThemeToggle"',
        )

        configuracion = self.client.get(
            reverse("dashboard:configuracion")
        )
        self.assertEqual(configuracion.status_code, 200)
        self.assertContains(
            configuracion,
            'id="dvThemeToggle"',
        )
        self.assertContains(
            configuracion,
            "Apariencia",
        )

        self.assertContains(
            respuesta,
            'id="dvManagementMenu"',
        )
        self.assertContains(
            respuesta,
            'id="dvManagementMenuToggle"',
        )
        self.assertRegex(
            contenido,
            r"/static/shared/management_menu(?:\.[0-9a-f]+)?\.css",
        )
        self.assertRegex(
            contenido,
            r"/static/shared/management_menu(?:\.[0-9a-f]+)?\.js",
        )
        self.assertNotContains(
            respuesta,
            'id="dv-dashboard-menu-script"',
        )
        self.assertContains(
            respuesta,
            "dashboard-test",
        )
        self.assertContains(
            respuesta,
            "CERRAR SESIÓN",
        )
        self.assertContains(
            respuesta,
            'class="dv-management-menu__account"',
        )
        self.assertNotContains(
            respuesta,
            'id="dv-dashboard-session"',
        )

    def test_dashboard_muestra_impresoras_y_planificaciones(self):
        ahora = timezone.now()

        Produccion.objects.create(
            producto=self.producto,
            cantidad=2,
            impresora=self.impresora_a,
            estado="IMPRIMIENDO",
            inicio_impresion=ahora,
            tiempo_impresion_minutos=90,
        )

        Produccion.objects.create(
            producto=self.producto,
            cantidad=3,
            estado="PENDIENTE",
            inicio_impresion=ahora + timedelta(hours=2),
            tiempo_impresion_minutos=120,
        )

        respuesta = self.client.get(
            reverse("dashboard:inicio")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "Impresoras y próximos trabajos",
        )
        self.assertContains(
            respuesta,
            "A1 dashboard",
        )
        self.assertContains(
            respuesta,
            "P1S dashboard",
        )
        self.assertContains(
            respuesta,
            "251 g",
        )
        self.assertContains(
            respuesta,
            "376.5 g",
        )

    def test_barra_resume_presupuestos_y_operacion(self):
        cliente = Cliente.objects.create(
            nombre="Cliente dashboard presupuesto",
            activo=True,
        )
        presupuesto = Presupuesto.objects.create(
            cliente=cliente,
            estado="PENDIENTE",
        )
        DetallePresupuesto.objects.create(
            presupuesto=presupuesto,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=2,
            precio_lista_unitario=Decimal("5000"),
            precio_unitario=Decimal("4500"),
        )

        respuesta = self.client.get(
            reverse("dashboard:inicio")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.context["presupuestos_pendientes"],
            1,
        )
        self.assertEqual(
            respuesta.context["monto_presupuestado_pendiente"],
            Decimal("9000"),
        )
        self.assertContains(
            respuesta,
            "PRESUPUESTOS PENDIENTES",
        )
        self.assertContains(
            respuesta,
            "PRODUCCIÓN",
        )
        self.assertContains(
            respuesta,
            "LISTOS / ENTREGAS",
        )
        self.assertNotContains(
            respuesta,
            ">ATRASADOS<",
        )

    def test_dashboard_muestra_solicitudes_web_pendientes(self):
        solicitud = SolicitudWeb.objects.create(
            nombre="Cliente catálogo",
            telefono="11 4444-5555",
            telefono_normalizado="1144445555",
            email="cliente@example.com",
            estado="NUEVA",
        )
        SolicitudWebItem.objects.create(
            solicitud=solicitud,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=3,
            nombre_snapshot=self.producto.nombre,
            precio_base_unitario=Decimal("5000"),
            adicional_unitario=Decimal("0"),
            precio_unitario=Decimal("4500"),
        )

        respuesta = self.client.get(
            reverse("dashboard:inicio")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.context["solicitudes_web_pendientes"],
            1,
        )
        self.assertEqual(
            respuesta.context["solicitudes_web_nuevas"],
            1,
        )
        self.assertContains(
            respuesta,
            "SOLICITUDES WEB",
        )
        self.assertContains(
            respuesta,
            "Cliente catálogo",
        )
        self.assertContains(
            respuesta,
            "3 unidades",
        )
        self.assertContains(
            respuesta,
            "13.500",
        )
        self.assertContains(
            respuesta,
            "REVISAR SOLICITUD",
        )

    def test_dashboard_puede_iniciar_planificacion(self):
        produccion = Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            estado="PENDIENTE",
            inicio_impresion=timezone.now(),
            tiempo_impresion_minutos=90,
        )

        respuesta = self.client.post(
            reverse(
                "dashboard:produccion_iniciar",
                args=[produccion.id],
            ),
            {
                "impresora": self.impresora_b.id,
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("dashboard:inicio"),
        )

        produccion.refresh_from_db()
        self.assertEqual(
            produccion.estado,
            "IMPRIMIENDO",
        )
        self.assertEqual(
            produccion.impresora_id,
            self.impresora_b.id,
        )

    def test_dashboard_puede_marcar_impresion_lista(self):
        produccion = Produccion.objects.create(
            producto=self.producto,
            cantidad=2,
            impresora=self.impresora_a,
            destino="STOCK",
            estado="IMPRIMIENDO",
            inicio_impresion=timezone.now(),
            tiempo_impresion_minutos=90,
        )

        respuesta = self.client.post(
            reverse(
                "dashboard:produccion_estado",
                args=[produccion.id],
            ),
            {
                "estado": "LISTO",
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("dashboard:inicio"),
        )

        produccion.refresh_from_db()
        self.producto.refresh_from_db()

        self.assertEqual(
            produccion.estado,
            "LISTO",
        )
        self.assertTrue(
            produccion.ingresado_stock,
        )
        self.assertEqual(
            self.producto.stock,
            2,
        )

    def test_dashboard_muestra_miniatura_en_produccion(self):
        ProductoImagen.objects.create(
            producto=self.producto,
            file_id="prod-thumb-dashboard",
            url="https://example.com/dashboard.jpg",
            thumbnail_url="https://example.com/dashboard-thumb.jpg",
            orden=1,
        )
        Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            impresora=self.impresora_a,
            estado="IMPRIMIENDO",
            inicio_impresion=timezone.now(),
            tiempo_impresion_minutos=90,
        )

        respuesta = self.client.get(
            reverse("dashboard:inicio")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "https://example.com/dashboard-thumb.jpg",
        )
        self.assertContains(
            respuesta,
            'class="dv-producto-thumb"',
        )

