from decimal import Decimal

from django.test import TestCase

from .models import Producto, ProductoComponente, TipoProducto


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
