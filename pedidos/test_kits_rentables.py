from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from costos.models import ConfiguracionCostos
from kits.models import Kit
from productos.models import Producto, TipoProducto

from .models import Pedido


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
class PedidosKitsRentablesTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="tester-kits-rentables",
            password="test",
        )
        self.client.force_login(usuario)

        ConfiguracionCostos.objects.create(
            nombre="Costos pedido rentable",
            coste_plastico_kg=Decimal("10000"),
            coste_plastico_kg_cantidad=Decimal("10000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date.today(),
            activa=True,
        )

        self.tipo = TipoProducto.objects.create(
            nombre="Sensorial pedido rentable",
            activo=True,
        )
        self.rentable = Producto.objects.create(
            nombre="Rentable pedido",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("300"),
            requiere_impresion=True,
            activo=True,
            solo_produccion=False,
        )
        self.caro = Producto.objects.create(
            nombre="Caro pedido",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("500"),
            requiere_impresion=True,
            activo=True,
            solo_produccion=False,
        )
        self.kit = Kit.objects.create(
            nombre="Kit pedido 2x9000",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("9000"),
            activo=True,
        )
        self.cliente = Cliente.objects.create(
            nombre="Cliente prueba",
            activo=True,
        )

    def test_api_de_pedido_devuelve_solo_productos_rentables(self):
        response = self.client.get(
            reverse(
                "pedidos:productos_kit",
                args=[self.kit.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        ids = {
            producto["id"]
            for producto in response.json()["productos"]
        }
        self.assertIn(self.rentable.id, ids)
        self.assertNotIn(self.caro.id, ids)

    def test_api_puede_mostrar_seleccion_historica_fuera_de_margen(self):
        response = self.client.get(
            reverse(
                "pedidos:productos_kit",
                args=[self.kit.id],
            ),
            {"seleccionado": [self.caro.id]},
        )

        self.assertEqual(response.status_code, 200)
        productos = {
            producto["id"]: producto
            for producto in response.json()["productos"]
        }
        self.assertIn(self.caro.id, productos)
        self.assertFalse(productos[self.caro.id]["elegible"])

    def test_nuevo_pedido_rechaza_producto_fuera_de_margen(self):
        response = self.client.post(
            reverse("pedidos:nuevo"),
            {
                "cliente": str(self.cliente.id),
                "item_indice": ["1"],
                "tipo_item_1": "KIT",
                "cantidad_1": "1",
                "kit_1": str(self.kit.id),
                "productos_kit_1": [
                    str(self.rentable.id),
                    str(self.caro.id),
                ],
            },
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Pedido.objects.count(), 0)
        self.assertContains(
            response,
            "ya no es una opción rentable",
        )

    def test_formulario_de_kit_muestra_panel_de_opciones_habilitadas(self):
        response = self.client.get(
            reverse(
                "kits:editar",
                args=[self.kit.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "PRODUCTOS HABILITADOS PARA ESTE KIT",
        )
        self.assertContains(
            response,
            "actualizarOpcionesRentables",
        )
