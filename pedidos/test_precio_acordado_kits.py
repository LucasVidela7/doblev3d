from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from costos.models import ConfiguracionCostos
from kits.models import Kit, KitComponente
from productos.models import Producto, TipoProducto

from .models import DetalleKitProducto, DetallePedido, Pedido


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    },
)
class PrecioAcordadoKitTests(TestCase):
    def setUp(self):
        ConfiguracionCostos.objects.create(
            nombre="Costo QA pedidos",
            coste_plastico_kg=Decimal("20000"),
            coste_plastico_kg_cantidad=Decimal("14000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        self.tipo = TipoProducto.objects.create(
            nombre="Tipo QA kits",
            activo=True,
        )
        self.producto_a = Producto.objects.create(
            nombre="Pieza A QA",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=1,
            peso_gramos=Decimal("100"),
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            personalizable=False,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=False,
        )
        self.producto_b = Producto.objects.create(
            nombre="Pieza B QA",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=1,
            peso_gramos=Decimal("80"),
            margen_ganancia=Decimal("55"),
            requiere_impresion=True,
            personalizable=False,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=False,
        )
        self.kit = Kit.objects.create(
            nombre="Kit acordado QA",
            modalidad="FIJO",
            cantidad_productos=2,
            precio=Decimal("52000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=self.kit,
            producto=self.producto_a,
            cantidad=2,
        )
        self.cliente = Cliente.objects.create(
            nombre="Cliente QA precio kit",
            activo=True,
        )
        self.usuario = get_user_model().objects.create_user(
            username="qa-precio-kit",
            password="ClaveSegura-12345",
        )
        self.client.force_login(self.usuario)

    def _crear_detalle_kit(self, pedido, kit=None, cantidad=5, precio=None, manual=True):
        kit = kit or self.kit
        detalle = DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="KIT",
            kit=kit,
            cantidad=cantidad,
            precio_unitario=precio or kit.precio,
            precio_kit_manual=manual,
            estado="PENDIENTE",
        )
        for componente in kit.componentes.all():
            DetalleKitProducto.objects.create(
                detalle=detalle,
                producto=componente.producto,
                cantidad=componente.cantidad * cantidad,
            )
        detalle.refresh_from_db()
        return detalle

    def test_nuevo_pedido_guarda_precio_acordado_de_kit(self):
        respuesta = self.client.post(
            reverse("pedidos:nuevo"),
            data={
                "cliente": str(self.cliente.id),
                "fecha_entrega": "",
                "observaciones": "Precio conversado por WhatsApp",
                "item_indice": ["1"],
                "tipo_item_1": "KIT",
                "kit_1": str(self.kit.id),
                "cantidad_1": "5",
                "precio_unitario_kit_1": "44000.00",
                "precio_kit_manual_1": "1",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        detalle = DetallePedido.objects.get(tipo_item="KIT")
        self.assertTrue(detalle.precio_kit_manual)
        self.assertEqual(detalle.precio_unitario, Decimal("44000.00"))
        self.assertEqual(detalle.subtotal, Decimal("220000.00"))

    def test_precio_manual_no_es_pisado_por_descuento_de_volumen(self):
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        detalle = self._crear_detalle_kit(
            pedido,
            cantidad=5,
            precio=Decimal("43000"),
            manual=True,
        )

        detalle.refresh_from_db()
        self.assertEqual(detalle.precio_unitario, Decimal("43000.00"))
        self.assertTrue(detalle.precio_kit_manual)

    def test_editar_pedido_actualiza_y_conserva_precio_manual(self):
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        detalle = self._crear_detalle_kit(
            pedido,
            cantidad=5,
            precio=Decimal("45000"),
            manual=True,
        )

        respuesta = self.client.post(
            reverse("pedidos:editar", args=[pedido.id]),
            data={
                "cliente": str(self.cliente.id),
                "fecha_entrega": "",
                "observaciones": "Actualizado",
                "item_indice": ["0"],
                "detalle_id_0": str(detalle.id),
                "tipo_item_0": "KIT",
                "kit_0": str(self.kit.id),
                "cantidad_0": "5",
                "precio_unitario_kit_0": "42000.00",
                "precio_kit_manual_0": "1",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        nuevo = pedido.detalles.get(tipo_item="KIT")
        self.assertTrue(nuevo.precio_kit_manual)
        self.assertEqual(nuevo.precio_unitario, Decimal("42000.00"))

    def test_editar_kit_libre_reconstruye_productos_repetidos(self):
        kit_libre = Kit.objects.create(
            nombre="Kit libre repetidos QA",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=3,
            precio=Decimal("30000"),
            activo=True,
        )
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        detalle = DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="KIT",
            kit=kit_libre,
            cantidad=5,
            precio_unitario=Decimal("30000"),
            precio_kit_manual=True,
            estado="PENDIENTE",
        )
        DetalleKitProducto.objects.create(
            detalle=detalle,
            producto=self.producto_a,
            cantidad=10,
        )
        DetalleKitProducto.objects.create(
            detalle=detalle,
            producto=self.producto_b,
            cantidad=5,
        )

        respuesta = self.client.get(
            reverse("pedidos:editar", args=[pedido.id])
        )

        self.assertEqual(respuesta.status_code, 200)
        item = respuesta.context["items_iniciales"][0]
        self.assertEqual(len(item["productos_kit_ids"]), 3)
        self.assertEqual(
            item["productos_kit_ids"].count(self.producto_a.id),
            2,
        )
        self.assertEqual(
            item["productos_kit_ids"].count(self.producto_b.id),
            1,
        )
        self.assertTrue(item["precio_kit_manual"])

    def test_editar_kit_fijo_preserva_composicion_guardada(self):
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        detalle = self._crear_detalle_kit(
            pedido,
            cantidad=2,
            precio=Decimal("50000"),
            manual=True,
        )

        # La definición maestra cambia después de realizada la venta.
        self.kit.componentes.all().delete()
        KitComponente.objects.create(
            kit=self.kit,
            producto=self.producto_b,
            cantidad=3,
        )

        respuesta = self.client.post(
            reverse("pedidos:editar", args=[pedido.id]),
            data={
                "cliente": str(self.cliente.id),
                "fecha_entrega": "",
                "observaciones": "Mantener receta vendida",
                "item_indice": ["0"],
                "detalle_id_0": str(detalle.id),
                "tipo_item_0": "KIT",
                "kit_0": str(self.kit.id),
                "cantidad_0": "3",
                "precio_unitario_kit_0": "50000.00",
                "precio_kit_manual_0": "1",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        nuevo = pedido.detalles.get(tipo_item="KIT")
        componentes = {
            componente.producto_id: componente.cantidad
            for componente in nuevo.productos_kit.all()
        }
        self.assertEqual(componentes, {self.producto_a.id: 6})

    def test_formularios_inyectan_precio_de_kit_y_mejoras_visuales(self):
        nuevo = self.client.get(reverse("pedidos:nuevo"))
        self.assertEqual(nuevo.status_code, 200)
        self.assertContains(nuevo, "dv-pedido-form-style")
        self.assertContains(nuevo, "precio_unitario_kit_")
        self.assertContains(nuevo, "USAR PRECIO AUTOMÁTICO")

        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        self._crear_detalle_kit(
            pedido,
            cantidad=1,
            precio=Decimal("51000"),
            manual=True,
        )

        editar = self.client.get(reverse("pedidos:editar", args=[pedido.id]))
        self.assertEqual(editar.status_code, 200)
        self.assertContains(editar, "dv-pedido-form-script")
        self.assertContains(editar, '"precio_kit_manual": true')
