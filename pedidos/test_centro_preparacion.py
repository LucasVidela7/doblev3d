from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from productos.models import Producto, TipoProducto

from .models import DetallePedido, EstadoImpresionPedido, Pedido


class CentroPreparacionTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="preparacion-test",
            password="ClaveSegura-12345",
        )
        self.client.force_login(usuario)

        self.cliente = Cliente.objects.create(
            nombre="Cliente preparación",
            activo=True,
        )
        tipo = TipoProducto.objects.create(
            nombre="Tipo preparación",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Cubo preparación",
            categoria="PRODUCTO",
            tipo=tipo,
            requiere_impresion=True,
            stock=10,
            activo=True,
        )
        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        DetallePedido.objects.create(
            pedido=self.pedido,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=4,
            precio_unitario=Decimal("1000"),
            estado="PENDIENTE",
        )

    def test_pedido_con_stock_aparece_para_preparar(self):
        respuesta = self.client.get(
            reverse("pedidos:impresiones")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Para preparar")
        self.assertContains(respuesta, self.pedido.codigo)
        self.assertContains(respuesta, "TODO DISPONIBLE")
        self.assertEqual(
            respuesta.context["total_para_preparar"],
            1,
        )

    def test_iniciar_preparacion_reserva_stock(self):
        respuesta = self.client.post(
            reverse(
                "pedidos:iniciar_preparacion",
                args=[self.pedido.id],
            )
        )

        self.assertEqual(respuesta.status_code, 302)

        self.producto.refresh_from_db()
        self.pedido.refresh_from_db()
        estado = EstadoImpresionPedido.objects.get(
            pedido=self.pedido,
            producto=self.producto,
        )

        self.assertEqual(self.producto.stock, 6)
        self.assertEqual(self.pedido.estado, "PREPARANDO")
        self.assertTrue(estado.reservado_stock)
        self.assertEqual(estado.cantidad_stock_reservada, 4)
        self.assertFalse(estado.listo)

    def test_reserva_evitar_doble_uso_de_stock(self):
        otro = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        DetallePedido.objects.create(
            pedido=otro,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=7,
            precio_unitario=Decimal("1000"),
            estado="PENDIENTE",
        )

        self.client.post(
            reverse(
                "pedidos:iniciar_preparacion",
                args=[self.pedido.id],
            )
        )

        respuesta = self.client.get(
            reverse("pedidos:impresiones")
        )

        self.assertEqual(
            respuesta.context["total_en_preparacion"],
            1,
        )
        self.assertEqual(
            respuesta.context["total_falta_stock"],
            1,
        )

    def test_marcar_listo_consumiendo_reserva_no_descuenta_dos_veces(self):
        self.client.post(
            reverse(
                "pedidos:iniciar_preparacion",
                args=[self.pedido.id],
            )
        )
        estado = EstadoImpresionPedido.objects.get(
            pedido=self.pedido,
            producto=self.producto,
        )

        self.client.post(
            reverse("pedidos:cambiar_listo"),
            {
                "estado_id": estado.id,
                "listo": "1",
            },
        )

        self.producto.refresh_from_db()
        self.pedido.refresh_from_db()
        estado.refresh_from_db()

        self.assertEqual(self.producto.stock, 6)
        self.assertTrue(estado.listo)
        self.assertTrue(estado.stock_descontado)
        self.assertEqual(estado.cantidad_stock_descontada, 4)
        self.assertFalse(estado.reservado_stock)
        self.assertEqual(estado.cantidad_stock_reservada, 0)
        self.assertEqual(self.pedido.estado, "LISTO")

    def test_liberar_preparacion_devuelve_stock(self):
        self.client.post(
            reverse(
                "pedidos:iniciar_preparacion",
                args=[self.pedido.id],
            )
        )

        respuesta = self.client.post(
            reverse(
                "pedidos:liberar_preparacion",
                args=[self.pedido.id],
            )
        )

        self.assertEqual(respuesta.status_code, 302)
        self.producto.refresh_from_db()
        self.pedido.refresh_from_db()
        estado = EstadoImpresionPedido.objects.get(
            pedido=self.pedido,
            producto=self.producto,
        )

        self.assertEqual(self.producto.stock, 10)
        self.assertFalse(estado.reservado_stock)
        self.assertEqual(estado.cantidad_stock_reservada, 0)
        self.assertEqual(self.pedido.estado, "PENDIENTE")

    def test_cancelar_pedido_devuelve_stock_reservado(self):
        self.client.post(
            reverse(
                "pedidos:iniciar_preparacion",
                args=[self.pedido.id],
            )
        )

        self.client.post(
            reverse(
                "pedidos:cancelar",
                args=[self.pedido.id],
            )
        )

        self.producto.refresh_from_db()
        self.pedido.refresh_from_db()

        self.assertEqual(self.producto.stock, 10)
        self.assertEqual(self.pedido.estado, "CANCELADO")
