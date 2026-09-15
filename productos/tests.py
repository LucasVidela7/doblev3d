from datetime import date
from decimal import Decimal

from django.test import RequestFactory, TestCase
from django.template.loader import render_to_string
from django.urls import reverse

from costos.models import ConfiguracionCostos

from .models import Producto, ProductoComponente, TipoProducto
from stock.models import MovimientoStock

from .views import _armar_producto, _guardar_producto_desde_post


class ProductoCompuestoTests(TestCase):
    def setUp(self):
        self.tipo = TipoProducto.objects.create(nombre="Test")

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
            tipo_fabricacion="SIMPLE",
            solo_produccion=True,
        )

    def test_compuesto_suma_tiempo_y_peso(self):
        cuerpo = self.pieza("Cuerpo", 2, 30, 100)
        tapa = self.pieza("Tapa", 0, 20, 12.5)
        producto = Producto.objects.create(
            nombre="Esquinero",
            categoria="PRODUCTO",
            tipo=self.tipo,
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            tipo_fabricacion="COMPUESTO",
        )
        ProductoComponente.objects.create(
            producto=producto,
            componente=cuerpo,
            cantidad=1,
        )
        ProductoComponente.objects.create(
            producto=producto,
            componente=tapa,
            cantidad=3,
        )
        producto.refresh_from_db()
        self.assertEqual(producto.horas, 3)
        self.assertEqual(producto.minutos, 30)
        self.assertEqual(producto.peso_gramos, Decimal("137.50"))

    def test_cambio_en_pieza_recalcula_padre(self):
        pieza = self.pieza("Pieza", 1, 0, 20)
        producto = Producto.objects.create(
            nombre="Compuesto",
            categoria="PRODUCTO",
            tipo=self.tipo,
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            tipo_fabricacion="COMPUESTO",
        )
        ProductoComponente.objects.create(
            producto=producto,
            componente=pieza,
            cantidad=2,
        )
        pieza.horas = 1
        pieza.minutos = 30
        pieza.peso_gramos = Decimal("25")
        pieza.save()
        producto.refresh_from_db()
        self.assertEqual(producto.horas, 3)
        self.assertEqual(producto.minutos, 0)
        self.assertEqual(producto.peso_gramos, Decimal("50.00"))

    def test_crear_piezas_inline_desde_compuesto(self):
        request = RequestFactory().post(
            "/productos/nuevo/",
            data={
                "nombre": "Kit carcasa",
                "categoria": "PRODUCTO",
                "tipo": str(self.tipo.id),
                "margen_ganancia": "60",
                "tipo_fabricacion": "COMPUESTO",
                "stock": "0",
                "requiere_impresion": "1",
                "activo": "1",
                "componente_modo": ["NUEVA", "NUEVA"],
                "componente_id": ["", ""],
                "componente_nombre": ["Cuerpo carcasa", "Tapa carcasa"],
                "componente_horas": ["2", "0"],
                "componente_minutos": ["30", "20"],
                "componente_peso": ["100", "12.5"],
                "componente_cantidad": ["1", "3"],
            },
        )

        producto, errores = _guardar_producto_desde_post(request)

        self.assertEqual(errores, [])
        self.assertIsNotNone(producto)

        piezas = Producto.objects.filter(solo_produccion=True).order_by("nombre")
        self.assertEqual(piezas.count(), 2)
        self.assertTrue(all(p.tipo_fabricacion == "SIMPLE" for p in piezas))
        self.assertTrue(all(p.requiere_impresion for p in piezas))

        producto.refresh_from_db()
        self.assertEqual(producto.componentes.count(), 2)
        self.assertEqual(producto.horas, 3)
        self.assertEqual(producto.minutos, 30)
        self.assertEqual(producto.peso_gramos, Decimal("137.50"))

    def test_pieza_inline_hereda_tipo_y_margen(self):
        request = RequestFactory().post(
            "/productos/nuevo/",
            data={
                "nombre": "Producto padre",
                "categoria": "PRODUCTO",
                "tipo": str(self.tipo.id),
                "margen_ganancia": "55",
                "tipo_fabricacion": "COMPUESTO",
                "stock": "0",
                "requiere_impresion": "1",
                "activo": "1",
                "componente_modo": ["NUEVA"],
                "componente_id": [""],
                "componente_nombre": ["Pieza hija"],
                "componente_horas": ["1"],
                "componente_minutos": ["15"],
                "componente_peso": ["20"],
                "componente_cantidad": ["1"],
            },
        )

        producto, errores = _guardar_producto_desde_post(request)
        self.assertEqual(errores, [])

        pieza = Producto.objects.get(nombre="Pieza hija")
        self.assertEqual(pieza.tipo_id, self.tipo.id)
        self.assertEqual(pieza.margen_ganancia, Decimal("55"))
        self.assertTrue(pieza.solo_produccion)
        self.assertEqual(pieza.stock, 0)
        self.assertFalse(pieza.personalizable)
        self.assertEqual(producto.componentes.get().componente_id, pieza.id)

    def test_precio_compuesto_se_calcula_desde_piezas_aunque_resumen_este_desactualizado(self):
        ConfiguracionCostos.objects.create(
            nombre="Test",
            coste_plastico_kg=Decimal("20000"),
            tasa_fallos=Decimal("10"),
            coste_luz_hora=Decimal("100"),
            coste_amortizacion_hora=Decimal("200"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )

        cuerpo = self.pieza("Cuerpo", 1, 30, 80)
        tapa = self.pieza("Tapa", 0, 20, 15)
        producto = Producto.objects.create(
            nombre="Compuesto con piezas nuevas",
            categoria="PRODUCTO",
            tipo=self.tipo,
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            tipo_fabricacion="COMPUESTO",
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

        costo_esperado = cuerpo.costo + tapa.costo * Decimal("2")
        seguro_esperado = cuerpo.seguro + tapa.seguro * Decimal("2")
        horas_esperadas = cuerpo.horas_totales + tapa.horas_totales * Decimal("2")

        Producto.objects.filter(pk=producto.pk).update(
            horas=0,
            minutos=0,
            peso_gramos=Decimal("0"),
        )
        producto.refresh_from_db()

        self.assertEqual(producto.horas_totales, horas_esperadas)
        self.assertEqual(producto.costo, costo_esperado)
        self.assertEqual(producto.seguro, seguro_esperado)
        self.assertGreater(producto.subtotal, Decimal("0"))

    def test_editar_producto_renderiza_margen_decimal_valido(self):
        producto = self.pieza(
            "Pieza con margen",
            1,
            0,
            20,
        )
        producto.margen_ganancia = Decimal("57.50")
        producto.save(
            update_fields=["margen_ganancia"]
        )
        request = RequestFactory().get(
            reverse(
                "productos:editar",
                args=[producto.id],
            )
        )

        html = render_to_string(
            "productos/formulario.html",
            {
                "request": request,
                "producto": producto,
                "tipos": [self.tipo],
                "categorias": Producto.CATEGORIAS,
                "tipos_fabricacion":
                    Producto.TIPOS_FABRICACION,
                "piezas": [],
                "componentes_actuales": [],
                "modo": "editar",
            },
        )

        self.assertIn(
            'value="57.50"',
            html,
        )
        self.assertNotIn(
            'value="57,50"',
            html,
        )

    def test_armar_compuesto_descuenta_piezas_y_suma_terminado(self):
        cuerpo = self.pieza("Cuerpo armado", 1, 0, 20)
        tapa = self.pieza("Tapa armada", 0, 30, 10)
        cuerpo.stock = 5
        tapa.stock = 8
        cuerpo.save(update_fields=["stock"])
        tapa.save(update_fields=["stock"])
        compuesto = Producto.objects.create(
            nombre="Producto armable",
            categoria="PRODUCTO",
            tipo=self.tipo,
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            tipo_fabricacion="COMPUESTO",
            stock=1,
        )
        ProductoComponente.objects.create(
            producto=compuesto,
            componente=cuerpo,
            cantidad=1,
        )
        ProductoComponente.objects.create(
            producto=compuesto,
            componente=tapa,
            cantidad=2,
        )

        self.assertEqual(compuesto.unidades_armables, 4)
        _armar_producto(compuesto.id, 3)

        cuerpo.refresh_from_db()
        tapa.refresh_from_db()
        compuesto.refresh_from_db()
        self.assertEqual(cuerpo.stock, 2)
        self.assertEqual(tapa.stock, 2)
        self.assertEqual(compuesto.stock, 4)
        self.assertEqual(
            MovimientoStock.objects.filter(
                tipo="SALIDA_ARMADO"
            ).count(),
            2,
        )
        self.assertEqual(
            MovimientoStock.objects.filter(
                producto=compuesto,
                tipo="ENTRADA_ARMADO",
                cantidad=3,
            ).count(),
            1,
        )

    def test_armado_sin_stock_no_modifica_ningun_producto(self):
        pieza = self.pieza("Pieza escasa", 1, 0, 20)
        pieza.stock = 1
        pieza.save(update_fields=["stock"])
        compuesto = Producto.objects.create(
            nombre="Compuesto sin stock",
            categoria="PRODUCTO",
            tipo=self.tipo,
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            tipo_fabricacion="COMPUESTO",
            stock=2,
        )
        ProductoComponente.objects.create(
            producto=compuesto,
            componente=pieza,
            cantidad=2,
        )

        with self.assertRaisesRegex(
            ValueError,
            "Stock insuficiente",
        ):
            _armar_producto(compuesto.id, 1)

        pieza.refresh_from_db()
        compuesto.refresh_from_db()
        self.assertEqual(pieza.stock, 1)
        self.assertEqual(compuesto.stock, 2)
        self.assertFalse(MovimientoStock.objects.exists())
