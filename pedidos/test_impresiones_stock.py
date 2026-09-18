from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from productos.models import Producto, ProductoComponente, TipoProducto
from produccion.models import Produccion

from .impresiones_stock import obtener_impresiones_por_producto
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
class StockRealImpresionesPorProductoTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="stock-tester",
            password="test12345",
        )
        self.client.force_login(usuario)

        tipo = TipoProducto.objects.create(
            nombre="Compuestos stock",
            activo=True,
        )
        self.pieza = Producto.objects.create(
            nombre="Pieza con stock",
            categoria="PRODUCTO",
            tipo=tipo,
            horas=1,
            minutos=0,
            peso_gramos=Decimal("10"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            stock=3,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=True,
        )
        self.compuesto = Producto.objects.create(
            nombre="Producto compuesto",
            categoria="PRODUCTO",
            tipo=tipo,
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            stock=0,
            activo=True,
            tipo_fabricacion="COMPUESTO",
            solo_produccion=False,
        )
        ProductoComponente.objects.create(
            producto=self.compuesto,
            componente=self.pieza,
            cantidad=2,
        )

        cliente = Cliente.objects.create(
            nombre="Cliente stock",
            activo=True,
        )
        pedido = Pedido.objects.create(
            cliente=cliente,
            estado="PENDIENTE",
        )
        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PRODUCTO",
            producto=self.compuesto,
            cantidad=2,
            precio_unitario=Decimal("1000"),
            estado="PENDIENTE",
        )

    def _item_pieza(self):
        return next(
            item
            for item in obtener_impresiones_por_producto()
            if item["producto"].id == self.pieza.id
        )

    def test_pieza_muestra_stock_real_y_descuenta_necesidad(self):
        item = self._item_pieza()

        self.assertEqual(item["cantidad_normal"], 4)
        self.assertEqual(item["stock"], 3)
        self.assertEqual(item["necesidad_normal_impresion"], 1)
        self.assertEqual(item["a_imprimir"], 1)
        self.assertEqual(item["falta_normal_planificar"], 1)
        self.assertEqual(item["falta_iniciar"], 1)

    def test_planificador_usa_stock_de_pieza_para_calcular_excedente(self):
        inicio = (
            timezone.localtime(timezone.now() + timedelta(hours=2))
            .strftime("%Y-%m-%dT%H:%M")
        )

        respuesta = self.client.post(
            reverse("pedidos:planificar_impresion_producto"),
            {
                "producto": self.pieza.id,
                "cantidad": "2",
                "inicio_impresion": inicio,
                "horas": "1",
                "minutos": "0",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        produccion = Produccion.objects.get()
        self.assertIn(
            "Demanda estándar pendiente al planificar: 1",
            produccion.observaciones,
        )
        self.assertIn(
            "Excedente voluntario para stock: 1",
            produccion.observaciones,
        )


    def test_marcar_un_pedido_listo_reduce_demanda_y_stock_en_paralelo(self):
        pepino = Producto.objects.create(
            nombre="Pepino Sensorial regresion",
            categoria="PRODUCTO",
            tipo=self.pieza.tipo,
            horas=1,
            minutos=0,
            peso_gramos=Decimal("10"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            stock=9,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=False,
        )
        cliente = Cliente.objects.first()
        pedidos = []

        for _ in range(9):
            pedido = Pedido.objects.create(
                cliente=cliente,
                estado="PENDIENTE",
            )
            DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="PRODUCTO",
                producto=pepino,
                cantidad=1,
                precio_unitario=Decimal("1000"),
                estado="PENDIENTE",
            )
            pedidos.append(pedido)

        # Reproduce la pantalla "Impresiones por pedido": crea los estados
        # operativos que luego usa la acción para marcar una unidad como LISTO.
        respuesta = self.client.get(reverse("pedidos:impresiones"))
        self.assertEqual(respuesta.status_code, 200)

        estado = pedidos[0].estados_impresion.get(producto=pepino)
        respuesta = self.client.post(
            reverse("pedidos:cambiar_listo"),
            {
                "estado_id": estado.id,
                "listo": "1",
            },
        )
        self.assertEqual(respuesta.status_code, 302)

        pepino.refresh_from_db()
        self.assertEqual(pepino.stock, 8)

        items = [
            item
            for item in obtener_impresiones_por_producto()
            if item["producto"].id == pepino.id
        ]

        # Con 8 pedidos pendientes y stock físico 8 no hay necesidad
        # de fabricación, por lo que el producto debe desaparecer de
        # "Impresiones por producto".
        self.assertEqual(items, [])

    def test_stock_no_cubre_personalizados_genericos(self):
        DetallePedido.objects.create(
            pedido=Pedido.objects.first(),
            tipo_item="PERSONALIZADO",
            producto=self.compuesto,
            cantidad=1,
            precio_unitario=Decimal("1000"),
            precio_total_personalizado=Decimal("1000"),
            estado="PENDIENTE",
            personalizado=True,
            detalle_personalizacion="Nombre especial",
        )

        item = self._item_pieza()

        self.assertEqual(item["cantidad_normal"], 4)
        self.assertEqual(item["cantidad_personalizada"], 2)
        self.assertEqual(item["stock"], 3)
        self.assertEqual(item["a_imprimir"], 3)
