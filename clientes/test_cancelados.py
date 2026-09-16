from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from pedidos.models import DetallePedido, Pedido

from .models import Cliente


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
class HistorialCanceladosClienteTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="cliente-cancelados-tests",
            password="test-pass-seguro",
        )
        self.client.force_login(usuario)

        self.cliente = Cliente.objects.create(
            nombre="Cliente con historial",
            activo=True,
        )

        self.pedido_activo = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        DetallePedido.objects.create(
            pedido=self.pedido_activo,
            tipo_item="PERSONALIZADO",
            cantidad=1,
            precio_unitario=Decimal("2500"),
            precio_total_personalizado=Decimal("2500"),
            detalle_personalizacion="Pedido vigente",
        )

        self.pedido_cancelado = Pedido.objects.create(
            cliente=self.cliente,
            estado="CANCELADO",
        )
        DetallePedido.objects.create(
            pedido=self.pedido_cancelado,
            tipo_item="PERSONALIZADO",
            cantidad=1,
            precio_unitario=Decimal("9000"),
            precio_total_personalizado=Decimal("9000"),
            estado="CANCELADO",
            detalle_personalizacion="Detalle cancelado visible",
        )

        self.url = reverse(
            "clientes:detalle",
            args=[self.cliente.id],
        )

    def test_cancelado_permanece_visible_en_historial(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.pedido_cancelado.codigo)
        self.assertContains(respuesta, "CANCELADO")
        self.assertContains(respuesta, "Detalle cancelado visible")

    def test_cancelado_no_suma_compras_ni_saldo_activo(self):
        respuesta = self.client.get(self.url)

        self.assertEqual(
            respuesta.context["total_comprado"],
            Decimal("2500"),
        )
        self.assertEqual(
            respuesta.context["saldo_pendiente"],
            Decimal("2500"),
        )
        self.assertEqual(
            respuesta.context["cantidad_pedidos"],
            2,
        )
        self.assertEqual(
            respuesta.context["cantidad_cancelados"],
            1,
        )

    def test_cancelado_no_habilita_acciones_operativas(self):
        respuesta = self.client.get(self.url)
        contenido = respuesta.content.decode("utf-8")
        bloque_cancelado = contenido.split(
            self.pedido_cancelado.codigo,
            1,
        )[1].split("</article>", 1)[0]

        self.assertNotIn("EDITAR PEDIDO", bloque_cancelado)
        self.assertNotIn("CANCELAR PEDIDO", bloque_cancelado)
        self.assertNotIn("ELIMINAR PEDIDO", bloque_cancelado)
        self.assertNotIn("REGISTRAR PAGO", bloque_cancelado)

    def test_eliminado_no_aparece_en_historial(self):
        pedido_eliminado = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        codigo_eliminado = pedido_eliminado.codigo
        pedido_eliminado.delete()

        respuesta = self.client.get(self.url)

        self.assertNotContains(respuesta, codigo_eliminado)
