from datetime import date
from decimal import Decimal

from django.test import TestCase

import config.ui_middleware as ui_middleware
from costos.models import ConfiguracionCostos
from productos.models import Producto, TipoProducto

from .economia import recomendacion_kit
from .models import Kit, KitComponente
from .ui_alignment import (
    _dashboard_kits_html,
    _datos_economicos_kits,
    _kit_economia_html,
    aplicar,
)


class KitsUIAlignmentTests(TestCase):
    def setUp(self):
        aplicar()

        ConfiguracionCostos.objects.create(
            nombre="Test UI kits",
            coste_plastico_kg=Decimal("1000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )

        self.tipo = TipoProducto.objects.create(
            nombre="Tipo UI kits",
            activo=True,
        )

        self.producto = Producto.objects.create(
            nombre="Producto UI",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=0,
            peso_gramos=Decimal("1000"),
            margen_ganancia=Decimal("70"),
            requiere_impresion=True,
            personalizable=False,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=False,
        )

    def crear_kit_fijo(self, nombre, precio=Decimal("1000")):
        kit = Kit.objects.create(
            nombre=nombre,
            modalidad="FIJO",
            cantidad_productos=1,
            precio=precio,
            activo=True,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=self.producto,
            cantidad=1,
        )
        return kit

    def test_middleware_usa_fuente_unica_de_recomendacion(self):
        self.assertIs(
            ui_middleware._datos_economicos_kits,
            _datos_economicos_kits,
        )
        self.assertIs(
            ui_middleware._dashboard_kits_html,
            _dashboard_kits_html,
        )
        self.assertIs(
            ui_middleware._kit_economia_html,
            _kit_economia_html,
        )

    def test_datos_distinguen_revisar_advertencia_y_ok(self):
        kit_critico = self.crear_kit_fijo("Kit crítico")
        base_critico = recomendacion_kit(kit_critico)
        kit_critico.precio = max(
            base_critico["precio_agresivo"] - Decimal("100"),
            Decimal("1"),
        )
        kit_critico.save(update_fields=["precio"])

        kit_advertencia = self.crear_kit_fijo("Kit advertencia")
        base_advertencia = recomendacion_kit(kit_advertencia)
        self.assertGreater(
            base_advertencia["precio_recomendado"],
            base_advertencia["precio_agresivo"],
        )
        kit_advertencia.precio = (
            base_advertencia["precio_agresivo"]
            + base_advertencia["precio_recomendado"]
        ) / Decimal("2")
        kit_advertencia.save(update_fields=["precio"])

        kit_ok = self.crear_kit_fijo("Kit OK")
        base_ok = recomendacion_kit(kit_ok)
        kit_ok.precio = base_ok["precio_recomendado"]
        kit_ok.save(update_fields=["precio"])

        datos, total, resumen = _datos_economicos_kits()

        self.assertEqual(total, 3)
        self.assertEqual(
            datos[str(kit_critico.id)]["estado"],
            "REVISAR",
        )
        self.assertEqual(
            datos[str(kit_advertencia.id)]["estado"],
            "ADVERTENCIA",
        )
        self.assertEqual(
            datos[str(kit_ok.id)]["estado"],
            "OK",
        )
        self.assertEqual(resumen["criticos"], 1)
        self.assertEqual(resumen["advertencias"], 1)
        self.assertEqual(resumen["total_revision"], 2)

    def test_pedido_muestra_los_tres_escenarios(self):
        kit = self.crear_kit_fijo("Kit pedido")
        base = recomendacion_kit(kit)
        kit.precio = base["precio_recomendado"]
        kit.save(update_fields=["precio"])

        datos, _, _ = _datos_economicos_kits()
        html = _kit_economia_html(datos)

        self.assertIn("AGRESIVO $", html)
        self.assertIn("RECOMENDADO $", html)
        self.assertIn("CONSERVADOR $", html)
        self.assertIn("BAJO RECOMENDADO", html)
        self.assertNotIn("precio_sugerido_minimo", html)

    def test_dashboard_separa_criticos_y_advertencias(self):
        html = _dashboard_kits_html(
            5,
            {
                "criticos": 2,
                "advertencias": 1,
                "sin_datos": 1,
                "total_revision": 4,
            },
        )

        self.assertIn("2 por debajo de Agresivo", html)
        self.assertIn("1 sin datos de costo", html)
        self.assertIn("1 kit por debajo de Recomendado", html)
        self.assertIn("Precios según la calculadora", html)
