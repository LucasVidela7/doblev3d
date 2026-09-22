import json
from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings
from django.urls import reverse

from calculadora.precios import calcular_escenarios_producto
from costos.models import ConfiguracionCostos
from kits.economia import precio_automatico_kit_libre
from kits.models import Kit, KitComponente
from pedidos.models import Presupuesto, SolicitudWeb
from clientes.models import Cliente
from productos.models import ConfiguracionCatalogo, Producto, TipoProducto


@override_settings(
    SECURE_SSL_REDIRECT=False,
    TURNSTILE_SITE_KEY="",
    TURNSTILE_SECRET_KEY="",
)
class CarritoPublicoTests(TestCase):
    def setUp(self):
        ConfiguracionCostos.objects.create(
            nombre="Costos carrito",
            coste_plastico_kg=Decimal("10000"),
            coste_plastico_kg_cantidad=Decimal("9000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        self.tipo = TipoProducto.objects.create(
            nombre="Sensoriales carrito",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Producto carrito",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("100"),
            margen_ganancia=Decimal("50"),
            activo=True,
            solo_produccion=False,
        )

    def _post(self, payload, telefono="+54 11 5555 1234"):
        return self.client.post(
            reverse("catalogo_carrito"),
            {
                "nombre": "Cliente Web",
                "telefono": telefono,
                "email": "cliente@example.com",
                "observaciones": "Prueba web",
                "cart_payload": json.dumps(payload),
                "website": "",
            },
        )

    def test_checkout_es_publico_y_muestra_loader(self):
        response = self.client.get(reverse("catalogo_carrito"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ENVIAR SOLICITUD DE PRESUPUESTO")
        self.assertContains(response, "Validando tu solicitud")
        self.assertContains(response, "data-checkout-loader")

    def test_producto_crea_solicitud_sin_crear_cliente_ni_presupuesto(self):
        response = self._post(
            [
                {
                    "kind": "product",
                    "id": self.producto.id,
                    "qty": 2,
                    "unitPrice": 1,
                }
            ]
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(SolicitudWeb.objects.count(), 1)
        self.assertEqual(Cliente.objects.count(), 0)
        self.assertEqual(Presupuesto.objects.count(), 0)

        solicitud = SolicitudWeb.objects.get()
        item = solicitud.items.get()
        # La regla vigente mantiene precio de lista entre 1 y 4
        # unidades; los descuentos de producto comienzan desde 5.
        esperado_unitario = self.producto.subtotal

        self.assertEqual(item.precio_base_unitario, self.producto.subtotal)
        self.assertEqual(item.precio_unitario, esperado_unitario)
        self.assertEqual(item.cantidad, 2)
        self.assertEqual(solicitud.total, esperado_unitario * Decimal("2"))

    def test_solicitud_duplicada_no_genera_dos_registros(self):
        payload = [
            {
                "kind": "product",
                "id": self.producto.id,
                "qty": 1,
            }
        ]

        primera = self._post(payload)
        segunda = self._post(payload)

        self.assertEqual(primera.status_code, 302)
        self.assertEqual(segunda.status_code, 302)
        self.assertEqual(SolicitudWeb.objects.count(), 1)

    def test_honeypot_no_crea_solicitud(self):
        response = self.client.post(
            reverse("catalogo_carrito"),
            {
                "nombre": "Bot",
                "telefono": "1155555555",
                "cart_payload": json.dumps(
                    [{"kind": "product", "id": self.producto.id, "qty": 1}]
                ),
                "website": "https://spam.example",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(SolicitudWeb.objects.count(), 0)

    def test_kit_libre_se_recalcula_en_servidor(self):
        economico = Producto.objects.create(
            nombre="Opción económica",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("80"),
            margen_ganancia=Decimal("50"),
            activo=True,
            solo_produccion=False,
        )
        premium = Producto.objects.create(
            nombre="Opción premium",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("1000"),
            margen_ganancia=Decimal("65"),
            activo=True,
            solo_produccion=False,
        )
        kit = Kit.objects.create(
            nombre="Kit carrito configurable",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("3000"),
            proteger_rentabilidad_libre=True,
            activo=True,
        )

        response = self._post(
            [
                {
                    "kind": "kit",
                    "id": kit.id,
                    "qty": 1,
                    "unitPrice": 1,
                    "selections": [
                        {"id": economico.id},
                        {"id": premium.id},
                    ],
                }
            ],
            telefono="+54 11 5555 9999",
        )

        self.assertEqual(response.status_code, 302)
        item = SolicitudWeb.objects.get().items.get()
        esperado = precio_automatico_kit_libre(
            kit,
            [economico, premium],
        )
        self.assertEqual(item.precio_unitario, esperado)
        self.assertEqual(
            item.adicional_unitario,
            max(esperado - kit.precio, Decimal("0")),
        )
        self.assertEqual(item.productos_kit.count(), 2)

    def test_kit_libre_rechaza_seleccion_incompleta(self):
        kit = Kit.objects.create(
            nombre="Kit carrito incompleto",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("3000"),
            proteger_rentabilidad_libre=True,
            activo=True,
        )

        response = self._post(
            [
                {
                    "kind": "kit",
                    "id": kit.id,
                    "qty": 1,
                    "selections": [{"id": self.producto.id}],
                }
            ],
            telefono="+54 11 5555 8888",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "necesita exactamente")
        self.assertEqual(SolicitudWeb.objects.count(), 0)


    def test_api_precios_aplica_descuento_de_producto_por_cantidad(self):
        response = self.client.post(
            reverse("catalogo_carrito_precios"),
            data=json.dumps(
                [
                    {
                        "key": "product:%s:" % self.producto.id,
                        "kind": "product",
                        "id": self.producto.id,
                        "qty": 10,
                        "selections": [],
                    }
                ]
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        linea = data["lineas"][0]
        self.assertLess(
            linea["precio_final_total"],
            linea["precio_lista_total"],
        )
        self.assertGreater(linea["descuento_porcentaje"], 0)

    def test_api_precios_aplica_volumen_desde_dos_kits(self):
        kit = Kit.objects.create(
            nombre="Kit fijo volumen web",
            modalidad="FIJO",
            cantidad_productos=1,
            precio=Decimal("5000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=self.producto,
            cantidad=1,
        )

        response = self.client.post(
            reverse("catalogo_carrito_precios"),
            data=json.dumps(
                [
                    {
                        "key": "kit:%s:" % kit.id,
                        "kind": "kit",
                        "id": kit.id,
                        "qty": 2,
                        "selections": [],
                    }
                ]
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        linea = data["lineas"][0]
        self.assertLess(
            linea["precio_final_total"],
            linea["precio_lista_total"],
        )
        self.assertGreater(linea["descuento_porcentaje"], 0)

    def test_confirmacion_ofrece_whatsapp_con_detalle(self):
        response = self._post(
            [
                {
                    "kind": "product",
                    "id": self.producto.id,
                    "qty": 1,
                }
            ],
            telefono="+54 11 5555 7777",
        )
        self.assertEqual(response.status_code, 302)

        gracias = self.client.get(
            reverse("catalogo_carrito_gracias")
        )
        self.assertEqual(gracias.status_code, 200)
        self.assertContains(
            gracias,
            "ENVIAR DETALLE POR WHATSAPP",
        )
        self.assertContains(
            gracias,
            "https://wa.me/5491164760709",
        )
        self.assertContains(gracias, "WEB0001")


    def test_kits_fijos_distintos_no_combinan_descuento(self):
        kit_a = Kit.objects.create(
            nombre="Kit fijo A independiente",
            modalidad="FIJO",
            cantidad_productos=1,
            precio=Decimal("5000"),
            activo=True,
        )
        kit_b = Kit.objects.create(
            nombre="Kit fijo B independiente",
            modalidad="FIJO",
            cantidad_productos=1,
            precio=Decimal("5000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=kit_a,
            producto=self.producto,
            cantidad=1,
        )
        KitComponente.objects.create(
            kit=kit_b,
            producto=self.producto,
            cantidad=1,
        )

        response = self.client.post(
            reverse("catalogo_carrito_precios"),
            data=json.dumps(
                [
                    {
                        "key": "kit:%s:" % kit_a.id,
                        "kind": "kit",
                        "id": kit_a.id,
                        "qty": 1,
                        "selections": [],
                    },
                    {
                        "key": "kit:%s:" % kit_b.id,
                        "kind": "kit",
                        "id": kit_b.id,
                        "qty": 1,
                        "selections": [],
                    },
                ]
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["ahorro"], 0)
        self.assertTrue(
            all(
                linea["descuento_porcentaje"] == 0
                for linea in data["lineas"]
            )
        )

    def test_kits_libres_misma_categoria_si_combinan_descuento(self):
        kit_a = Kit.objects.create(
            nombre="Kit libre A misma categoría",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=1,
            precio=Decimal("5000"),
            proteger_rentabilidad_libre=False,
            activo=True,
        )
        kit_b = Kit.objects.create(
            nombre="Kit libre B misma categoría",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=1,
            precio=Decimal("5000"),
            proteger_rentabilidad_libre=False,
            activo=True,
        )

        response = self.client.post(
            reverse("catalogo_carrito_precios"),
            data=json.dumps(
                [
                    {
                        "key": "kit:%s:%s" % (kit_a.id, self.producto.id),
                        "kind": "kit",
                        "id": kit_a.id,
                        "qty": 1,
                        "selections": [{"id": self.producto.id}],
                    },
                    {
                        "key": "kit:%s:%s" % (kit_b.id, self.producto.id),
                        "kind": "kit",
                        "id": kit_b.id,
                        "qty": 1,
                        "selections": [{"id": self.producto.id}],
                    },
                ]
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["ok"])
        self.assertGreater(data["ahorro"], 0)
        self.assertTrue(
            any(
                linea["descuento_porcentaje"] > 0
                for linea in data["lineas"]
            )
        )

    def test_api_precios_mantiene_descuentos_con_mas_de_cien_unidades(self):
        productos = [self.producto]
        for indice in range(5):
            productos.append(
                Producto.objects.create(
                    nombre=f"Producto volumen {indice}",
                    categoria="PRODUCTO",
                    tipo=self.tipo,
                    peso_gramos=Decimal("100"),
                    margen_ganancia=Decimal("50"),
                    activo=True,
                    solo_produccion=False,
                )
            )

        payload = [
            {
                "key": "product:%s:" % producto.id,
                "kind": "product",
                "id": producto.id,
                "qty": 20,
                "selections": [],
            }
            for producto in productos
        ]

        precios = self.client.post(
            reverse("catalogo_carrito_precios"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(precios.status_code, 200)
        data = precios.json()
        self.assertTrue(data["ok"])
        self.assertGreater(data["ahorro"], 0)

        checkout = self._post(
            payload,
            telefono="+54 11 5555 3030",
        )
        self.assertEqual(checkout.status_code, 200)
        self.assertContains(checkout, "¿Necesitás más de 100 unidades?")
        self.assertContains(checkout, "CONSULTAR POR WHATSAPP")
        self.assertEqual(SolicitudWeb.objects.count(), 0)

    def test_producto_inactivo_en_carrito_se_identifica_por_nombre(self):
        self.producto.activo = False
        self.producto.save(update_fields=["activo"])

        response = self._post(
            [
                {
                    "kind": "product",
                    "id": self.producto.id,
                    "qty": 1,
                }
            ],
            telefono="+54 11 5555 4040",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.producto.nombre)
        self.assertContains(response, "ya no está disponible")
        self.assertEqual(SolicitudWeb.objects.count(), 0)

    def test_confirmacion_y_whatsapp_incluyen_detalle_publico_tokenizado(self):
        response = self._post(
            [
                {
                    "kind": "product",
                    "id": self.producto.id,
                    "qty": 1,
                }
            ],
            telefono="+54 11 5555 5050",
        )
        self.assertEqual(response.status_code, 302)

        solicitud = SolicitudWeb.objects.get()
        detalle_url = reverse(
            "solicitud_publica",
            args=[solicitud.public_token],
        )

        gracias = self.client.get(reverse("catalogo_carrito_gracias"))
        self.assertContains(gracias, "VER DETALLE DE MI SOLICITUD")
        self.assertContains(gracias, detalle_url)

        detalle = self.client.get(detalle_url)
        self.assertEqual(detalle.status_code, 200)
        self.assertContains(detalle, solicitud.codigo)
        self.assertContains(detalle, self.producto.nombre)
        self.assertContains(detalle, "TOTAL SOLICITADO")


    def test_checkout_muestra_plazo_desde_confirmacion_del_presupuesto(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.mensaje_plazo_entrega = (
            "Entre 3 y 10 días hábiles después de confirmar el presupuesto."
        )
        config.save(update_fields=["mensaje_plazo_entrega"])

        response = self.client.get(reverse("catalogo_carrito"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "Entre 3 y 10 días hábiles después de confirmar el presupuesto.",
        )
        self.assertContains(
            response,
            "El plazo comienza una vez confirmado el presupuesto.",
        )

    def test_checkout_orienta_compra_y_pedido_especial(self):
        response = self.client.get(
            reverse("catalogo_carrito")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PASO")
        self.assertContains(response, "TOTAL ESTIMADO")
        self.assertContains(response, "EDITAR CARRITO")
        self.assertContains(
            response,
            "¿No encontraste un producto en la tienda?",
        )
        self.assertContains(
            response,
            "data-special-observation",
        )
        self.assertContains(
            response,
            "?motivo=producto_especial",
        )
        self.assertContains(
            response,
            "No pagás nada ahora",
        )

    def test_confirmacion_explica_que_sigue_y_el_plazo(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(
            pk=1
        )
        config.mensaje_plazo_entrega = (
            "Entrega de prueba luego de confirmar."
        )
        config.save(
            update_fields=["mensaje_plazo_entrega"]
        )

        self._post(
            [
                {
                    "kind": "product",
                    "id": self.producto.id,
                    "qty": 1,
                }
            ],
            telefono="+54 11 5555 6060",
        )

        response = self.client.get(
            reverse("catalogo_carrito_gracias")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "¿Qué pasa ahora?")
        self.assertContains(response, "Chequeamos tu solicitud")
        self.assertContains(
            response,
            "Comenzamos después de tu OK",
        )
        self.assertContains(
            response,
            "Entrega de prueba luego de confirmar.",
        )
        self.assertNotContains(response, "VOLVER ATRÁS")

