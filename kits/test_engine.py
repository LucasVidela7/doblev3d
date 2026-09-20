from datetime import date
from decimal import Decimal

from django.test import TestCase

from costos.models import ConfiguracionCostos
from productos.models import Producto, TipoProducto

from .engine import KitEngine
from .models import Kit, KitComponente


class KitEngineTests(TestCase):
    def setUp(self):
        ConfiguracionCostos.objects.create(
            nombre="Engine Kits",
            coste_plastico_kg=Decimal("1000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        self.tipo = TipoProducto.objects.create(
            nombre="Engine tipo",
            activo=True,
        )
        self.a = Producto.objects.create(
            nombre="Engine A",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("100"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            activo=True,
            solo_produccion=False,
        )
        self.b = Producto.objects.create(
            nombre="Engine B",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("800"),
            margen_ganancia=Decimal("65"),
            requiere_impresion=True,
            activo=True,
            solo_produccion=False,
        )

    def test_fijo_devuelve_componentes_escalados(self):
        kit = Kit.objects.create(
            nombre="Engine fijo",
            modalidad="FIJO",
            cantidad_productos=2,
            precio=Decimal("5000"),
        )
        KitComponente.objects.create(
            kit=kit,
            producto=self.a,
            cantidad=2,
        )

        componentes = KitEngine.componentes(
            kit,
            cantidad_kits=3,
        )

        self.assertEqual(len(componentes), 1)
        self.assertEqual(componentes[0]["cantidad"], 6)

    def test_libre_valida_seleccion_y_precio(self):
        kit = Kit.objects.create(
            nombre="Engine libre",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("3000"),
            proteger_rentabilidad_libre=True,
        )

        precio = KitEngine.precio_unitario(
            kit,
            productos=[self.a, self.b],
        )

        self.assertGreaterEqual(precio, kit.precio)

    def test_snapshot_congela_identidad_y_componentes(self):
        kit = Kit.objects.create(
            nombre="Engine snapshot",
            modalidad="FIJO",
            cantidad_productos=2,
            precio=Decimal("5000"),
        )
        KitComponente.objects.create(
            kit=kit,
            producto=self.a,
            cantidad=2,
        )

        snapshot = KitEngine.snapshot(
            kit,
            cantidad_kits=2,
            precio_unitario=Decimal("4800"),
            precio_manual=True,
            componentes=[
                {
                    "producto": self.a,
                    "cantidad": 4,
                }
            ],
            costo_unitario=Decimal("1000"),
        )

        self.assertEqual(snapshot["nombre"], "Engine snapshot")
        self.assertEqual(snapshot["modalidad"], "FIJO")
        self.assertEqual(snapshot["precio_unitario_vendido"], "4800")
        self.assertTrue(snapshot["precio_manual"])
        self.assertEqual(
            snapshot["componentes"][0]["cantidad_total"],
            4,
        )
        self.assertEqual(
            snapshot["componentes"][0]["cantidad_por_kit"],
            "2",
        )
