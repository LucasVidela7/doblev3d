import os
from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from kits.models import Kit
from productos.image_models import ProductoImagen
from productos.models import Producto, TipoProducto

from .models import DetalleKitProducto, DetallePedido, Pedido


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


    @patch.dict(os.environ, {"APP_ENV": "qa"}, clear=False)
    def test_pedido_publico_muestra_fotos_producto_y_kit_en_grilla(self):
        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="qa",
            file_id="pedido-publico-producto-1",
            url="https://ik.imagekit.io/demo/pedido-producto-1.jpg",
            thumbnail_url="",
            orden=1,
        )
        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="qa",
            file_id="pedido-publico-producto-2",
            url="https://ik.imagekit.io/demo/pedido-producto-2.jpg",
            thumbnail_url="",
            orden=2,
        )
        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="production",
            file_id="pedido-publico-producto-prod",
            url="https://ik.imagekit.io/demo/pedido-producto-prod.jpg",
            thumbnail_url="",
            orden=1,
        )

        productos_kit = []
        for indice in range(1, 5):
            producto = Producto.objects.create(
                nombre=f"Producto kit {indice}",
                categoria="PRODUCTO",
                tipo=self.producto.tipo,
                activo=True,
                requiere_impresion=False,
            )
            ProductoImagen.objects.create(
                producto=producto,
                ambiente="qa",
                file_id=f"pedido-publico-kit-{indice}",
                url=f"https://ik.imagekit.io/demo/pedido-kit-{indice}.jpg",
                thumbnail_url="",
                orden=1,
            )
            productos_kit.append(producto)

        kit = Kit.objects.create(
            nombre="Kit visual público",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.producto.tipo,
            cantidad_productos=4,
            precio=Decimal("20000"),
            activo=True,
        )
        detalle_kit = DetallePedido.objects.create(
            pedido=self.pedido,
            tipo_item="KIT",
            kit=kit,
            cantidad=1,
            precio_unitario=Decimal("20000"),
        )
        for producto in productos_kit:
            DetalleKitProducto.objects.create(
                detalle=detalle_kit,
                producto=producto,
                cantidad=1,
            )

        respuesta = self.client.get(
            reverse(
                "pedido_publico",
                args=[self.pedido.public_token],
            )
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'class="item-gallery"', count=2)
        self.assertContains(
            respuesta,
            "https://ik.imagekit.io/demo/pedido-producto-1.jpg",
        )
        self.assertContains(
            respuesta,
            "https://ik.imagekit.io/demo/pedido-producto-2.jpg",
        )
        self.assertNotContains(
            respuesta,
            "https://ik.imagekit.io/demo/pedido-producto-prod.jpg",
        )
        for indice in range(1, 5):
            self.assertContains(
                respuesta,
                f"https://ik.imagekit.io/demo/pedido-kit-{indice}.jpg",
            )
