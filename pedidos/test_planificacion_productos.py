from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from kits.models import Kit
from produccion.models import Produccion
from productos.models import Producto, TipoProducto

from .impresiones_compuestas import obtener_impresiones_por_producto
from .models import DetallePedido, Pedido


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
class PlanificacionDesdeImpresionesTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="tester",
            password="test12345",
        )
        self.client.force_login(usuario)

        self.tipo = TipoProducto.objects.create(
            nombre="Sensorial",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Producto estándar",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=1,
            minutos=0,
            peso_gramos=Decimal("20"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            personalizable=True,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=False,
        )
        self.cliente = Cliente.objects.create(
            nombre="Cliente test",
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
            cantidad=5,
            precio_unitario=Decimal("1000"),
            estado="PENDIENTE",
        )

    def _inicio_futuro(self):
        return (
            timezone.localtime(timezone.now() + timedelta(hours=2))
            .strftime("%Y-%m-%dT%H:%M")
        )

    def test_planificar_cantidad_libre_descuenta_falta_iniciar(self):
        respuesta = self.client.post(
            reverse("pedidos:planificar_impresion_producto"),
            {
                "producto": self.producto.id,
                "cantidad": "2",
                "inicio_impresion": self._inicio_futuro(),
                "horas": "1",
                "minutos": "30",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        produccion = Produccion.objects.get()
        self.assertEqual(produccion.estado, "PENDIENTE")
        self.assertEqual(produccion.destino, "STOCK")
        self.assertEqual(produccion.cantidad, 2)
        self.assertIsNone(produccion.impresora)
        self.assertEqual(produccion.tiempo_impresion_minutos, 90)

        item = next(
            actual
            for actual in obtener_impresiones_por_producto()
            if actual["producto"].id == self.producto.id
        )
        self.assertEqual(item["planificadas"], 2)
        self.assertEqual(item["falta_normal_planificar"], 3)
        self.assertEqual(item["falta_iniciar"], 3)

    def test_personalizado_se_planifica_separado_y_con_referencia(self):
        personalizado = DetallePedido.objects.create(
            pedido=self.pedido,
            tipo_item="PERSONALIZADO",
            producto=self.producto,
            cantidad=2,
            precio_unitario=Decimal("1200"),
            precio_total_personalizado=Decimal("2400"),
            estado="PENDIENTE",
            personalizado=True,
            detalle_personalizacion="Agregar nombre LUCAS",
            color_personalizacion="Azul",
        )

        respuesta = self.client.post(
            reverse("pedidos:planificar_impresion_producto"),
            {
                "producto": self.producto.id,
                "personalizado_id": personalizado.id,
                "cantidad": "1",
                "inicio_impresion": self._inicio_futuro(),
                "horas": "1",
                "minutos": "0",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        produccion = Produccion.objects.get()
        self.assertEqual(produccion.destino, "PEDIDO")
        self.assertEqual(produccion.pedido, self.pedido)
        self.assertIn(
            f"PERSONALIZADO:{personalizado.id}",
            produccion.observaciones,
        )
        self.assertIn("Agregar nombre LUCAS", produccion.observaciones)
        self.assertIn("Azul", produccion.observaciones)

    def test_permite_planificar_mas_que_la_necesidad_estandar_para_stock(self):
        respuesta = self.client.post(
            reverse("pedidos:planificar_impresion_producto"),
            {
                "producto": self.producto.id,
                "cantidad": "6",
                "inicio_impresion": self._inicio_futuro(),
                "horas": "2",
                "minutos": "0",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        produccion = Produccion.objects.get()
        self.assertEqual(produccion.cantidad, 6)
        self.assertEqual(produccion.destino, "STOCK")
        self.assertIn(
            "Excedente voluntario para stock: 1",
            produccion.observaciones,
        )

    def test_pieza_interna_es_bloqueada_en_nuevo_pedido(self):
        pieza = Producto.objects.create(
            nombre="Pieza interna",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=1,
            minutos=0,
            peso_gramos=Decimal("5"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=True,
        )

        respuesta = self.client.post(
            reverse("pedidos:nuevo"),
            {
                "producto_0": str(pieza.id),
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(respuesta.url, reverse("pedidos:nuevo"))
        self.assertEqual(Pedido.objects.count(), 1)

    def test_api_kit_libre_no_devuelve_piezas_internas(self):
        pieza = Producto.objects.create(
            nombre="Pieza kit interna",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=1,
            minutos=0,
            peso_gramos=Decimal("5"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=True,
        )
        kit = Kit.objects.create(
            nombre="Kit libre test",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=1,
            precio=Decimal("1000"),
            activo=True,
        )

        respuesta = self.client.get(
            reverse("pedidos:productos_kit", args=[kit.id])
        )
        self.assertEqual(respuesta.status_code, 200)
        ids = {
            item["id"]
            for item in respuesta.json()["productos"]
        }
        self.assertIn(self.producto.id, ids)
        self.assertNotIn(pieza.id, ids)

    def test_impresiones_por_producto_redirige_a_planificacion(self):
        respuesta = self.client.get(
            reverse("pedidos:impresiones_productos")
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            respuesta.url,
            reverse("produccion:lista"),
        )

        planificacion = self.client.get(
            reverse("produccion:lista")
        )
        self.assertEqual(planificacion.status_code, 200)
        self.assertContains(planificacion, "Necesidad de impresión")
        self.assertContains(planificacion, "PLANIFICAR ESTE PRODUCTO")
        self.assertContains(planificacion, "Cantidad")
