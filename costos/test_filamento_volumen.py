from datetime import date
from decimal import Decimal

from django.test import TestCase

from .models import ConfiguracionCostos, TramoCostoFilamento


class TramosFilamentoTests(TestCase):
    def setUp(self):
        self.config = ConfiguracionCostos.objects.create(
            nombre="Costos volumen",
            coste_plastico_kg=Decimal("20000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        TramoCostoFilamento.objects.create(
            configuracion=self.config,
            desde_gramos=Decimal("1000"),
            coste_plastico_kg=Decimal("16000"),
            activo=True,
        )
        TramoCostoFilamento.objects.create(
            configuracion=self.config,
            desde_gramos=Decimal("5000"),
            coste_plastico_kg=Decimal("14000"),
            activo=True,
        )

    def test_antes_del_primer_tramo_usa_precio_estandar(self):
        self.assertEqual(
            self.config.precio_filamento_para_gramos(999),
            Decimal("20000"),
        )

    def test_aplica_el_mejor_tramo_alcanzado(self):
        self.assertEqual(
            self.config.precio_filamento_para_gramos(1000),
            Decimal("16000"),
        )
        self.assertEqual(
            self.config.precio_filamento_para_gramos(4999),
            Decimal("16000"),
        )
        self.assertEqual(
            self.config.precio_filamento_para_gramos(5000),
            Decimal("14000"),
        )
        self.assertEqual(
            self.config.precio_filamento_para_gramos(12000),
            Decimal("14000"),
        )

    def test_tramo_mas_caro_no_hace_subir_el_costo(self):
        TramoCostoFilamento.objects.create(
            configuracion=self.config,
            desde_gramos=Decimal("10000"),
            coste_plastico_kg=Decimal("25000"),
            activo=True,
        )

        self.assertEqual(
            self.config.precio_filamento_para_gramos(10000),
            Decimal("14000"),
        )

    def test_tramo_inactivo_no_se_aplica(self):
        TramoCostoFilamento.objects.filter(
            desde_gramos=Decimal("1000")
        ).update(activo=False)

        self.assertEqual(
            self.config.precio_filamento_para_gramos(1200),
            Decimal("20000"),
        )
