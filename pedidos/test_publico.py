from decimal import Decimal
from uuid import uuid4

from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from productos.models import Producto, TipoProducto

from .models import DetallePedido, Pedido


@override_settings(SECURE_SSL_REDIRECT=False)
class PedidoPublicoTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombre="Cliente Público",
            telefono="+54 9 11 5555 1111",
            email="privado@example.com",
            activo=True,
        )
        tipo = TipoProducto.objects.create(
            nombre="Público",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Pepino sensorial público",
            categoria="PRODUCTO",
            tipo=tipo,
            activo=True,
            requiere_impresion=False,
        )
        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PREPARANDO",
        )
        DetallePedido.objects.create(
            pedido=self.pedido,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=2,
            precio_unitario=Decimal("5000"),
        )

    def test_pedido_publico_es_accesible_por_token_sin_login(self):
        self.client.logout()
        respuesta = self.client.get(
            reverse(
                "pedido_publico",
                args=[self.pedido.public_token],
            )
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.pedido.codigo)
        self.assertContains(respuesta, "Pepino sensorial público")
        self.assertContains(respuesta, "SALDO PENDIENTE")
        self.assertContains(respuesta, "10.000")
        self.assertNotContains(respuesta, self.cliente.telefono)
        self.assertNotContains(respuesta, self.cliente.email)

    def test_token_inexistente_no_expone_pedido(self):
        self.client.logout()
        respuesta = self.client.get(
            reverse(
                "pedido_publico",
                args=[uuid4()],
            )
        )
        self.assertEqual(respuesta.status_code, 404)
