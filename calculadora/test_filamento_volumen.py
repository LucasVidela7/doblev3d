from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from costos.models import ConfiguracionCostos, TramoCostoFilamento
from productos.models import Producto, TipoProducto

from .precios import (
    calcular_escenarios_kit_fijo,
    calcular_escenarios_kit_libre,
    calcular_escenarios_producto,
    desglose_productivo,
)


class FilamentoVolumenCalculadoraTests(TestCase):
    def setUp(self):
        self.config = ConfiguracionCostos.objects.create(
            nombre="Costos calculadora",
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
        self.tipo = TipoProducto.objects.create(
            nombre="Volumen",
            activo=True,
        )

    def crear_producto(self, nombre, peso, margen="60"):
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

    def test_producto_individual_conserva_coste_estandar(self):
        producto = self.crear_producto("Individual", 100)

        self.assertEqual(producto.costo, Decimal("2000"))
        self.assertEqual(producto.subtotal, Decimal("5000"))

        desglose = desglose_productivo(producto, 1)

        self.assertEqual(
            desglose["precio_filamento_kg"],
            Decimal("20000"),
        )
        self.assertFalse(desglose["usa_filamento_volumen"])
        self.assertEqual(producto.subtotal, Decimal("5000"))

    def test_calculadora_aplica_volumen_segun_gramos_totales(self):
        producto = self.crear_producto("Mayorista", 100)

        nueve = desglose_productivo(producto, 9)
        diez = desglose_productivo(producto, 10)
        cincuenta = desglose_productivo(producto, 50)

        self.assertEqual(
            nueve["precio_filamento_kg"],
            Decimal("20000"),
        )
        self.assertEqual(
            diez["precio_filamento_kg"],
            Decimal("16000"),
        )
        self.assertEqual(
            cincuenta["precio_filamento_kg"],
            Decimal("14000"),
        )
        self.assertEqual(
            diez["costo_material"],
            Decimal("1600"),
        )
        self.assertEqual(
            cincuenta["costo_material"],
            Decimal("1400"),
        )

    def test_escenarios_producto_usan_costo_de_volumen(self):
        producto = self.crear_producto("Escenarios", 100)

        calculo = calcular_escenarios_producto(producto, 10)

        self.assertTrue(calculo["usa_filamento_volumen"])
        self.assertEqual(
            calculo["precio_filamento_kg"],
            Decimal("16000"),
        )
        self.assertEqual(
            calculo["costo_productivo_total"],
            Decimal("16000"),
        )

    def test_kit_fijo_elige_tramo_por_peso_de_toda_la_composicion(self):
        producto_a = self.crear_producto("A", 600)
        producto_b = self.crear_producto("B", 500)

        # Cada producto por separado queda debajo de 1 kg, pero el kit suma
        # 1,1 kg. El tramo debe aplicarse a toda la composición.
        calculo = calcular_escenarios_kit_fijo(
            [
                {"producto": producto_a, "cantidad": 1},
                {"producto": producto_b, "cantidad": 1},
            ]
        )

        self.assertTrue(calculo["usa_filamento_volumen"])
        self.assertEqual(
            calculo["peso_total_gramos"],
            Decimal("1100"),
        )
        self.assertEqual(
            calculo["precio_filamento_kg"],
            Decimal("16000"),
        )
        self.assertEqual(
            calculo["costo_total"],
            Decimal("17600"),
        )

    def test_kit_libre_hereda_la_misma_logica_de_volumen(self):
        producto_a = self.crear_producto("Liviano", 100)
        producto_b = self.crear_producto("Pesado", 200)

        calculo = calcular_escenarios_kit_libre(
            [producto_a, producto_b],
            10,
        )

        self.assertTrue(
            all(
                item["usa_filamento_volumen"]
                for item in calculo["productos"]
            )
        )
        self.assertEqual(
            calculo["productos"][0]["precio_filamento_kg"],
            Decimal("16000"),
        )
        self.assertEqual(
            calculo["productos"][1]["precio_filamento_kg"],
            Decimal("16000"),
        )

    def test_vista_calculadora_existente_usa_el_tramo(self):
        producto = self.crear_producto("Vista", 100)

        respuesta = self.client.post(
            reverse("calculadora:precios"),
            data={
                "modo": "existente",
                "producto_id": str(producto.id),
                "cantidad": "10",
                "cantidades_lista": "9,10,50",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        resultado = respuesta.context["resultado_existente"]
        self.assertEqual(
            resultado["desglose"]["precio_filamento_kg"],
            Decimal("16000"),
        )
        self.assertTrue(
            resultado["desglose"]["usa_filamento_volumen"]
        )
        self.assertEqual(
            resultado["lista_escenarios"][0]["desglose"][
                "precio_filamento_kg"
            ],
            Decimal("20000"),
        )
        self.assertEqual(
            resultado["lista_escenarios"][1]["desglose"][
                "precio_filamento_kg"
            ],
            Decimal("16000"),
        )
        self.assertEqual(
            resultado["lista_escenarios"][2]["desglose"][
                "precio_filamento_kg"
            ],
            Decimal("14000"),
        )
