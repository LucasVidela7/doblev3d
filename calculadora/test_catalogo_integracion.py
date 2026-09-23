from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from calculadora.precios import calcular_precio_catalogo_producto
from clientes.models import Cliente
from costos.models import ConfiguracionCostos
from kits.models import Kit, KitComponente
from pedidos.kits_volumen import calcular_precio_volumen_kits
from pedidos.models import DetallePresupuesto, Presupuesto
from productos.models import Producto, TipoProducto


TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STORAGES=TEST_STORAGES,
)
class CalculadoraCatalogoIntegracionTests(TestCase):
    def setUp(self):
        ConfiguracionCostos.objects.create(
            nombre="Costos calculadora integrada",
            coste_plastico_kg=Decimal("20000"),
            coste_plastico_kg_cantidad=Decimal("14000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        self.tipo = TipoProducto.objects.create(
            nombre="Tipo calculadora integrada",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Producto calculadora integrada",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=30,
            peso_gramos=Decimal("100"),
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            personalizable=True,
            stock=10,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=False,
        )
        self.kit = Kit.objects.create(
            nombre="Kit calculadora integrada",
            modalidad="FIJO",
            cantidad_productos=2,
            precio=Decimal("13000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=self.kit,
            producto=self.producto,
            cantidad=2,
        )
        self.cliente = Cliente.objects.create(
            nombre="Cliente calculadora integrada",
            telefono="1155552222",
            activo=True,
        )
        self.usuario = get_user_model().objects.create_user(
            username="calc-integrada",
            password="test-pass-seguro",
        )
        self.client.force_login(self.usuario)

    def test_api_producto_expone_el_mismo_precio_del_catalogo(self):
        esperado = calcular_precio_catalogo_producto(
            self.producto,
            5,
        )

        respuesta = self.client.get(
            reverse("pedidos:precio_producto"),
            {
                "producto_id": self.producto.id,
                "cantidad": 5,
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertTrue(datos["ok"])
        self.assertIn("catalogo", datos)
        self.assertEqual(
            Decimal(str(datos["catalogo"]["precio_unitario"])),
            esperado["precio_unitario"],
        )
        self.assertEqual(
            Decimal(str(datos["catalogo"]["precio_final_total"])),
            esperado["precio_final_total"],
        )
        self.assertEqual(
            Decimal(str(datos["catalogo"]["descuento_porcentaje"])),
            esperado["descuento_porcentaje"],
        )

    def test_calculadora_kit_usa_el_mismo_motor_de_volumen(self):
        respuesta = self.client.post(
            reverse("calculadora:precios"),
            {
                "modo": "kit",
                "kit_id": str(self.kit.id),
                "cantidad": "2",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        resultado = respuesta.context["resultado_kit"]
        self.assertIsNotNone(resultado)

        directo = calcular_precio_volumen_kits(
            [
                {
                    "key": "test",
                    "kit": self.kit,
                    "cantidad": 2,
                    "precio_unitario_lista": self.kit.precio,
                    "componentes": [
                        {
                            "producto": self.producto,
                            "cantidad": 4,
                        }
                    ],
                }
            ]
        )

        self.assertEqual(
            resultado["precio_final_total"],
            directo["precio_final_total"],
        )
        self.assertEqual(
            resultado["descuento_porcentaje"],
            directo["descuento_porcentaje"],
        )

    def test_calculadora_personalizado_toma_base_exacta_del_catalogo(self):
        esperado = calcular_precio_catalogo_producto(
            self.producto,
            5,
        )

        respuesta = self.client.post(
            reverse("calculadora:precios"),
            {
                "modo": "personalizado",
                "producto_personalizado_id": str(self.producto.id),
                "cantidad": "5",
                "precio_total_personalizado": "30000",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        resultado = respuesta.context["resultado_personalizado"]
        self.assertIsNotNone(resultado)
        self.assertEqual(
            resultado["base"]["precio_final_total"],
            esperado["precio_final_total"],
        )

    def test_calculadora_producto_acepta_cantidad_mayor_a_20(self):
        respuesta = self.client.post(
            reverse("calculadora:precios"),
            {
                "modo": "existente",
                "producto_id": str(self.producto.id),
                "cantidad": "100",
                "cantidades_lista": "20,50,100",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        resultado = respuesta.context["resultado_existente"]
        self.assertIsNotNone(resultado)
        self.assertEqual(resultado["cantidad"], 100)
        self.assertEqual(
            [fila["cantidad"] for fila in resultado["lista_precios"]],
            [20, 50, 100],
        )
        self.assertNotContains(
            respuesta,
            'max="20"',
        )

    def test_calculadora_kit_y_personalizado_aceptan_mas_de_20(self):
        kit = self.client.post(
            reverse("calculadora:precios"),
            {
                "modo": "kit",
                "kit_id": str(self.kit.id),
                "cantidad": "75",
            },
        )
        self.assertEqual(kit.status_code, 200)
        self.assertEqual(
            kit.context["resultado_kit"]["cantidad"],
            75,
        )

        personalizado = self.client.post(
            reverse("calculadora:precios"),
            {
                "modo": "personalizado",
                "producto_personalizado_id": str(self.producto.id),
                "cantidad": "120",
                "precio_total_personalizado": "500000",
            },
        )
        self.assertEqual(personalizado.status_code, 200)
        self.assertEqual(
            personalizado.context["resultado_personalizado"]["cantidad"],
            120,
        )

    def test_modo_actual_es_visible_y_activo_en_tema_oscuro(self):
        respuesta = self.client.get(
            reverse("calculadora:precios"),
            {"modo": "kit"},
        )

        self.assertEqual(respuesta.status_code, 200)
        contenido = respuesta.content.decode()
        self.assertIn(
            'class="mode-current"',
            contenido,
        )
        self.assertIn(
            'class="tab active">KIT</a>',
            contenido,
        )
        self.assertIn(
            'html[data-dv-theme="dark"] body .tabs .tab.active',
            contenido,
        )
        self.assertIn(
            'color:var(--dv-on-blue,#fff)!important',
            contenido,
        )

    def test_presupuesto_producto_automatico_guarda_precio_catalogo(self):
        esperado = calcular_precio_catalogo_producto(
            self.producto,
            5,
        )

        respuesta = self.client.post(
            reverse("pedidos:nuevo"),
            {
                "cliente": str(self.cliente.id),
                "fecha_entrega": "",
                "observaciones": "",
                "item_indice": ["1"],
                "tipo_item_1": "PRODUCTO",
                "producto_1": str(self.producto.id),
                "cantidad_1": "5",
                "precio_producto_manual_1": "0",
                "precio_unitario_1": "",
                "precio_total_producto_1": "",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        detalle = DetallePresupuesto.objects.get(
            presupuesto=Presupuesto.objects.get(),
        )
        self.assertEqual(
            detalle.precio_unitario,
            esperado["precio_unitario"],
        )

    def test_presupuesto_producto_manual_conserva_precio_acordado(self):
        respuesta = self.client.post(
            reverse("pedidos:nuevo"),
            {
                "cliente": str(self.cliente.id),
                "fecha_entrega": "",
                "observaciones": "",
                "item_indice": ["1"],
                "tipo_item_1": "PRODUCTO",
                "producto_1": str(self.producto.id),
                "cantidad_1": "5",
                "precio_producto_manual_1": "1",
                "precio_unitario_1": "",
                "precio_total_producto_1": "12500",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        detalle = DetallePresupuesto.objects.get(
            presupuesto=Presupuesto.objects.get(),
        )
        self.assertEqual(
            detalle.precio_unitario,
            Decimal("2500.00"),
        )
