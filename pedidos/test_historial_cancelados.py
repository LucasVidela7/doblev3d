from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente

from .models import DetallePedido, Pedido


# Esta suite cubre en QA la diferencia funcional entre cancelar (historial)
# y eliminar (borrado definitivo) en las vistas donde se listan pedidos.
# La ejecución de Railway reutiliza su base temporal para evitar residuos de
# una corrida previa interrumpida; nunca usa la base de datos real de QA.
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
class HistorialCanceladosPedidosTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="pedidos-cancelados-tests",
            password="test-pass-seguro",
        )
        self.client.force_login(usuario)

        self.cliente = Cliente.objects.create(
            nombre="Cliente pedidos cancelados",
            activo=True,
        )

        self.activo = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        DetallePedido.objects.create(
            pedido=self.activo,
            tipo_item="PERSONALIZADO",
            cantidad=1,
            precio_unitario=Decimal("3000"),
            precio_total_personalizado=Decimal("3000"),
            detalle_personalizacion="Activo",
        )

        self.cancelado = Pedido.objects.create(
            cliente=self.cliente,
            estado="CANCELADO",
        )
        DetallePedido.objects.create(
            pedido=self.cancelado,
            tipo_item="PERSONALIZADO",
            cantidad=1,
            precio_unitario=Decimal("8000"),
            precio_total_personalizado=Decimal("8000"),
            estado="CANCELADO",
            detalle_personalizacion="Cancelado histórico",
        )

    def test_filtro_cancelados_muestra_solo_historial_cancelado(self):
        respuesta = self.client.get(reverse("pedidos:cancelados"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.cancelado.codigo)
        self.assertContains(respuesta, "Cancelado histórico")
        self.assertNotContains(respuesta, self.activo.codigo)
        self.assertContains(respuesta, "CANCELADO")

    def test_historial_cancelado_es_solo_lectura(self):
        respuesta = self.client.get(reverse("pedidos:cancelados"))

        self.assertNotContains(respuesta, "+ PAGO")
        self.assertNotContains(respuesta, "Editar pedido")
        self.assertNotContains(respuesta, "Cancelar pedido")
        self.assertNotContains(respuesta, "Eliminar pedido")

    def test_ruta_pagos_redirige_a_finanzas_cobros(self):
        respuesta = self.client.get(
            reverse("pedidos:pagos")
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            respuesta.url,
            f"{reverse('pedidos:finanzas')}#cobros",
        )

    def test_finanzas_muestra_solo_saldo_vigente(self):
        respuesta = self.client.get(
            reverse("pedidos:finanzas")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, self.activo.codigo)
        self.assertNotContains(respuesta, self.cancelado.codigo)
        self.assertEqual(
            respuesta.context["saldo_total_actual"],
            Decimal("3000"),
        )
        self.assertEqual(
            respuesta.context["pedidos_con_saldo_actual"],
            1,
        )

    def test_eliminado_no_aparece_en_listados(self):
        eliminado = Pedido.objects.create(
            cliente=self.cliente,
            estado="CANCELADO",
        )
        codigo = eliminado.codigo
        eliminado.delete()

        historial = self.client.get(reverse("pedidos:cancelados"))
        finanzas = self.client.get(reverse("pedidos:finanzas"))

        self.assertNotContains(historial, codigo)
        self.assertNotContains(finanzas, codigo)
