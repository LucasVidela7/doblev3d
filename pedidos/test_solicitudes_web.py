import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from costos.models import ConfiguracionCostos
from kits.models import Kit, KitComponente
from pedidos.models import (
    Presupuesto,
    SolicitudWeb,
    SolicitudWebItem,
    SolicitudWebKitProducto,
)
from productos.models import ConfiguracionCatalogo, Producto, TipoProducto
from productos.whatsapp import renderizar_mensaje_solicitud
from productos.image_models import ProductoImagen


@override_settings(
    SECURE_SSL_REDIRECT=False,
    TURNSTILE_SITE_KEY="",
    TURNSTILE_SECRET_KEY="",
)
class SolicitudesWebGestionTests(TestCase):
    def setUp(self):
        ConfiguracionCostos.objects.create(
            nombre="Costos gestión web",
            coste_plastico_kg=Decimal("10000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        tipo = TipoProducto.objects.create(
            nombre="Web gestión",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Producto solicitud gestión",
            categoria="PRODUCTO",
            tipo=tipo,
            peso_gramos=Decimal("100"),
            margen_ganancia=Decimal("50"),
            activo=True,
            solo_produccion=False,
        )

        response = self.client.post(
            reverse("catalogo_carrito"),
            {
                "nombre": "Cliente",
                "apellido": "desde web",
                "telefono": "+54 11 4000 1234",
                "email": "web@example.com",
                "observaciones": "Color azul",
                "cart_payload": json.dumps(
                    [
                        {
                            "kind": "product",
                            "id": self.producto.id,
                            "qty": 2,
                        }
                    ]
                ),
                "website": "",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.solicitud = SolicitudWeb.objects.get()

        user = get_user_model().objects.create_user(
            username="operador-web",
            password="test-pass-123",
        )
        self.client.force_login(user)

    def test_bandeja_y_detalle_estan_protegidos_y_disponibles_logueado(self):
        response = self.client.get(reverse("pedidos:solicitudes_web"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.solicitud.codigo)
        self.assertContains(response, "Cliente desde web")
        self.assertContains(response, "+54 11 4000 1234")
        self.assertContains(
            response,
            "dv-commercial-page dv-commercial-board dv-solicitudes-page",
        )
        self.assertContains(response, "pedidos/comercial_gestion")

        detail = self.client.get(
            reverse(
                "pedidos:solicitud_web_detalle",
                args=[self.solicitud.id],
            )
        )
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, "CONVERTIR EN PRESUPUESTO")
        self.assertContains(detail, "WHATSAPP")
        self.assertContains(detail, self.producto.nombre)
        self.assertContains(
            detail,
            "dv-commercial-page dv-commercial-detail dv-solicitudes-page",
        )

    def test_adicionales_se_ven_en_solicitud_y_pedido_publico_y_gestion(self):
        kit = Kit.objects.create(
            nombre="Kit con adicionales visibles",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.producto.tipo,
            cantidad_productos=1,
            precio=Decimal("25000"),
            activo=True,
        )
        solicitud = SolicitudWeb.objects.create(
            nombre="Cliente adicionales",
            telefono="+54 11 4777 8899",
            email="extras@example.com",
            estado="NUEVA",
        )
        item = SolicitudWebItem.objects.create(
            solicitud=solicitud,
            tipo_item="KIT",
            kit=kit,
            cantidad=2,
            nombre_snapshot=kit.nombre,
            precio_base_unitario=Decimal("25000"),
            adicional_unitario=Decimal("2000"),
            adicional_color_unitario=Decimal("500"),
            precio_unitario=Decimal("26000"),
            modo_color="ESPECIFICO",
            color_elegido="Acqua",
            kit_snapshot={
                "nombre": kit.nombre,
                "precio_base": "25000",
                "precio_unitario_vendido": "26000",
            },
        )
        SolicitudWebKitProducto.objects.create(
            item=item,
            producto=self.producto,
            cantidad=2,
        )

        gestion_solicitud = self.client.get(
            reverse(
                "pedidos:solicitud_web_detalle",
                args=[solicitud.id],
            )
        )
        publica_solicitud = self.client.get(
            reverse(
                "solicitud_publica",
                args=[solicitud.public_token],
            )
        )

        for respuesta in (
            gestion_solicitud,
            publica_solicitud,
        ):
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(respuesta, "1.500")
            self.assertContains(respuesta, "500")
            self.assertContains(respuesta, "4.000")

        convertir = self.client.post(
            reverse(
                "pedidos:solicitud_web_convertir",
                args=[solicitud.id],
            )
        )
        self.assertEqual(convertir.status_code, 302)
        solicitud.refresh_from_db()
        presupuesto = solicitud.presupuesto_generado

        aprobar = self.client.post(
            reverse(
                "pedidos:presupuesto_aprobar",
                args=[presupuesto.id],
            )
        )
        self.assertEqual(aprobar.status_code, 302)
        presupuesto.refresh_from_db()
        pedido = presupuesto.pedido_generado

        gestion_pedido = self.client.get(
            reverse(
                "pedidos:detalle",
                args=[pedido.id],
            )
        )
        publico_pedido = self.client.get(
            reverse(
                "pedido_publico",
                args=[pedido.public_token],
            )
        )

        for respuesta in (
            gestion_pedido,
            publico_pedido,
        ):
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(respuesta, "1.500")
            self.assertContains(respuesta, "500")
            self.assertContains(respuesta, "4.000")
            self.assertContains(respuesta, "1.000")

        detalle_presupuesto = presupuesto.detalles.get()
        self.assertEqual(
            detalle_presupuesto.kit_snapshot[
                "adicional_opciones_unitario"
            ],
            "1500",
        )
        self.assertEqual(
            detalle_presupuesto.kit_snapshot[
                "adicional_color_unitario"
            ],
            "500",
        )

    def test_whatsapp_respuesta_usa_solo_primer_nombre(self):
        mensaje = renderizar_mensaje_solicitud(
            "Hola {nombre}!",
            self.solicitud,
        )

        self.assertEqual(mensaje, "Hola Cliente!")
        self.assertNotIn("desde web", mensaje)

    def test_whatsapp_respuesta_calcula_senia_y_fecha_hoy(self):
        mensaje = renderizar_mensaje_solicitud(
            "Seña: {senia} | Fecha: {fecha_hoy}",
            self.solicitud,
        )
        senia = Decimal(str(self.solicitud.total)) * Decimal("0.30")
        senia_formateada = "$ " + f"{senia:,.0f}".replace(",", ".")

        self.assertIn(f"Seña: {senia_formateada}", mensaje)
        self.assertIn(
            timezone.localdate().strftime("%d/%m/%Y"),
            mensaje,
        )


    def test_whatsapp_respuesta_solicitud_incluye_alias_configurado(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.whatsapp_pago_alias = "doblev3d.senia"
        config.whatsapp_pago_titular = "Titular Seña"
        config.save(
            update_fields=[
                "whatsapp_pago_alias",
                "whatsapp_pago_titular",
            ]
        )

        mensaje = renderizar_mensaje_solicitud(
            "Seña: {senia}\n{datos_pago}",
            self.solicitud,
            config=config,
            incluir_datos_pago=True,
        )

        self.assertIn(
            "Alias: doblev3d.senia - Titular Seña",
            mensaje,
        )

    def test_convertir_crea_cliente_y_presupuesto_sin_crear_pedido(self):
        response = self.client.post(
            reverse(
                "pedidos:solicitud_web_convertir",
                args=[self.solicitud.id],
            )
        )

        self.assertEqual(response.status_code, 302)

        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, "CONVERTIDA")
        self.assertIsNotNone(self.solicitud.presupuesto_generado_id)

        presupuesto = Presupuesto.objects.get(
            id=self.solicitud.presupuesto_generado_id
        )
        self.assertEqual(presupuesto.estado, "PENDIENTE")
        self.assertEqual(presupuesto.detalles.count(), 1)
        detalle = presupuesto.detalles.get()
        self.assertEqual(detalle.producto, self.producto)
        self.assertEqual(detalle.cantidad, 2)
        item_web = self.solicitud.items.get()
        self.assertEqual(detalle.precio_unitario, item_web.precio_unitario)
        self.assertEqual(
            detalle.precio_lista_unitario,
            self.producto.subtotal,
        )

        cliente = Cliente.objects.get(id=presupuesto.cliente_id)
        self.assertEqual(cliente.nombre, "Cliente desde web")
        self.assertEqual(cliente.telefono, "+54 11 4000 1234")
        self.assertIsNone(presupuesto.pedido_generado)

    def test_convertir_reutiliza_cliente_con_mismo_telefono_en_otro_formato(self):
        existente = Cliente.objects.create(
            nombre="Cliente previo",
            telefono="11 4000-1234",
            activo=True,
        )

        response = self.client.post(
            reverse(
                "pedidos:solicitud_web_convertir",
                args=[self.solicitud.id],
            ),
            {"datos_cliente": "MANTENER"},
        )

        self.assertEqual(response.status_code, 302)
        self.solicitud.refresh_from_db()
        presupuesto = Presupuesto.objects.get(
            id=self.solicitud.presupuesto_generado_id
        )
        self.assertEqual(presupuesto.cliente_id, existente.id)
        self.assertEqual(Cliente.objects.count(), 1)

        existente.refresh_from_db()
        self.assertEqual(existente.nombre, "Cliente previo")
        self.assertEqual(existente.telefono, "11 4000-1234")
        self.assertEqual(existente.email, "web@example.com")

    def test_detalle_advierte_si_nombre_no_coincide_con_telefono(self):
        Cliente.objects.create(
            nombre="Lucas Videla",
            telefono="11 4000-1234",
            email="original@example.com",
            activo=True,
        )
        self.solicitud.nombre = "Lucas Alala"
        self.solicitud.email = "nuevo@example.com"
        self.solicitud.save(update_fields=["nombre", "email"])

        response = self.client.get(
            reverse(
                "pedidos:solicitud_web_detalle",
                args=[self.solicitud.id],
            )
        )

        self.assertContains(
            response,
            "Datos distintos para un cliente existente",
        )
        self.assertContains(response, "Lucas Videla")
        self.assertContains(response, "Lucas Alala")
        self.assertContains(response, 'value="MANTENER"')
        self.assertContains(response, 'value="ACTUALIZAR"')

    def test_convertir_conservar_no_sobrescribe_ficha_existente(self):
        existente = Cliente.objects.create(
            nombre="Lucas Videla",
            telefono="11 4000-1234",
            email="original@example.com",
            activo=True,
        )
        self.solicitud.nombre = "Lucas Alala"
        self.solicitud.email = "nuevo@example.com"
        self.solicitud.save(update_fields=["nombre", "email"])

        response = self.client.post(
            reverse(
                "pedidos:solicitud_web_convertir",
                args=[self.solicitud.id],
            ),
            {"datos_cliente": "MANTENER"},
        )

        self.assertEqual(response.status_code, 302)
        existente.refresh_from_db()
        self.assertEqual(existente.nombre, "Lucas Videla")
        self.assertEqual(existente.email, "original@example.com")
        self.assertEqual(
            self.solicitud.__class__.objects.get(id=self.solicitud.id).nombre,
            "Lucas Alala",
        )

    def test_convertir_actualizar_requiere_decision_explicita(self):
        existente = Cliente.objects.create(
            nombre="Lucas Videla",
            telefono="11 4000-1234",
            email="original@example.com",
            activo=True,
        )
        self.solicitud.nombre = "Lucas Alala"
        self.solicitud.email = "nuevo@example.com"
        self.solicitud.save(update_fields=["nombre", "email"])

        bloqueada = self.client.post(
            reverse(
                "pedidos:solicitud_web_convertir",
                args=[self.solicitud.id],
            )
        )
        self.assertEqual(bloqueada.status_code, 302)
        self.solicitud.refresh_from_db()
        self.assertIsNone(self.solicitud.presupuesto_generado_id)

        actualizada = self.client.post(
            reverse(
                "pedidos:solicitud_web_convertir",
                args=[self.solicitud.id],
            ),
            {"datos_cliente": "ACTUALIZAR"},
        )

        self.assertEqual(actualizada.status_code, 302)
        existente.refresh_from_db()
        self.assertEqual(existente.nombre, "Lucas Alala")
        self.assertEqual(existente.email, "nuevo@example.com")
        self.assertEqual(existente.telefono, "11 4000-1234")

    def test_email_vacio_se_completa_sin_cambiar_nombre(self):
        existente = Cliente.objects.create(
            nombre="Cliente desde web",
            telefono="11 4000-1234",
            email="",
            activo=True,
        )

        response = self.client.post(
            reverse(
                "pedidos:solicitud_web_convertir",
                args=[self.solicitud.id],
            ),
            {"datos_cliente": "MANTENER"},
        )

        self.assertEqual(response.status_code, 302)
        existente.refresh_from_db()
        self.assertEqual(existente.nombre, "Cliente desde web")
        self.assertEqual(existente.email, "web@example.com")

    def test_marcar_contactada_no_convierte(self):
        response = self.client.post(
            reverse(
                "pedidos:solicitud_web_contactada",
                args=[self.solicitud.id],
            )
        )

        self.assertEqual(response.status_code, 302)
        self.solicitud.refresh_from_db()
        self.assertEqual(self.solicitud.estado, "CONTACTADA")
        self.assertIsNone(self.solicitud.presupuesto_generado_id)

    def test_bandeja_filtra_por_estado(self):
        self.solicitud.estado = "CONTACTADA"
        self.solicitud.save(update_fields=["estado"])

        otra = SolicitudWeb.objects.create(
            nombre="Otra solicitud",
            telefono="1144445555",
            estado="NUEVA",
        )

        respuesta = self.client.get(
            reverse("pedidos:solicitudes_web"),
            {"estado": "CONTACTADA"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.solicitud.codigo)
        self.assertNotContains(respuesta, otra.codigo)
        self.assertEqual(
            respuesta.context["estado_seleccionado"],
            "CONTACTADA",
        )

    def test_foto_aparece_en_bandeja_y_detalle_web(self):
        ProductoImagen.objects.create(
            producto=self.producto,
            file_id="solicitud-thumb",
            url="https://example.com/solicitud.jpg",
            thumbnail_url="https://example.com/solicitud-thumb.jpg",
            orden=1,
        )

        bandeja = self.client.get(
            reverse("pedidos:solicitudes_web")
        )
        detalle = self.client.get(
            reverse(
                "pedidos:solicitud_web_detalle",
                args=[self.solicitud.id],
            )
        )

        for respuesta in (bandeja, detalle):
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(
                respuesta,
                "https://example.com/solicitud-thumb.jpg",
            )

    def test_kit_web_conserva_snapshot_al_convertir_presupuesto(self):
        kit = Kit.objects.create(
            nombre="Kit snapshot web",
            modalidad="FIJO",
            cantidad_productos=2,
            precio=Decimal("15000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=self.producto,
            cantidad=2,
        )

        respuesta = self.client.post(
            reverse("catalogo_carrito"),
            {
                "nombre": "Cliente",
                "apellido": "kit web",
                "telefono": "+54 11 4999 7788",
                "email": "kitweb@example.com",
                "observaciones": "",
                "cart_payload": json.dumps(
                    [
                        {
                            "kind": "kit",
                            "id": kit.id,
                            "qty": 2,
                            "selections": [],
                        }
                    ]
                ),
                "website": "",
            },
        )
        self.assertEqual(respuesta.status_code, 302)

        solicitud = (
            SolicitudWeb.objects
            .exclude(id=self.solicitud.id)
            .get()
        )
        item = solicitud.items.get()

        self.assertEqual(
            item.kit_snapshot["nombre"],
            "Kit snapshot web",
        )
        self.assertEqual(
            item.kit_snapshot["componentes"][0]["cantidad_total"],
            4,
        )

        snapshot_web = dict(item.kit_snapshot)

        kit.nombre = "Kit modificado luego"
        kit.precio = Decimal("30000")
        kit.save(update_fields=["nombre", "precio"])

        respuesta = self.client.post(
            reverse(
                "pedidos:solicitud_web_convertir",
                args=[solicitud.id],
            )
        )
        self.assertEqual(respuesta.status_code, 302)

        solicitud.refresh_from_db()
        detalle = (
            solicitud.presupuesto_generado
            .detalles.get()
        )
        self.assertEqual(
            detalle.kit_snapshot["nombre"],
            "Kit snapshot web",
        )
        self.assertEqual(
            detalle.kit_snapshot["precio_base"],
            snapshot_web["precio_base"],
        )

