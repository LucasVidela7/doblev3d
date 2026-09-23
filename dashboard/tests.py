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
from productos.models import (
    ConfiguracionCatalogo,
    Producto,
    SolicitudArrepentimiento,
    TipoProducto,
)
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

    def test_barra_superior_mantiene_siete_metricas_y_unifica_ingresos(self):
        SolicitudArrepentimiento.objects.create(
            nombre="Cliente arrepentimiento",
            contacto="1144440000",
            estado="NUEVA",
        )

        respuesta = self.client.get(
            reverse("dashboard:inicio")
        )

        self.assertEqual(respuesta.status_code, 200)
        contenido = respuesta.content.decode()
        self.assertEqual(
            contenido.count('class="metrica '),
            7,
        )
        self.assertLess(
            contenido.index("SOLICITUDES WEB"),
            contenido.index("PRESUPUESTOS PENDIENTES"),
        )
        self.assertContains(respuesta, "INGRESOS")
        self.assertContains(respuesta, "Cobrado este mes")
        self.assertContains(respuesta, "saldo a cobrar")
        self.assertContains(respuesta, "ARREPENTIMIENTOS")
        self.assertEqual(
            respuesta.context["arrepentimientos_pendientes"],
            1,
        )
        self.assertContains(
            respuesta,
            reverse("dashboard:configuracion") + "#legal",
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

    def test_dashboard_repite_miniatura_si_producto_esta_ahora_y_en_cola(self):
        ProductoImagen.objects.create(
            producto=self.producto,
            file_id="thumb-repetida-dashboard",
            url="https://example.com/repetida.jpg",
            thumbnail_url="https://example.com/repetida-thumb.jpg",
            orden=1,
        )
        ahora = timezone.now()
        Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            impresora=self.impresora_a,
            estado="IMPRIMIENDO",
            inicio_impresion=ahora,
            tiempo_impresion_minutos=90,
        )
        Produccion.objects.create(
            producto=self.producto,
            cantidad=2,
            estado="PENDIENTE",
            inicio_impresion=ahora + timedelta(hours=2),
            tiempo_impresion_minutos=120,
        )

        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "https://example.com/repetida-thumb.jpg",
            count=2,
        )

    def test_arrepentimiento_se_resuelve_desde_configuracion(self):
        solicitud = SolicitudArrepentimiento.objects.create(
            nombre="Cliente arrepentimiento",
            contacto="1144443333",
            estado="NUEVA",
        )

        configuracion = self.client.get(
            reverse("dashboard:configuracion")
        )
        self.assertEqual(configuracion.status_code, 200)
        self.assertContains(
            configuracion,
            'form="resolverArrepentimiento'
            + str(solicitud.id)
            + '"',
        )
        self.assertContains(
            configuracion,
            'id="resolverArrepentimiento'
            + str(solicitud.id)
            + '"',
        )
        self.assertContains(
            configuracion,
            'action="'
            + reverse(
                "dashboard:arrepentimiento_resolver",
                args=[solicitud.id],
            )
            + '"',
        )

        respuesta = self.client.post(
            reverse(
                "dashboard:arrepentimiento_resolver",
                args=[solicitud.id],
            )
        )
        self.assertRedirects(
            respuesta,
            reverse("dashboard:configuracion") + "#legal",
        )

        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, "RESUELTA")

    def test_configuracion_redondeo_se_normaliza_a_multiplo_de_100(self):
        respuesta = self.client.post(
            reverse("dashboard:configuracion"),
            {
                "redondeo_precio_producto": "250",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        config = ConfiguracionCatalogo.objects.get(pk=1)
        self.assertEqual(
            config.redondeo_precio_producto,
            300,
        )

    def test_configuracion_sectorizada_muestra_una_seccion_por_vez(self):
        respuesta = self.client.get(
            reverse("dashboard:configuracion")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'class="cfg-workspace"')
        self.assertContains(respuesta, 'data-config-tab="tienda"')
        self.assertContains(respuesta, 'data-config-tab="whatsapp"')
        self.assertContains(respuesta, 'id="cfgSectionSelect"')
        self.assertContains(respuesta, 'class="cfg-save-dock"')
        self.assertContains(
            respuesta,
            '.cfg-section{display:none',
        )
        self.assertContains(
            respuesta,
            '.cfg-section.is-active{display:block}',
        )

    def test_configuracion_conserva_seccion_activa_al_guardar(self):
        respuesta = self.client.post(
            reverse("dashboard:configuracion"),
            {
                "config_seccion": "whatsapp",
                "redondeo_precio_producto": "100",
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("dashboard:configuracion")
            + "?guardado=1&periodo=30#whatsapp",
        )

    def test_configuracion_muestra_centro_y_plantillas_whatsapp(self):
        respuesta = self.client.get(
            reverse("dashboard:configuracion")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Tienda pública")
        self.assertContains(respuesta, "Mensajes de WhatsApp")
        self.assertContains(respuesta, "PEDIDOS Y COBROS")
        self.assertContains(respuesta, "OTROS CONTACTOS CON CLIENTES")
        self.assertContains(respuesta, "Pedido listo · pagado")
        self.assertContains(respuesta, "Pedido listo · con saldo")
        self.assertContains(
            respuesta,
            'name="redondeo_precio_producto"',
        )
        self.assertContains(
            respuesta,
            "Redondeo de precios de productos",
        )
        self.assertContains(respuesta, "Datos para cobrar")
        self.assertContains(
            respuesta,
            'name="whatsapp_pago_alias"',
        )
        self.assertContains(
            respuesta,
            'name="whatsapp_pago_titular"',
        )
        self.assertContains(respuesta, "Saldo pendiente")
        self.assertContains(respuesta, "Múltiples pedidos")
        self.assertContains(respuesta, "Reactivar cliente")
        self.assertContains(
            respuesta,
            'name="whatsapp_mensaje_cliente_pedido_listo"',
        )
        self.assertContains(
            respuesta,
            'id="dvWhatsappDefaults"',
        )
        self.assertContains(
            respuesta,
            'name="mostrar_productos_sin_foto"',
        )
        self.assertContains(
            respuesta,
            "Mostrar productos sin foto",
        )

    def test_configuracion_guarda_tienda_y_mensajes_whatsapp(self):
        respuesta = self.client.post(
            reverse("dashboard:configuracion"),
            {
                "catalogo_activo": "on",
                "mostrar_productos_sin_foto": "on",
                "notificaciones_pedidos_web_activas": "on",
                "mostrar_instagram": "on",
                "mostrar_whatsapp": "on",
                "mensaje_mantenimiento": "Volvemos pronto.",
                "mensaje_plazo_entrega": (
                    "Entrega entre 3 y 10 días hábiles desde la confirmación."
                ),
                "redondeo_precio_producto": "100",
                "instagram_usuario": "@doblev3d_nuevo",
                "whatsapp_numero": "+54 9 11 1234-5678",
                "whatsapp_pago_alias": "doblev3d.prueba",
                "whatsapp_pago_titular": "Titular Prueba",
                "whatsapp_mensaje": "Hola catálogo",
                "whatsapp_mensaje_respuesta_solicitud": (
                    "Hola {nombre}, recibimos {codigo}"
                ),
                "whatsapp_mensaje_post_solicitud": (
                    "Envié {codigo} por {total}"
                ),
                "whatsapp_mensaje_cliente_generico": (
                    "Hola {nombre}, mensaje general"
                ),
                "whatsapp_mensaje_cliente_pedido_listo": (
                    "{nombre}: {codigo} listo"
                ),
                "whatsapp_mensaje_cliente_pedido_listo_saldo": (
                    "{nombre}: {codigo} listo con saldo {saldo}"
                ),
                "whatsapp_mensaje_cliente_saldo": (
                    "{nombre}: saldo {saldo}"
                ),
                "whatsapp_mensaje_cliente_multiples_pedidos": (
                    "{nombre}: {cantidad_pedidos} pedidos por {saldo_total}"
                ),
                "whatsapp_mensaje_cliente_presupuesto": (
                    "{nombre}: presupuesto {codigo}"
                ),
                "whatsapp_mensaje_cliente_reactivacion": (
                    "{nombre}: pasaron {dias_sin_actividad} días"
                ),
                "razon_social": "Responsable Doble V 3D",
                "cuit": "20-12345678-9",
                "domicilio_legal": "Domicilio de prueba",
                "email_legal": "legal@example.com",
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("dashboard:configuracion") + "?guardado=1&periodo=30#tienda",
        )

        config = ConfiguracionCatalogo.objects.get(pk=1)
        self.assertTrue(config.mostrar_productos_sin_foto)
        self.assertEqual(
            config.mensaje_plazo_entrega,
            "Entrega entre 3 y 10 días hábiles desde la confirmación.",
        )
        self.assertEqual(
            config.redondeo_precio_producto,
            100,
        )
        self.assertEqual(
            config.instagram_usuario,
            "doblev3d_nuevo",
        )
        self.assertEqual(
            config.whatsapp_numero,
            "5491112345678",
        )
        self.assertEqual(
            config.whatsapp_pago_alias,
            "doblev3d.prueba",
        )
        self.assertEqual(
            config.whatsapp_pago_titular,
            "Titular Prueba",
        )
        self.assertEqual(
            config.whatsapp_mensaje_cliente_pedido_listo,
            "{nombre}: {codigo} listo",
        )
        self.assertEqual(
            config.whatsapp_mensaje_cliente_pedido_listo_saldo,
            "{nombre}: {codigo} listo con saldo {saldo}",
        )
        self.assertEqual(
            config.whatsapp_mensaje_cliente_saldo,
            "{nombre}: saldo {saldo}",
        )
        self.assertEqual(
            config.whatsapp_mensaje_cliente_multiples_pedidos,
            "{nombre}: {cantidad_pedidos} pedidos por {saldo_total}",
        )
        self.assertEqual(
            config.razon_social,
            "Responsable Doble V 3D",
        )
        self.assertEqual(
            config.cuit,
            "20-12345678-9",
        )
        self.assertEqual(
            config.email_legal,
            "legal@example.com",
        )

