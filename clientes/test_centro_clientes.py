from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from pedidos.models import DetallePedido, Pedido, Presupuesto
from productos.models import Producto, TipoProducto

from .models import Cliente


class CentroClientesTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="centro-clientes",
            password="test12345",
        )
        self.client.force_login(usuario)

        tipo = TipoProducto.objects.create(
            nombre="Sensorial",
        )
        producto = Producto.objects.create(
            nombre="Producto prueba",
            categoria="PRODUCTO",
            tipo=tipo,
            requiere_impresion=False,
            activo=True,
        )
        self.cliente_obj = Cliente.objects.create(
            nombre="María González",
            telefono="11 4444 4444",
            email="maria@example.com",
        )
        pedido = Pedido.objects.create(
            cliente=self.cliente_obj,
            estado="PENDIENTE",
        )
        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PRODUCTO",
            producto=producto,
            cantidad=2,
            precio_unitario=Decimal("5000"),
            estado="PENDIENTE",
        )
        Presupuesto.objects.create(
            cliente=self.cliente_obj,
            estado="PENDIENTE",
        )

    def test_lista_muestra_metricas_operativas(self):
        respuesta = self.client.get(
            reverse("clientes:lista"),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "NECESITAN ATENCIÓN")
        self.assertContains(respuesta, "CON PEDIDOS ACTIVOS")
        self.assertContains(respuesta, "CON PRESUPUESTOS")
        self.assertContains(respuesta, "María González")
        self.assertEqual(
            respuesta.context["metricas"]["con_pedidos"],
            1,
        )
        self.assertEqual(
            respuesta.context["metricas"]["con_presupuestos"],
            1,
        )

    def test_filtro_presupuestos(self):
        respuesta = self.client.get(
            reverse("clientes:lista"),
            {"estado": "presupuestos"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(len(respuesta.context["filas"]), 1)

    def test_detalle_es_vision_360(self):
        respuesta = self.client.get(
            reverse(
                "clientes:detalle",
                args=[self.cliente_obj.id],
            )
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "AHORA")
        self.assertContains(respuesta, "CUENTA CORRIENTE")
        self.assertContains(respuesta, "ACTIVIDAD RECIENTE")
        self.assertContains(
            respuesta,
            "REPETIR COMO PRESUPUESTO",
        )
