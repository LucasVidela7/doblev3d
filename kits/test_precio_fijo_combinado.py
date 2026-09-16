from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from costos.models import ConfiguracionCostos
from productos.models import Producto, TipoProducto

from .economia import recomendacion_kit
from .models import Kit, KitComponente
from .precio_fijo_combinado import calcular_escenarios_kit_fijo


class PrecioFijoCombinadoTests(TestCase):
    def setUp(self):
        ConfiguracionCostos.objects.create(
            nombre="Costo combo",
            coste_plastico_kg=Decimal("20000"),
            coste_plastico_kg_cantidad=Decimal("14000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        self.tipo = TipoProducto.objects.create(
            nombre="Piezas combo",
            activo=True,
        )
        self.esquinero = self._producto(
            "Esquinero",
            peso=100,
            margen=60,
        )
        self.extension = self._producto(
            "Extensión",
            peso=200,
            margen=60,
        )

    def _producto(self, nombre, peso, margen):
        return Producto.objects.create(
            nombre=nombre,
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=1,
            peso_gramos=Decimal(str(peso)),
            margen_ganancia=Decimal(str(margen)),
            requiere_impresion=True,
            personalizable=False,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=False,
        )

    def _componentes_combo(self):
        return [
            {"producto": self.esquinero, "cantidad": 8},
            {"producto": self.extension, "cantidad": 4},
        ]

    def test_combo_calcula_las_doce_piezas_como_una_sola_compra(self):
        combo = calcular_escenarios_kit_fijo(
            self._componentes_combo()
        )

        self.assertEqual(combo["cantidad_total"], 12)
        self.assertEqual(
            combo["costo_total"],
            Decimal("22400"),
        )
        self.assertEqual(
            combo["margen_tope_ponderado"],
            Decimal("60"),
        )
        self.assertEqual(
            combo["escenarios"]["recomendado"]["margen_objetivo"],
            Decimal("47.3"),
        )
        self.assertEqual(
            combo["escenarios"]["recomendado"]["total_recomendado"],
            Decimal("42600"),
        )

    def test_combo_es_mas_barato_que_comprar_los_bloques_por_separado(self):
        esquineros = calcular_escenarios_kit_fijo(
            [{"producto": self.esquinero, "cantidad": 8}]
        )
        extensiones = calcular_escenarios_kit_fijo(
            [{"producto": self.extension, "cantidad": 4}]
        )
        combo = calcular_escenarios_kit_fijo(
            self._componentes_combo()
        )

        separado = (
            esquineros["escenarios"]["recomendado"]["total_recomendado"]
            + extensiones["escenarios"]["recomendado"]["total_recomendado"]
        )
        recomendado_combo = combo[
            "escenarios"
        ]["recomendado"]["total_recomendado"]

        self.assertEqual(separado, Decimal("45900"))
        self.assertLess(recomendado_combo, separado)
        self.assertEqual(
            combo["escenarios"]["recomendado"]["referencia_separada"],
            separado,
        )
        self.assertEqual(
            combo["escenarios"]["recomendado"]["ahorro_combo"],
            separado - recomendado_combo,
        )

    def test_margen_base_se_pondera_por_el_costo_de_cada_componente(self):
        self.esquinero.margen_ganancia = Decimal("50")
        self.esquinero.save(update_fields=["margen_ganancia"])
        self.extension.margen_ganancia = Decimal("70")
        self.extension.save(update_fields=["margen_ganancia"])

        combo = calcular_escenarios_kit_fijo(
            self._componentes_combo()
        )

        # Ambos bloques aportan $11.200 de costo, por eso 50% y 70%
        # pesan exactamente lo mismo y el margen base queda en 60%.
        self.assertEqual(
            combo["margen_tope_ponderado"],
            Decimal("60"),
        )

    def test_listado_y_alertas_usan_el_mismo_calculo_combinado(self):
        kit = Kit.objects.create(
            nombre="Kit completo",
            modalidad="FIJO",
            cantidad_productos=12,
            precio=Decimal("42600"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=self.esquinero,
            cantidad=8,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=self.extension,
            cantidad=4,
        )

        recomendacion = recomendacion_kit(kit)

        self.assertTrue(recomendacion["disponible"])
        self.assertEqual(
            recomendacion["cantidad_total_calculada"],
            12,
        )
        self.assertEqual(
            recomendacion["precio_recomendado"],
            Decimal("42600"),
        )
        self.assertEqual(recomendacion["estado"], "OK")

    def test_api_informa_ahorro_frente_a_sumar_bloques(self):
        response = self.client.post(
            reverse("kits:recomendacion_fija"),
            data={
                "producto_id": [
                    str(self.esquinero.id),
                    str(self.extension.id),
                ],
                "cantidad": ["8", "4"],
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["cantidad_total"], 12)
        self.assertEqual(
            data["escenarios"]["recomendado"]["precio"],
            "42600.00",
        )
        self.assertEqual(
            data["escenarios"]["recomendado"]["referencia_separada"],
            "45900.00",
        )
        self.assertEqual(
            data["escenarios"]["recomendado"]["ahorro_combo"],
            "3300.00",
        )
