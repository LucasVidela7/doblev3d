from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from costos.models import ConfiguracionCostos
from productos.models import Producto, TipoProducto

from .models import (
    DetallePedido,
    DetallePresupuesto,
    Pedido,
    Presupuesto,
)


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
class PresupuestosTests(TestCase):
    def setUp(self):
        ConfiguracionCostos.objects.create(
            nombre="Costos presupuestos QA",
            coste_plastico_kg=Decimal("20000"),
            coste_plastico_kg_cantidad=Decimal("14000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        self.tipo = TipoProducto.objects.create(
            nombre="Tipo presupuesto QA",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Producto presupuesto QA",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=30,
            peso_gramos=Decimal("100"),
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            personalizable=False,
            stock=5,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=False,
        )
        self.cliente = Cliente.objects.create(
            nombre="Cliente presupuesto QA",
            activo=True,
        )
        self.usuario = get_user_model().objects.create_user(
            username="qa-presupuestos",
            password="ClaveSegura-12345",
        )
        self.client.force_login(self.usuario)

    def _crear_presupuesto(self, cantidad=2, total="9000"):
        return self.client.post(
            reverse("pedidos:nuevo"),
            data={
                "cliente": str(self.cliente.id),
                "fecha_entrega": "",
                "observaciones": "Consulta por WhatsApp",
                "item_indice": ["1"],
                "tipo_item_1": "PRODUCTO",
                "producto_1": str(self.producto.id),
                "cantidad_1": str(cantidad),
                "precio_total_producto_1": total,
                "precio_unitario_1": "",
                "precio_producto_manual_1": "1",
            },
        )

    def test_nuevo_presupuesto_carga_menu_y_tema_global(self):
        respuesta = self.client.get(
            reverse("pedidos:nuevo")
        )

        self.assertEqual(respuesta.status_code, 200)
        contenido = respuesta.content.decode()
        self.assertIn('id="dvManagementMenu"', contenido)
        self.assertRegex(
            contenido,
            r"/static/shared/management_menu(?:\.[0-9a-f]+)?\.css",
        )
        self.assertRegex(
            contenido,
            r"/static/shared/theme(?:\.[0-9a-f]+)?\.css",
        )
        self.assertIn(
            'id="dv-pedido-form-style"',
            contenido,
        )

    def test_nuevo_crea_presupuesto_y_no_pedido(self):
        respuesta = self._crear_presupuesto()

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Pedido.objects.count(), 0)
        presupuesto = Presupuesto.objects.get()
        self.assertEqual(presupuesto.estado, "PENDIENTE")
        self.assertEqual(presupuesto.cliente, self.cliente)
        self.assertEqual(presupuesto.total, Decimal("9000.00"))
        self.assertEqual(
            respuesta.url,
            reverse(
                "pedidos:presupuesto_detalle",
                args=[presupuesto.id],
            ),
        )

        detalle = DetallePresupuesto.objects.get(
            presupuesto=presupuesto,
        )
        self.assertEqual(detalle.cantidad, 2)
        self.assertEqual(
            detalle.precio_unitario,
            Decimal("4500.00"),
        )

    def test_detalle_muestra_subtotales_y_descuentos(self):
        self._crear_presupuesto()
        presupuesto = Presupuesto.objects.get()

        respuesta = self.client.get(
            reverse(
                "pedidos:presupuesto_detalle",
                args=[presupuesto.id],
            )
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, presupuesto.codigo)
        self.assertContains(respuesta, "SUBTOTAL LISTA")
        self.assertContains(respuesta, "DESCUENTOS")
        self.assertContains(respuesta, "TOTAL PRESUPUESTADO")

    def test_presupuesto_pendiente_se_puede_editar(self):
        self._crear_presupuesto()
        presupuesto = Presupuesto.objects.get()

        respuesta = self.client.post(
            reverse(
                "pedidos:presupuesto_editar",
                args=[presupuesto.id],
            ),
            data={
                "cliente": str(self.cliente.id),
                "fecha_entrega": "",
                "observaciones": "Actualizado",
                "item_indice": ["1"],
                "tipo_item_1": "PRODUCTO",
                "producto_1": str(self.producto.id),
                "cantidad_1": "1",
                "precio_total_producto_1": "6000",
                "precio_unitario_1": "",
                "precio_producto_manual_1": "1",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        presupuesto.refresh_from_db()
        self.assertEqual(
            presupuesto.observaciones,
            "Actualizado",
        )
        self.assertEqual(
            presupuesto.total,
            Decimal("6000.00"),
        )
        self.assertEqual(Pedido.objects.count(), 0)

    def test_aprobar_convierte_presupuesto_en_pedido(self):
        self._crear_presupuesto()
        presupuesto = Presupuesto.objects.get()
        precio_cotizado = presupuesto.detalles.get().precio_unitario

        respuesta = self.client.post(
            reverse(
                "pedidos:presupuesto_aprobar",
                args=[presupuesto.id],
            )
        )

        self.assertEqual(respuesta.status_code, 302)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "APROBADO")
        self.assertIsNotNone(presupuesto.pedido_generado_id)

        pedido = Pedido.objects.get()
        self.assertEqual(pedido.cliente, self.cliente)
        detalle = DetallePedido.objects.get(pedido=pedido)
        self.assertEqual(detalle.precio_unitario, precio_cotizado)
        self.assertEqual(
            pedido.presupuesto_origen.id,
            presupuesto.id,
        )
        self.assertEqual(
            respuesta.url,
            reverse("pedidos:detalle", args=[pedido.id]),
        )

    def test_rechazar_no_crea_pedido(self):
        self._crear_presupuesto()
        presupuesto = Presupuesto.objects.get()

        respuesta = self.client.post(
            reverse(
                "pedidos:presupuesto_rechazar",
                args=[presupuesto.id],
            )
        )

        self.assertEqual(respuesta.status_code, 302)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "RECHAZADO")
        self.assertEqual(Pedido.objects.count(), 0)
