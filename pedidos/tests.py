from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from costos.models import ConfiguracionCostos
from productos.models import Producto, ProductoComponente, TipoProducto


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

        # Simula un resumen viejo/incompleto en el padre. La API que consumen
        # Nuevo Pedido y Editar Pedido debe seguir calculando desde las piezas.
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
