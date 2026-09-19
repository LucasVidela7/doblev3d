from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase

from calculadora.precios import (
    calcular_costo_productivo_producto,
    calcular_escenarios_kit_fijo,
    calcular_escenarios_kit_libre,
)
from calculadora.views import calculadora_precios
from costos.models import ConfiguracionCostos
from productos.models import Producto, TipoProducto


class FilamentoEconomicoCantidadTests(TestCase):
    def setUp(self):
        self.config = ConfiguracionCostos.objects.create(
            nombre="Costo doble de filamento",
            coste_plastico_kg=Decimal("20000"),
            coste_plastico_kg_cantidad=Decimal("14000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        self.tipo = TipoProducto.objects.create(
            nombre="Tipo cantidad",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Producto 100 gramos",
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

    def test_producto_individual_conserva_filamento_estandar(self):
        self.assertEqual(
            self.producto.costo,
            Decimal("2000"),
        )

    def test_hasta_cuatro_unidades_usa_filamento_estandar(self):
        calculo = calcular_costo_productivo_producto(
            self.producto,
            4,
        )

        self.assertFalse(calculo["filamento_economico"])
        self.assertEqual(
            calculo["precio_filamento_kg"],
            Decimal("20000"),
        )
        self.assertEqual(
            calculo["costo_material"],
            Decimal("2000"),
        )

    def test_desde_cinco_unidades_usa_filamento_economico(self):
        calculo = calcular_costo_productivo_producto(
            self.producto,
            5,
        )

        self.assertTrue(calculo["filamento_economico"])
        self.assertEqual(
            calculo["precio_filamento_kg"],
            Decimal("14000"),
        )
        self.assertEqual(
            calculo["costo_material"],
            Decimal("1400"),
        )

    def test_costo_economico_cero_vuelve_al_estandar(self):
        self.config.coste_plastico_kg_cantidad = Decimal("0")
        self.config.save(update_fields=["coste_plastico_kg_cantidad"])

        calculo = calcular_costo_productivo_producto(
            self.producto,
            20,
        )

        self.assertFalse(calculo["filamento_economico"])
        self.assertEqual(
            calculo["precio_filamento_kg"],
            Decimal("20000"),
        )

    def test_kit_fijo_usa_filamento_economico_aunque_haya_una_unidad(self):
        calculo = calcular_escenarios_kit_fijo(
            [
                {
                    "producto": self.producto,
                    "cantidad": 1,
                }
            ]
        )

        self.assertTrue(calculo["filamento_economico"])
        self.assertEqual(
            calculo["precio_filamento_kg"],
            Decimal("14000"),
        )
        self.assertEqual(
            calculo["costo_total"],
            Decimal("1400"),
        )

    def test_kit_libre_usa_filamento_economico(self):
        calculo = calcular_escenarios_kit_libre(
            [self.producto],
            2,
        )

        self.assertTrue(calculo["filamento_economico"])
        self.assertEqual(
            calculo["precio_filamento_kg"],
            Decimal("14000"),
        )
        self.assertEqual(
            calculo["costo_promedio"],
            Decimal("2800"),
        )

    def test_calculadora_cambia_exactamente_entre_x4_y_x5(self):
        request = RequestFactory().post(
            "/calculadora/",
            data={
                "modo": "existente",
                "producto_id": str(self.producto.id),
                "cantidad": "5",
                "cantidades_lista": "4,5",
            },
        )

        with patch("calculadora.views.render") as render_mock:
            render_mock.return_value = HttpResponse()
            calculadora_precios(request)

        contexto = render_mock.call_args.args[2]
        resultado = contexto["resultado_existente"]

        self.assertTrue(
            resultado["catalogo"]["filamento_economico"]
        )
        self.assertEqual(
            resultado["catalogo"]["precio_filamento_kg"],
            Decimal("14000"),
        )

        fila_x4, fila_x5 = resultado["lista_precios"]
        self.assertFalse(
            fila_x4["filamento_economico"]
        )
        self.assertTrue(
            fila_x5["filamento_economico"]
        )
