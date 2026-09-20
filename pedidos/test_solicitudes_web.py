import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from costos.models import ConfiguracionCostos
from kits.models import Kit, KitComponente
from pedidos.models import Presupuesto, SolicitudWeb
from productos.models import Producto, TipoProducto
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
                "nombre": "Cliente desde web",
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
            )
        )

        self.assertEqual(response.status_code, 302)
        self.solicitud.refresh_from_db()
        presupuesto = Presupuesto.objects.get(
            id=self.solicitud.presupuesto_generado_id
        )
        self.assertEqual(presupuesto.cliente_id, existente.id)
        self.assertEqual(Cliente.objects.count(), 1)

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
                "nombre": "Cliente kit web",
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

