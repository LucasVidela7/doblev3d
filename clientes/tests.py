from django.test import TestCase
from django.urls import reverse

from pedidos.models import Pedido

from .models import Cliente


class DetalleClienteAccionesPedidoTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombre="Cliente historial",
            activo=True,
        )
        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        self.url = reverse(
            "clientes:detalle",
            args=[self.cliente.id],
        )

    def test_pendiente_muestra_editar_cancelar_y_eliminar(self):
        respuesta = self.client.get(self.url)

        self.assertContains(respuesta, "EDITAR PEDIDO")
        self.assertContains(respuesta, "CANCELAR PEDIDO")
        self.assertContains(respuesta, "ELIMINAR PEDIDO")
        self.assertNotContains(respuesta, "ENTREGAR PEDIDO")

    def test_listo_muestra_entregar_y_oculta_edicion(self):
        self.pedido.estado = "LISTO"
        self.pedido.save(update_fields=["estado"])

        respuesta = self.client.get(self.url)

        self.assertContains(respuesta, "ENTREGAR PEDIDO")
        self.assertNotContains(respuesta, "EDITAR PEDIDO")
        self.assertNotContains(respuesta, "CANCELAR PEDIDO")
        self.assertNotContains(respuesta, "ELIMINAR PEDIDO")

    def test_preparando_no_permite_acciones_de_modificacion(self):
        self.pedido.estado = "PREPARANDO"
        self.pedido.save(update_fields=["estado"])

        respuesta = self.client.get(self.url)

        self.assertNotContains(respuesta, "EDITAR PEDIDO")
        self.assertNotContains(respuesta, "CANCELAR PEDIDO")
        self.assertNotContains(respuesta, "ELIMINAR PEDIDO")
        self.assertNotContains(respuesta, "ENTREGAR PEDIDO")
