from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from costos.models import ConfiguracionCostos
from kits.models import Kit
from pedidos.models import (
    DetalleKitProducto,
    DetallePedido,
    Pedido,
    Presupuesto,
)
from productos.models import Producto, TipoProducto


class RepetirPedidoComoPresupuestoTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="repetir-pedido",
            password="test12345",
        )
        self.client.force_login(usuario)

        ConfiguracionCostos.objects.create(
            nombre="Costos test",
            coste_plastico_kg=Decimal("20000"),
            tasa_fallos=Decimal("10"),
            coste_luz_hora=Decimal("100"),
            coste_amortizacion_hora=Decimal("200"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        tipo = TipoProducto.objects.create(
            nombre="Sensoriales",
        )
        self.producto = Producto.objects.create(
            nombre="Cono giratorio",
            categoria="PRODUCTO",
            tipo=tipo,
            horas=1,
            minutos=0,
            peso_gramos=Decimal("40"),
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            activo=True,
        )
        self.cliente_obj = Cliente.objects.create(
            nombre="Cliente prueba",
            telefono="11 5555 5555",
        )
        self.pedido = Pedido.objects.create(
            cliente=self.cliente_obj,
            estado="ENTREGADO",
            observaciones="Entregar en caja grande",
        )
        DetallePedido.objects.create(
            pedido=self.pedido,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=2,
            precio_unitario=Decimal("4500"),
            costo_unitario=Decimal("2100"),
            estado="ENTREGADO",
        )

        self.kit = Kit.objects.create(
            nombre="Kit repetible",
            modalidad="FIJO",
            cantidad_productos=2,
            precio=Decimal("8000"),
            activo=True,
        )
        detalle_kit = DetallePedido.objects.create(
            pedido=self.pedido,
            tipo_item="KIT",
            kit=self.kit,
            cantidad=2,
            precio_unitario=Decimal("7000"),
            precio_kit_manual=True,
            costo_unitario=Decimal("3000"),
            estado="ENTREGADO",
        )
        DetalleKitProducto.objects.create(
            detalle=detalle_kit,
            producto=self.producto,
            cantidad=4,
        )

        DetallePedido.objects.create(
            pedido=self.pedido,
            tipo_item="PERSONALIZADO",
            producto=self.producto,
            cantidad=3,
            precio_unitario=Decimal("4000"),
            costo_unitario=Decimal("2100"),
            personalizado=True,
            detalle_personalizacion="Logo al frente",
            color_personalizacion="Rojo",
            precio_total_personalizado=Decimal("12000"),
            estado="ENTREGADO",
        )

    def test_repite_composicion_y_precio_historico(self):
        respuesta = self.client.post(
            reverse(
                "pedidos:repetir_como_presupuesto",
                args=[self.pedido.id],
            )
        )

        presupuesto = Presupuesto.objects.get()

        self.assertRedirects(
            respuesta,
            reverse(
                "pedidos:presupuesto_editar",
                args=[presupuesto.id],
            ),
        )
        self.assertEqual(
            presupuesto.cliente_id,
            self.cliente_obj.id,
        )
        self.assertIsNone(presupuesto.fecha_entrega)
        self.assertEqual(
            presupuesto.observaciones,
            self.pedido.observaciones,
        )

        detalles = list(
            presupuesto.detalles
            .prefetch_related("productos_kit")
            .order_by("id")
        )
        self.assertEqual(len(detalles), 3)

        producto = detalles[0]
        self.assertEqual(producto.cantidad, 2)
        self.assertEqual(
            producto.precio_unitario,
            Decimal("4500"),
        )

        kit = detalles[1]
        self.assertEqual(kit.cantidad, 2)
        self.assertEqual(
            kit.precio_unitario,
            Decimal("7000"),
        )
        self.assertTrue(kit.precio_kit_manual)
        self.assertEqual(
            kit.productos_kit.get().cantidad,
            4,
        )

        personalizado = detalles[2]
        self.assertEqual(
            personalizado.precio_total_personalizado,
            Decimal("12000"),
        )
        self.assertEqual(
            personalizado.detalle_personalizacion,
            "Logo al frente",
        )
        self.assertEqual(
            personalizado.color_personalizacion,
            "Rojo",
        )
