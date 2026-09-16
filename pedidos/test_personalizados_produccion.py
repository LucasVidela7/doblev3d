from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from produccion.models import Produccion
from productos.models import Producto, ProductoComponente, TipoProducto

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
class PersonalizadosProduccionTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="personalizados-produccion-tests",
            password="test-pass-seguro",
        )
        self.client.force_login(usuario)

        self.tipo = TipoProducto.objects.create(
            nombre="Personalizados QA",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Producto personalizable",
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
            nombre="Cliente personalizado QA",
            activo=True,
        )

    def _pedido(self):
        return Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )

    def _personalizado(self, pedido, producto=None, cantidad=1):
        producto = producto or self.producto
        return DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PERSONALIZADO",
            producto=producto,
            cantidad=cantidad,
            precio_unitario=Decimal("2000"),
            precio_total_personalizado=Decimal("2000") * cantidad,
            estado="PENDIENTE",
            personalizado=True,
            detalle_personalizacion="Nombre LUCAS",
            color_personalizacion="Azul",
        )

    def _inicio_futuro(self):
        return (
            timezone.localtime(timezone.now() + timedelta(hours=2))
            .strftime("%Y-%m-%dT%H:%M")
        )

    def test_confirmar_personalizado_no_da_500_y_actualiza_pedido(self):
        pedido = self._pedido()
        detalle = self._personalizado(pedido)

        respuesta = self.client.post(
            reverse("pedidos:cambiar_listo"),
            {
                "detalle_personalizado_id": str(detalle.id),
                "listo": "1",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        detalle.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(detalle.estado, "LISTO")
        self.assertEqual(pedido.estado, "LISTO")

    def test_produccion_lista_cierra_personalizado_y_elimina_la_necesidad(self):
        pedido = self._pedido()
        detalle = self._personalizado(pedido, cantidad=2)

        produccion = Produccion.objects.create(
            producto=self.producto,
            cantidad=2,
            destino="PEDIDO",
            pedido=pedido,
            estado="PENDIENTE",
            inicio_impresion=timezone.now(),
            tiempo_impresion_minutos=60,
            observaciones=f"PERSONALIZADO:{detalle.id}\nPrueba QA",
        )

        detalle.refresh_from_db()
        self.assertEqual(detalle.estado, "PENDIENTE")

        produccion.estado = "LISTO"
        produccion.save(update_fields=["estado"])

        detalle.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(detalle.estado, "LISTO")
        self.assertEqual(pedido.estado, "LISTO")

        ids = {
            item["producto"].id
            for item in obtener_impresiones_por_producto()
        }
        self.assertNotIn(self.producto.id, ids)

    def test_revertir_produccion_lista_devuelve_personalizado_a_pendiente(self):
        pedido = self._pedido()
        detalle = self._personalizado(pedido)
        produccion = Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            destino="PEDIDO",
            pedido=pedido,
            estado="LISTO",
            inicio_impresion=timezone.now(),
            tiempo_impresion_minutos=60,
            observaciones=f"PERSONALIZADO:{detalle.id}",
        )

        detalle.refresh_from_db()
        self.assertEqual(detalle.estado, "LISTO")

        produccion.estado = "PENDIENTE"
        produccion.save(update_fields=["estado"])

        detalle.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(detalle.estado, "PENDIENTE")
        self.assertEqual(pedido.estado, "PENDIENTE")

    def test_compuesto_requiere_todas_sus_piezas_finalizadas(self):
        pieza_a = Producto.objects.create(
            nombre="Pieza A",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=1,
            minutos=0,
            peso_gramos=Decimal("10"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=True,
        )
        pieza_b = Producto.objects.create(
            nombre="Pieza B",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=1,
            minutos=0,
            peso_gramos=Decimal("10"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=True,
        )
        compuesto = Producto.objects.create(
            nombre="Personalizado compuesto",
            categoria="PRODUCTO",
            tipo=self.tipo,
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            personalizable=True,
            stock=0,
            activo=True,
            tipo_fabricacion="COMPUESTO",
            solo_produccion=False,
        )
        ProductoComponente.objects.create(
            producto=compuesto,
            componente=pieza_a,
            cantidad=1,
        )
        ProductoComponente.objects.create(
            producto=compuesto,
            componente=pieza_b,
            cantidad=2,
        )

        pedido = self._pedido()
        detalle = self._personalizado(pedido, producto=compuesto, cantidad=1)

        Produccion.objects.create(
            producto=pieza_a,
            cantidad=1,
            destino="PEDIDO",
            pedido=pedido,
            estado="LISTO",
            inicio_impresion=timezone.now(),
            tiempo_impresion_minutos=60,
            observaciones=f"PERSONALIZADO:{detalle.id}",
        )
        detalle.refresh_from_db()
        self.assertEqual(detalle.estado, "PENDIENTE")

        Produccion.objects.create(
            producto=pieza_b,
            cantidad=2,
            destino="PEDIDO",
            pedido=pedido,
            estado="LISTO",
            inicio_impresion=timezone.now(),
            tiempo_impresion_minutos=60,
            observaciones=f"PERSONALIZADO:{detalle.id}",
        )
        detalle.refresh_from_db()
        self.assertEqual(detalle.estado, "LISTO")

    def test_vista_repara_personalizado_historico_con_produccion_lista(self):
        pedido = self._pedido()
        detalle = self._personalizado(pedido)
        produccion = Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            destino="PEDIDO",
            pedido=pedido,
            estado="LISTO",
            inicio_impresion=timezone.now(),
            tiempo_impresion_minutos=60,
            observaciones="Producción histórica sin marca inicial",
        )

        # Simula un registro LISTO anterior a la señal actual.
        Produccion.objects.filter(pk=produccion.pk).update(
            observaciones=f"PERSONALIZADO:{detalle.id}\nHistórico"
        )
        detalle.refresh_from_db()
        self.assertEqual(detalle.estado, "PENDIENTE")

        respuesta = self.client.get(
            reverse("pedidos:impresiones_productos")
        )
        self.assertEqual(respuesta.status_code, 200)

        detalle.refresh_from_db()
        self.assertEqual(detalle.estado, "LISTO")

    def test_planificador_estandar_permite_superar_demanda_para_stock(self):
        pedido = self._pedido()
        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=5,
            precio_unitario=Decimal("1000"),
            estado="PENDIENTE",
        )

        respuesta = self.client.post(
            reverse("pedidos:planificar_impresion_producto"),
            {
                "producto": self.producto.id,
                "cantidad": "8",
                "inicio_impresion": self._inicio_futuro(),
                "horas": "3",
                "minutos": "0",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        produccion = Produccion.objects.get()
        self.assertEqual(produccion.cantidad, 8)
        self.assertEqual(produccion.destino, "STOCK")
        self.assertIn("Excedente voluntario para stock: 3", produccion.observaciones)

    def test_planificador_personalizado_conserva_limite_del_pedido(self):
        pedido = self._pedido()
        detalle = self._personalizado(pedido, cantidad=2)

        respuesta = self.client.post(
            reverse("pedidos:planificar_impresion_producto"),
            {
                "producto": self.producto.id,
                "personalizado_id": detalle.id,
                "cantidad": "3",
                "inicio_impresion": self._inicio_futuro(),
                "horas": "2",
                "minutos": "0",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertFalse(Produccion.objects.exists())

    def test_planificador_personalizado_no_ignora_produccion_ya_lista(self):
        pedido = self._pedido()
        detalle = self._personalizado(pedido, cantidad=3)
        Produccion.objects.create(
            producto=self.producto,
            cantidad=2,
            destino="PEDIDO",
            pedido=pedido,
            estado="LISTO",
            inicio_impresion=timezone.now(),
            tiempo_impresion_minutos=60,
            observaciones=f"PERSONALIZADO:{detalle.id}",
        )

        detalle.refresh_from_db()
        self.assertEqual(detalle.estado, "PENDIENTE")

        respuesta = self.client.post(
            reverse("pedidos:planificar_impresion_producto"),
            {
                "producto": self.producto.id,
                "personalizado_id": detalle.id,
                "cantidad": "2",
                "inicio_impresion": self._inicio_futuro(),
                "horas": "1",
                "minutos": "0",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Produccion.objects.count(), 1)

    def test_interfaz_indica_cantidad_libre(self):
        pedido = self._pedido()
        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=2,
            precio_unitario=Decimal("1000"),
            estado="PENDIENTE",
        )

        respuesta = self.client.get(
            reverse("pedidos:impresiones_productos")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "dv-planificador-libre-script")
        self.assertContains(respuesta, "Cantidad libre")
