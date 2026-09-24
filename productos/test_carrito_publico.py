import json
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from calculadora.precios import (
    MARGEN_MINIMO,
    calcular_costo_productivo_producto,
    calcular_escenarios_producto,
)
from costos.models import ConfiguracionCostos
from kits.economia import precio_automatico_kit_libre
from kits.models import Kit, KitComponente
from pedidos.models import Pedido, Presupuesto, SolicitudWeb
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
                "nombre": "Cliente",
                "apellido": "Web",
                "telefono": telefono,
                "email": "cliente@example.com",
                "observaciones": "Prueba web",
                "cart_payload": json.dumps(payload),
                "website": "",
            },
        )


    def test_checkout_pide_nombre_y_apellido_por_separado(self):
        response = self.client.get(reverse("catalogo_carrito"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="nombre"')
        self.assertContains(response, 'autocomplete="given-name"')
        self.assertContains(response, 'name="apellido"')
        self.assertContains(response, 'autocomplete="family-name"')

    def test_checkout_rechaza_solicitud_sin_apellido(self):
        response = self.client.post(
            reverse("catalogo_carrito"),
            {
                "nombre": "Lucas",
                "apellido": "",
                "telefono": "+54 11 5555 1200",
                "email": "",
                "observaciones": "",
                "cart_payload": json.dumps(
                    [
                        {
                            "kind": "product",
                            "id": self.producto.id,
                            "qty": 1,
                        }
                    ]
                ),
                "website": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ingresá tu apellido.")
        self.assertEqual(SolicitudWeb.objects.count(), 0)

    def test_checkout_guarda_nombre_completo(self):
        self._post(
            [
                {
                    "kind": "product",
                    "id": self.producto.id,
                    "qty": 1,
                }
            ],
            telefono="+54 11 5555 1201",
        )

        solicitud = SolicitudWeb.objects.get()
        self.assertEqual(solicitud.nombre, "Cliente Web")

    def test_detalle_publico_muestra_acceso_gestion_solo_con_sesion(self):
        self._post(
            [
                {
                    "kind": "product",
                    "id": self.producto.id,
                    "qty": 1,
                }
            ],
            telefono="+54 11 5555 8080",
        )
        solicitud = SolicitudWeb.objects.get()
        url_publica = reverse(
            "solicitud_publica",
            args=[solicitud.public_token],
        )
        url_gestion = reverse(
            "pedidos:solicitud_web_detalle",
            args=[solicitud.id],
        )

        anonima = self.client.get(url_publica)
        self.assertEqual(anonima.status_code, 200)
        self.assertNotContains(anonima, "VER EN GESTIÓN")
        self.assertNotContains(anonima, url_gestion)

        user = get_user_model().objects.create_user(
            username="admin-catalogo",
            password="test-pass-123",
        )
        self.client.force_login(user)

        autenticada = self.client.get(url_publica)
        self.assertEqual(autenticada.status_code, 200)
        self.assertContains(autenticada, "VER EN GESTIÓN")
        self.assertContains(autenticada, url_gestion)

    def test_detalle_publico_muestra_estado_real_del_flujo(self):
        self._post(
            [{"kind": "product", "id": self.producto.id, "qty": 1}],
            telefono="+54 11 5555 8181",
        )
        solicitud = SolicitudWeb.objects.get()
        url = reverse("solicitud_publica", args=[solicitud.public_token])

        recibida = self.client.get(url)
        self.assertContains(recibida, "Estado actual")
        self.assertContains(recibida, "Solicitud recibida")

        solicitud.estado = "CONTACTADA"
        solicitud.save(update_fields=["estado"])
        self.assertContains(self.client.get(url), "En contacto")

        cliente = Cliente.objects.create(
            nombre="Cliente estado público",
            telefono="1155558181",
            activo=True,
        )
        presupuesto = Presupuesto.objects.create(
            cliente=cliente,
            estado="PENDIENTE",
        )
        solicitud.estado = "CONVERTIDA"
        solicitud.presupuesto_generado = presupuesto
        solicitud.save(update_fields=["estado", "presupuesto_generado"])
        presupuesto_response = self.client.get(url)
        self.assertContains(presupuesto_response, "Presupuesto en revisión")
        self.assertContains(presupuesto_response, presupuesto.codigo)

        pedido = Pedido.objects.create(
            cliente=cliente,
            estado="PREPARANDO",
        )
        presupuesto.estado = "APROBADO"
        presupuesto.pedido_generado = pedido
        presupuesto.save(update_fields=["estado", "pedido_generado"])
        preparando = self.client.get(url)
        self.assertContains(preparando, "En preparación")
        self.assertContains(preparando, pedido.codigo)

        pedido.estado = "LISTO"
        pedido.save(update_fields=["estado"])
        self.assertContains(self.client.get(url), "Listo")

        pedido.estado = "ENTREGADO"
        pedido.save(update_fields=["estado"])
        self.assertContains(self.client.get(url), "Entregado")

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

    def test_producto_color_especifico_no_suma_adicional(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.colores_disponibles = "Rojo\nAzul"
        config.save(update_fields=["colores_disponibles"])
        self.producto.permite_elegir_color = True
        self.producto.save(update_fields=["permite_elegir_color"])

        response = self._post(
            [
                {
                    "kind": "product",
                    "id": self.producto.id,
                    "qty": 1,
                    "color_mode": "ESPECIFICO",
                    "color": "Rojo",
                }
            ],
            telefono="+54 11 5555 2101",
        )

        self.assertEqual(response.status_code, 302)
        item = SolicitudWeb.objects.get().items.get()
        self.assertEqual(item.modo_color, "ESPECIFICO")
        self.assertEqual(item.color_elegido, "Rojo")
        self.assertEqual(item.adicional_color_unitario, Decimal("0"))

    def test_kit_libre_mismo_color_suma_base_mas_productos(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.colores_disponibles = "Rojo\nAzul"
        config.adicional_color_kit_base = Decimal("1000")
        config.adicional_color_kit_por_producto = Decimal("500")
        config.save(
            update_fields=[
                "colores_disponibles",
                "adicional_color_kit_base",
                "adicional_color_kit_por_producto",
            ]
        )
        otro = Producto.objects.create(
            nombre="Otra opción color",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("90"),
            margen_ganancia=Decimal("50"),
            activo=True,
            solo_produccion=False,
        )
        kit = Kit.objects.create(
            nombre="Kit libre color",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("5000"),
            proteger_rentabilidad_libre=False,
            permite_elegir_color=True,
            activo=True,
        )

        response = self._post(
            [
                {
                    "kind": "kit",
                    "id": kit.id,
                    "qty": 1,
                    "selections": [
                        {"id": self.producto.id},
                        {"id": otro.id},
                    ],
                    "color_mode": "ESPECIFICO",
                    "color": "Azul",
                }
            ],
            telefono="+54 11 5555 2102",
        )

        self.assertEqual(response.status_code, 302)
        item = SolicitudWeb.objects.get().items.get()
        self.assertEqual(item.modo_color, "ESPECIFICO")
        self.assertEqual(item.color_elegido, "Azul")
        self.assertEqual(
            item.adicional_color_unitario,
            Decimal("2000"),
        )
        self.assertGreaterEqual(
            item.adicional_unitario,
            item.adicional_color_unitario,
        )

    def test_kit_fijo_color_especifico_no_suma_adicional(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.colores_disponibles = "Rojo\nAzul"
        config.save(update_fields=["colores_disponibles"])
        kit = Kit.objects.create(
            nombre="Kit fijo color",
            modalidad="FIJO",
            cantidad_productos=1,
            precio=Decimal("5000"),
            permite_elegir_color=True,
            activo=True,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=self.producto,
            cantidad=1,
        )

        response = self._post(
            [
                {
                    "kind": "kit",
                    "id": kit.id,
                    "qty": 1,
                    "color_mode": "ESPECIFICO",
                    "color": "Rojo",
                    "selections": [],
                }
            ],
            telefono="+54 11 5555 2103",
        )

        self.assertEqual(response.status_code, 302)
        item = SolicitudWeb.objects.get().items.get()
        self.assertEqual(item.color_elegido, "Rojo")
        self.assertEqual(item.adicional_color_unitario, Decimal("0"))

    def test_color_fuera_de_configuracion_se_rechaza(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.colores_disponibles = "Rojo\nAzul"
        config.save(update_fields=["colores_disponibles"])
        self.producto.permite_elegir_color = True
        self.producto.save(update_fields=["permite_elegir_color"])

        response = self._post(
            [
                {
                    "kind": "product",
                    "id": self.producto.id,
                    "qty": 1,
                    "color_mode": "ESPECIFICO",
                    "color": "Verde",
                }
            ],
            telefono="+54 11 5555 2104",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ya no está disponible")
        self.assertEqual(SolicitudWeb.objects.count(), 0)

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

    @override_settings(CATALOGO_ANTISPAM_ENABLED=False)
    def test_antispam_desactivado_ignora_honeypot(self):
        response = self.client.post(
            reverse("catalogo_carrito"),
            {
                "nombre": "Juan",
                "apellido": "Perez",
                "telefono": "1155555566",
                "email": "",
                "observaciones": "",
                "cart_payload": json.dumps(
                    [{"kind": "product", "id": self.producto.id, "qty": 1}]
                ),
                "website": "https://spam.example",
            },
        )

        self.assertEqual(response.status_code, 302)
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


    def test_kit_libre_rechaza_repeticion_por_encima_del_limite(self):
        kit = Kit.objects.create(
            nombre="Kit sin repetidos",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            max_repeticiones_producto=1,
            precio=Decimal("5000"),
            proteger_rentabilidad_libre=False,
            activo=True,
        )

        response = self._post(
            [
                {
                    "kind": "kit",
                    "id": kit.id,
                    "qty": 1,
                    "selections": [
                        {"id": self.producto.id},
                        {"id": self.producto.id},
                    ],
                }
            ],
            telefono="+54 11 5555 8899",
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "no puede repetirse")
        self.assertEqual(SolicitudWeb.objects.count(), 0)

    def test_detalle_publico_expone_limite_de_repeticion(self):
        otro = Producto.objects.create(
            nombre="Otra opción repetición",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("80"),
            margen_ganancia=Decimal("50"),
            activo=True,
            solo_produccion=False,
        )
        kit = Kit.objects.create(
            nombre="Kit límite público",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            max_repeticiones_producto=1,
            precio=Decimal("5000"),
            proteger_rentabilidad_libre=False,
            activo=True,
        )

        response = self.client.get(
            reverse("catalogo_kit_detalle", args=[kit.slug])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'data-max-per-product="1"',
        )
        self.assertContains(
            response,
            "Cada producto puede elegirse una sola vez.",
        )

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

    def test_api_kit_color_no_duplica_adicional_y_mantiene_descuento(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.colores_disponibles = "Rojo\nAzul"
        config.adicional_color_kit_base = Decimal("2500")
        config.adicional_color_kit_por_producto = Decimal("500")
        config.save(
            update_fields=[
                "colores_disponibles",
                "adicional_color_kit_base",
                "adicional_color_kit_por_producto",
            ]
        )

        otro = Producto.objects.create(
            nombre="Otra pieza para kit color",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("100"),
            margen_ganancia=Decimal("50"),
            activo=True,
            solo_produccion=False,
        )
        kit = Kit.objects.create(
            nombre="Kit color precio carrito",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("25000"),
            proteger_rentabilidad_libre=False,
            permite_elegir_color=True,
            activo=True,
        )

        payload_base = {
            "key": (
                "kit:%s:%s,%s:color:rojo"
                % (kit.id, self.producto.id, otro.id)
            ),
            "kind": "kit",
            "id": kit.id,
            "selections": [
                {"id": self.producto.id},
                {"id": otro.id},
            ],
            "color_mode": "ESPECIFICO",
            "color": "Rojo",
        }

        una = self.client.post(
            reverse("catalogo_carrito_precios"),
            data=json.dumps([{**payload_base, "qty": 1}]),
            content_type="application/json",
        )
        self.assertEqual(una.status_code, 200)
        linea_una = una.json()["lineas"][0]
        self.assertEqual(
            Decimal(str(linea_una["precio_lista_unitario"])),
            Decimal("28500"),
        )
        self.assertEqual(
            Decimal(str(linea_una["precio_unitario"])),
            Decimal("28500"),
        )
        self.assertEqual(
            Decimal(str(linea_una["adicional_color"])),
            Decimal("3500"),
        )

        dos_color = self.client.post(
            reverse("catalogo_carrito_precios"),
            data=json.dumps([{**payload_base, "qty": 2}]),
            content_type="application/json",
        )
        self.assertEqual(dos_color.status_code, 200)
        linea_color = dos_color.json()["lineas"][0]
        self.assertLess(
            linea_color["precio_final_total"],
            linea_color["precio_lista_total"],
        )
        self.assertGreater(linea_color["descuento_porcentaje"], 0)

        payload_surtido = {
            **payload_base,
            "key": (
                "kit:%s:%s,%s"
                % (kit.id, self.producto.id, otro.id)
            ),
            "color_mode": "SURTIDO",
            "color": "",
            "qty": 2,
        }
        dos_surtido = self.client.post(
            reverse("catalogo_carrito_precios"),
            data=json.dumps([payload_surtido]),
            content_type="application/json",
        )
        self.assertEqual(dos_surtido.status_code, 200)
        linea_surtido = dos_surtido.json()["lineas"][0]

        self.assertEqual(
            Decimal(str(linea_color["precio_unitario"]))
            - Decimal(str(linea_surtido["precio_unitario"])),
            Decimal("3500"),
        )

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


    def test_cuatro_kits_libres_separados_equivalen_a_un_x4(self):
        opciones = [self.producto]
        for indice, peso in enumerate(("80", "120", "170"), start=1):
            opciones.append(
                Producto.objects.create(
                    nombre=f"Opción kit x4 {indice}",
                    categoria="PRODUCTO",
                    tipo=self.tipo,
                    peso_gramos=Decimal(peso),
                    margen_ganancia=Decimal("50"),
                    activo=True,
                    solo_produccion=False,
                )
            )

        kit = Kit.objects.create(
            nombre="Kit libre equivalencia x4",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("25000"),
            proteger_rentabilidad_libre=False,
            activo=True,
        )

        combinaciones = [
            [opciones[0], opciones[1]],
            [opciones[0], opciones[2]],
            [opciones[1], opciones[3]],
            [opciones[2], opciones[3]],
        ]
        payload_separado = []
        for indice, seleccion in enumerate(combinaciones, start=1):
            payload_separado.append(
                {
                    "key": f"kit-separado-{indice}",
                    "kind": "kit",
                    "id": kit.id,
                    "qty": 1,
                    "selections": [
                        {"id": producto.id}
                        for producto in seleccion
                    ],
                }
            )

        separado = self.client.post(
            reverse("catalogo_carrito_precios"),
            data=json.dumps(payload_separado),
            content_type="application/json",
        )
        agrupado = self.client.post(
            reverse("catalogo_carrito_precios"),
            data=json.dumps(
                [
                    {
                        "key": "kit-agrupado-x4",
                        "kind": "kit",
                        "id": kit.id,
                        "qty": 4,
                        "selections": [
                            {"id": opciones[0].id},
                            {"id": opciones[1].id},
                        ],
                    }
                ]
            ),
            content_type="application/json",
        )

        self.assertEqual(separado.status_code, 200)
        self.assertEqual(agrupado.status_code, 200)

        lineas_separadas = separado.json()["lineas"]
        linea_agrupada = agrupado.json()["lineas"][0]
        descuentos = {
            Decimal(str(linea["descuento_porcentaje"]))
            for linea in lineas_separadas
        }

        self.assertEqual(len(descuentos), 1)
        descuento_separado = descuentos.pop()
        descuento_agrupado = Decimal(
            str(linea_agrupada["descuento_porcentaje"])
        )
        self.assertGreater(descuento_separado, Decimal("0"))
        self.assertEqual(
            descuento_separado,
            descuento_agrupado,
        )

    def test_curva_kits_x2_x4_x6_es_uniforme_de_1_a_10_y_segura(self):
        """
        Prueba comercial integral:
        - x2, x4 y x6 comparten curva por cantidad total de kits.
        - distintas selecciones baratas/caras no cambian el porcentaje.
        - un único kit llevado a qty=N coincide con N kits separados.
        - las combinaciones de este escenario de estrés conservan el margen
          mínimo técnico.
        """
        productos = [self.producto]
        for indice, peso in enumerate(("30", "60", "140", "200", "250"), start=1):
            productos.append(
                Producto.objects.create(
                    nombre=f"Sensorial estrés {indice}",
                    categoria="PRODUCTO",
                    tipo=self.tipo,
                    peso_gramos=Decimal(peso),
                    margen_ganancia=Decimal("50"),
                    activo=True,
                    solo_produccion=False,
                )
            )

        kits = {}
        for cantidad, precio in ((2, "12000"), (4, "19000"), (6, "25000")):
            kits[cantidad] = Kit.objects.create(
                nombre=f"Kit sensorial x{cantidad} estrés",
                modalidad="LIBRE_CATEGORIA",
                tipo_producto=self.tipo,
                cantidad_productos=cantidad,
                precio=Decimal(precio),
                proteger_rentabilidad_libre=False,
                activo=True,
            )

        selecciones = {
            2: [
                [productos[0], productos[5]],
                [productos[1], productos[4]],
            ],
            4: [
                [productos[0], productos[1], productos[4], productos[5]],
                [productos[1], productos[2], productos[3], productos[5]],
            ],
            6: [
                productos[:6],
                [productos[5], productos[4], productos[3], productos[2], productos[1], productos[0]],
            ],
        }

        esperados = {
            1: Decimal("0.0"),
            2: Decimal("3.8"),
            3: Decimal("6.0"),
            4: Decimal("7.5"),
            5: Decimal("8.6"),
            6: Decimal("9.4"),
            7: Decimal("10.0"),
            8: Decimal("10.5"),
            9: Decimal("10.9"),
            # Decimal.quantize usa ROUND_HALF_EVEN por defecto: 11.25 -> 11.2.
            10: Decimal("11.2"),
        }

        resumen_impreso = []

        for total_kits in range(1, 11):
            # Escenario A: una configuración de x6 aumentada a qty=N.
            seleccion_agrupada = selecciones[6][0]
            agrupado = self.client.post(
                reverse("catalogo_carrito_precios"),
                data=json.dumps(
                    [
                        {
                            "key": f"agrupado-x6-{total_kits}",
                            "kind": "kit",
                            "id": kits[6].id,
                            "qty": total_kits,
                            "selections": [
                                {"id": producto.id}
                                for producto in seleccion_agrupada
                            ],
                        }
                    ]
                ),
                content_type="application/json",
            )
            self.assertEqual(agrupado.status_code, 200)
            linea_agrupada = agrupado.json()["lineas"][0]
            descuento_agrupado = Decimal(
                str(linea_agrupada["descuento_porcentaje"])
            )

            # Escenario B: N kits separados, alternando x2/x4/x6 y usando
            # selecciones de costos muy diferentes.
            payload_mixto = []
            costo_mixto = Decimal("0")
            for indice in range(total_kits):
                cantidad_kit = (2, 4, 6)[indice % 3]
                seleccion = selecciones[cantidad_kit][indice % 2]
                payload_mixto.append(
                    {
                        "key": f"mixto-{total_kits}-{indice}",
                        "kind": "kit",
                        "id": kits[cantidad_kit].id,
                        "qty": 1,
                        "selections": [
                            {"id": producto.id}
                            for producto in seleccion
                        ],
                    }
                )
                for producto in seleccion:
                    costo_mixto += Decimal(
                        str(
                            calcular_costo_productivo_producto(
                                producto,
                                cantidad=1,
                                forzar_filamento_economico=True,
                            )["costo_productivo"]
                        )
                    )

            mixto = self.client.post(
                reverse("catalogo_carrito_precios"),
                data=json.dumps(payload_mixto),
                content_type="application/json",
            )
            self.assertEqual(mixto.status_code, 200)
            datos_mixtos = mixto.json()
            descuentos_mixtos = {
                Decimal(str(linea["descuento_porcentaje"]))
                for linea in datos_mixtos["lineas"]
            }

            esperado = esperados[total_kits]
            self.assertEqual(descuento_agrupado, esperado)
            self.assertEqual(descuentos_mixtos, {esperado})

            precio_final_mixto = Decimal(
                str(datos_mixtos["precio_final_total"])
            )
            margen_mixto = (
                (
                    precio_final_mixto - costo_mixto
                )
                / precio_final_mixto
                * Decimal("100")
                if precio_final_mixto > 0
                else Decimal("0")
            ).quantize(Decimal("0.1"))

            self.assertGreaterEqual(
                margen_mixto,
                MARGEN_MINIMO,
                msg=(
                    f"Con {total_kits} kits el margen de estrés cayó a "
                    f"{margen_mixto}%."
                ),
            )

            resumen_impreso.append(
                (
                    total_kits,
                    esperado,
                    margen_mixto,
                    len(datos_mixtos["lineas"]),
                )
            )

        print("DV_KIT_CURVE_STRESS_BEGIN")
        for cantidad, descuento, margen, lineas in resumen_impreso:
            print(
                "DV_KIT_CURVE_STRESS "
                f"kits={cantidad} descuento={descuento}% "
                f"margen_mixto={margen}% lineas={lineas}"
            )
        print("DV_KIT_CURVE_STRESS_END")

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

    def test_checkout_acepta_mas_de_cien_unidades_y_marca_volumen_alto(self):
        productos = [self.producto]
        for indice in range(2):
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
                "qty": 50,
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
        self.assertTrue(precios.json()["ok"])
        self.assertGreater(precios.json()["ahorro"], 0)

        checkout = self._post(
            payload,
            telefono="+54 11 5555 3030",
        )
        self.assertEqual(checkout.status_code, 302)
        self.assertEqual(SolicitudWeb.objects.count(), 1)

        solicitud = SolicitudWeb.objects.get()
        self.assertEqual(solicitud.total_unidades, 150)
        self.assertTrue(solicitud.es_volumen_alto)

    def test_checkout_incluye_aviso_de_volumen_no_bloqueante(self):
        response = self.client.get(reverse("catalogo_carrito"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-limit-modal")
        self.assertContains(response, "hidden")
        self.assertContains(response, "Compra de volumen alto")
        self.assertContains(response, "CONTINUAR CON SOLICITUD")
        self.assertContains(response, "data-limit-edit-cart")

    def test_cantidad_maxima_por_linea_es_50(self):
        aceptada = self._post(
            [
                {
                    "kind": "product",
                    "id": self.producto.id,
                    "qty": 50,
                }
            ],
            telefono="+54 11 5555 3131",
        )
        self.assertEqual(aceptada.status_code, 302)
        self.assertEqual(SolicitudWeb.objects.count(), 1)

        rechazada = self._post(
            [
                {
                    "kind": "product",
                    "id": self.producto.id,
                    "qty": 51,
                }
            ],
            telefono="+54 11 5555 3232",
        )
        self.assertEqual(rechazada.status_code, 200)
        self.assertContains(rechazada, "entre 1 y 50 unidades")
        self.assertEqual(SolicitudWeb.objects.count(), 1)

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

