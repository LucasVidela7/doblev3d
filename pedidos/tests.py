from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from costos.models import ConfiguracionCostos
from productos.models import Producto, ProductoComponente, TipoProducto

from .models import Pedido


class PrecioProductoApiTests(TestCase):
    def setUp(self):
        self.tipo = TipoProducto.objects.create(nombre="Test pedidos")
        ConfiguracionCostos.objects.create(
            nombre="Test",
            coste_plastico_kg=Decimal("20000"),
            tasa_fallos=Decimal("10"),
            coste_luz_hora=Decimal("100"),
            coste_amortizacion_hora=Decimal("200"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )

    def pieza(self, nombre, horas, minutos, peso):
        return Producto.objects.create(
            nombre=nombre,
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=horas,
            minutos=minutos,
            peso_gramos=Decimal(str(peso)),
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=True,
        )

    def test_api_calcula_precio_compuesto_desde_sus_piezas(self):
        cuerpo = self.pieza("Cuerpo", 1, 30, 80)
        tapa = self.pieza("Tapa", 0, 20, 15)

        producto = Producto.objects.create(
            nombre="Producto compuesto",
            categoria="PRODUCTO",
            tipo=self.tipo,
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            activo=True,
            tipo_fabricacion="COMPUESTO",
            solo_produccion=False,
        )

        ProductoComponente.objects.create(
            producto=producto,
            componente=cuerpo,
            cantidad=1,
        )
        ProductoComponente.objects.create(
            producto=producto,
            componente=tapa,
            cantidad=2,
        )

        Producto.objects.filter(pk=producto.pk).update(
            horas=0,
            minutos=0,
            peso_gramos=Decimal("0"),
        )

        respuesta = self.client.get(
            reverse("pedidos:precio_producto"),
            {
                "producto_id": producto.id,
                "cantidad": 10,
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()

        self.assertTrue(datos["ok"])
        self.assertTrue(datos["producto"]["es_compuesto"])
        self.assertGreater(datos["producto"]["precio_lista"], 0)
        self.assertGreater(datos["costo_productivo"], 0)
        self.assertGreater(datos["producto"]["peso_gramos"], 0)
        self.assertGreater(datos["producto"]["horas"], 0)

        for estrategia in ("conservador", "recomendado", "agresivo"):
            self.assertIn(estrategia, datos["escenarios"])
            self.assertGreater(
                datos["escenarios"][estrategia]["total_recomendado"],
                0,
            )
            self.assertGreater(
                datos["escenarios"][estrategia]["precio_unitario_pedido"],
                0,
            )


class AccionesPedidoEstadoTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombre="Cliente test",
            activo=True,
        )
        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )

    def _estado(self, estado):
        self.pedido.estado = estado
        self.pedido.save(update_fields=["estado"])

    def test_editar_solo_se_permite_en_pendiente(self):
        for estado in ("PREPARANDO", "LISTO", "ENTREGADO", "CANCELADO"):
            self._estado(estado)
            respuesta = self.client.get(
                reverse("pedidos:editar", args=[self.pedido.id])
            )
            self.assertEqual(respuesta.status_code, 302)
            self.pedido.refresh_from_db()
            self.assertEqual(self.pedido.estado, estado)

    def test_cancelar_no_se_permite_fuera_de_pendiente(self):
        self._estado("LISTO")
        respuesta = self.client.post(
            reverse("pedidos:cancelar", args=[self.pedido.id])
        )
        self.assertEqual(respuesta.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, "LISTO")

    def test_eliminar_no_se_permite_fuera_de_pendiente(self):
        self._estado("PREPARANDO")
        respuesta = self.client.post(
            reverse("pedidos:eliminar", args=[self.pedido.id])
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Pedido.objects.filter(pk=self.pedido.id).exists())

    def test_entregar_requiere_estado_listo(self):
        respuesta = self.client.post(
            reverse("pedidos:entregar", args=[self.pedido.id])
        )
        self.assertEqual(respuesta.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, "PENDIENTE")

        self._estado("LISTO")
        respuesta = self.client.post(
            reverse("pedidos:entregar", args=[self.pedido.id])
        )
        self.assertEqual(respuesta.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, "ENTREGADO")

    def test_entregar_desde_cliente_vuelve_al_detalle(self):
        self._estado("LISTO")
        respuesta = self.client.post(
            reverse("pedidos:entregar", args=[self.pedido.id]),
            {
                "origen": "cliente",
                "cliente_id": str(self.cliente.id),
            },
        )
        self.assertRedirects(
            respuesta,
            reverse("clientes:detalle", args=[self.cliente.id]),
            fetch_redirect_response=False,
        )
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, "ENTREGADO")
