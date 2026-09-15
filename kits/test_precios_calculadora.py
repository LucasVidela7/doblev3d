from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import resolve, reverse

from calculadora.precios import (
    calcular_escenarios_kit_fijo,
    calcular_escenarios_kit_libre,
    calcular_escenarios_producto,
    redondear_arriba,
)
from costos.models import ConfiguracionCostos
from productos.models import Producto, TipoProducto

from .models import Kit


class PreciosKitCalculadoraTests(TestCase):
    def setUp(self):
        ConfiguracionCostos.objects.create(
            nombre="Test precios kit",
            coste_plastico_kg=Decimal("1000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        self.tipo = TipoProducto.objects.create(
            nombre="Kit test",
            activo=True,
        )

    def crear_producto(
        self,
        nombre,
        peso,
        margen,
        solo_produccion=False,
    ):
        return Producto.objects.create(
            nombre=nombre,
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=0,
            peso_gramos=Decimal(str(peso)),
            margen_ganancia=Decimal(str(margen)),
            requiere_impresion=True,
            personalizable=False,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=solo_produccion,
        )

    def test_kit_fijo_suma_los_tres_escenarios_de_la_calculadora(self):
        producto_a = self.crear_producto(
            "Producto A",
            1000,
            70,
        )
        producto_b = self.crear_producto(
            "Producto B",
            500,
            45,
        )

        componentes = [
            {"producto": producto_a, "cantidad": 10},
            {"producto": producto_b, "cantidad": 3},
        ]

        resultado = calcular_escenarios_kit_fijo(
            componentes
        )
        calculo_a = calcular_escenarios_producto(
            producto_a,
            10,
        )
        calculo_b = calcular_escenarios_producto(
            producto_b,
            3,
        )

        for clave in (
            "agresivo",
            "recomendado",
            "conservador",
        ):
            esperado = (
                calculo_a["escenarios"][clave][
                    "total_recomendado"
                ]
                + calculo_b["escenarios"][clave][
                    "total_recomendado"
                ]
            )
            self.assertEqual(
                resultado["escenarios"][clave][
                    "total_recomendado"
                ],
                esperado,
            )

        self.assertLessEqual(
            resultado["escenarios"]["agresivo"][
                "total_recomendado"
            ],
            resultado["escenarios"]["recomendado"][
                "total_recomendado"
            ],
        )
        self.assertLessEqual(
            resultado["escenarios"]["recomendado"][
                "total_recomendado"
            ],
            resultado["escenarios"]["conservador"][
                "total_recomendado"
            ],
        )

    def test_kit_libre_combina_promedio_y_peor_caso(self):
        economico = self.crear_producto(
            "Económico",
            500,
            45,
        )
        exigente = self.crear_producto(
            "Exigente",
            2000,
            70,
        )
        cantidad = 4

        resultado = calcular_escenarios_kit_libre(
            [economico, exigente],
            cantidad,
        )
        calculo_economico = calcular_escenarios_producto(
            economico,
            cantidad,
        )
        calculo_exigente = calcular_escenarios_producto(
            exigente,
            cantidad,
        )

        agresivos = [
            calculo_economico["escenarios"]["agresivo"][
                "total_recomendado"
            ],
            calculo_exigente["escenarios"]["agresivo"][
                "total_recomendado"
            ],
        ]
        recomendados = [
            calculo_economico["escenarios"]["recomendado"][
                "total_recomendado"
            ],
            calculo_exigente["escenarios"]["recomendado"][
                "total_recomendado"
            ],
        ]
        conservadores = [
            calculo_economico["escenarios"]["conservador"][
                "total_recomendado"
            ],
            calculo_exigente["escenarios"]["conservador"][
                "total_recomendado"
            ],
        ]

        esperado_agresivo = redondear_arriba(
            sum(agresivos, Decimal("0")) / Decimal("2")
        )
        esperado_recomendado = max(
            redondear_arriba(
                sum(recomendados, Decimal("0")) / Decimal("2")
            ),
            max(agresivos),
        )
        esperado_conservador = max(conservadores)

        self.assertEqual(
            resultado["escenarios"]["agresivo"][
                "total_recomendado"
            ],
            esperado_agresivo,
        )
        self.assertEqual(
            resultado["escenarios"]["recomendado"][
                "total_recomendado"
            ],
            esperado_recomendado,
        )
        self.assertEqual(
            resultado["escenarios"]["conservador"][
                "total_recomendado"
            ],
            esperado_conservador,
        )
        self.assertLessEqual(
            esperado_agresivo,
            esperado_recomendado,
        )
        self.assertLessEqual(
            esperado_recomendado,
            esperado_conservador,
        )

    def test_api_fija_devuelve_agresivo_recomendado_y_conservador(self):
        producto = self.crear_producto(
            "Producto API",
            1000,
            70,
        )

        respuesta = self.client.post(
            reverse("kits:recomendacion_fija"),
            data={
                "producto_id": [str(producto.id)],
                "cantidad": ["10"],
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        data = respuesta.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["tipo"], "FIJO")
        self.assertEqual(
            set(data["escenarios"]),
            {"agresivo", "recomendado", "conservador"},
        )
        self.assertEqual(data["margen_piso"], "22.5")
        self.assertGreater(
            Decimal(data["escenarios"]["recomendado"]["precio"]),
            Decimal(data["costo_total"]),
        )

    def test_api_fija_agrupa_producto_repetido_antes_de_calcular(self):
        producto = self.crear_producto(
            "Producto repetido",
            800,
            60,
        )

        respuesta = self.client.post(
            reverse("kits:recomendacion_fija"),
            data={
                "producto_id": [
                    str(producto.id),
                    str(producto.id),
                ],
                "cantidad": ["2", "3"],
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        data = respuesta.json()
        esperado = calcular_escenarios_producto(
            producto,
            5,
        )["escenarios"]["recomendado"][
            "total_recomendado"
        ]

        self.assertEqual(
            Decimal(data["escenarios"]["recomendado"]["precio"]),
            esperado,
        )

    def test_api_libre_devuelve_promedio_peor_caso_y_tres_escenarios(self):
        self.crear_producto(
            "Producto libre A",
            500,
            45,
        )
        self.crear_producto(
            "Producto libre B",
            2000,
            70,
        )
        self.crear_producto(
            "Pieza interna",
            10000,
            90,
            solo_produccion=True,
        )

        respuesta = self.client.post(
            reverse("kits:recomendacion_libre"),
            data={
                "tipo_producto": str(self.tipo.id),
                "cantidad": "4",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        data = respuesta.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["tipo"], "LIBRE_CATEGORIA")
        self.assertEqual(data["productos_categoria"], 2)
        self.assertEqual(
            set(data["escenarios"]),
            {"agresivo", "recomendado", "conservador"},
        )
        self.assertIn(
            "margen_peor_caso",
            data["escenarios"]["recomendado"],
        )
        self.assertGreaterEqual(
            Decimal(data["escenarios"]["recomendado"]["precio"]),
            Decimal(data["escenarios"]["agresivo"]["precio"]),
        )
        self.assertGreaterEqual(
            Decimal(data["escenarios"]["conservador"]["precio"]),
            Decimal(data["escenarios"]["recomendado"]["precio"]),
        )

    def test_nuevo_y_editar_cargan_interfaz_de_tres_escenarios(self):
        kit = Kit.objects.create(
            nombre="Kit edición escenarios",
            modalidad="FIJO",
            cantidad_productos=1,
            precio=Decimal("1000"),
            activo=True,
        )

        respuestas = (
            self.client.get(reverse("kits:nuevo")),
            self.client.get(
                reverse("kits:editar", args=[kit.id])
            ),
        )

        for respuesta in respuestas:
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(
                respuesta,
                "kits/precios_fijos.css",
            )
            self.assertContains(
                respuesta,
                "kits/precios_fijos.js",
            )
            self.assertContains(
                respuesta,
                reverse("kits:recomendacion_fija"),
            )
            self.assertContains(
                respuesta,
                reverse("kits:recomendacion_libre"),
            )

    def test_rutas_recomendacion(self):
        self.assertEqual(
            resolve(
                "/kits/recomendacion-fija/"
            ).view_name,
            "kits:recomendacion_fija",
        )
        self.assertEqual(
            resolve(
                "/kits/recomendacion-libre/"
            ).view_name,
            "kits:recomendacion_libre",
        )
