from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from calculadora.precios import calcular_costo_productivo_producto

from .models import (
    ConfiguracionCatalogo,
    Insumo,
    Producto,
    ProductoComponente,
    ProductoInsumo,
    TipoProducto,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class ProductoInsumosTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="qa-producto-insumos",
            password="test",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.tipo = TipoProducto.objects.create(
            nombre="Sensorial",
            activo=True,
        )
        self.config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        self.config.incremento_insumos_por_defecto = Decimal("15.00")
        self.config.redondeo_precio_producto = 100
        self.config.save(
            update_fields=[
                "incremento_insumos_por_defecto",
                "redondeo_precio_producto",
            ]
        )
        self.argolla = Insumo.objects.create(
            nombre="Argolla llavero",
            tipo_uso="PRODUCTO",
            unidad_medida="UNIDAD",
            precio_compra=Decimal("8000"),
            cantidad_compra=Decimal("100"),
            stock=Decimal("100"),
        )

    def _producto(self, nombre="Llavero", margen="50"):
        return Producto.objects.create(
            nombre=nombre,
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=0,
            peso_gramos=0,
            margen_ganancia=Decimal(margen),
            requiere_impresion=False,
            personalizable=False,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
        )

    def test_insumo_directo_entra_en_costo_y_precio(self):
        producto = self._producto()
        ProductoInsumo.objects.create(
            producto=producto,
            insumo=self.argolla,
            cantidad=Decimal("1"),
        )

        self.assertEqual(
            producto.costo_insumos_directos,
            Decimal("92.0000"),
        )
        self.assertEqual(
            producto.costo_productivo_total,
            Decimal("92.0000"),
        )
        self.assertEqual(producto.subtotal, Decimal("200"))
        self.assertEqual(producto.ganancia, Decimal("108.0000"))

    def test_cambio_de_precio_del_insumo_recalcula_producto_sin_reasignar(self):
        producto = self._producto()
        ProductoInsumo.objects.create(
            producto=producto,
            insumo=self.argolla,
            cantidad=Decimal("1"),
        )
        self.assertEqual(producto.subtotal, Decimal("200"))

        self.argolla.precio_compra = Decimal("10000")
        self.argolla.save(update_fields=["precio_compra", "actualizado_en"])

        producto.refresh_from_db()
        self.assertEqual(
            producto.costo_insumos_directos,
            Decimal("115.0000"),
        )
        self.assertEqual(producto.subtotal, Decimal("300"))

    def test_calculadora_incluye_insumos(self):
        producto = self._producto()
        ProductoInsumo.objects.create(
            producto=producto,
            insumo=self.argolla,
            cantidad=Decimal("2"),
        )

        desglose = calcular_costo_productivo_producto(producto)

        self.assertEqual(desglose["costo_insumos"], Decimal("184.0000"))
        self.assertEqual(
            desglose["costo_productivo"],
            Decimal("184.0000"),
        )

    def test_compuesto_suma_insumos_de_piezas_y_propios(self):
        pieza = self._producto("Pieza con argolla")
        ProductoInsumo.objects.create(
            producto=pieza,
            insumo=self.argolla,
            cantidad=Decimal("1"),
        )
        iman = Insumo.objects.create(
            nombre="Imán",
            tipo_uso="PRODUCTO",
            precio_compra=Decimal("4000"),
            cantidad_compra=Decimal("100"),
            incremento_personalizado=Decimal("20"),
        )
        compuesto = Producto.objects.create(
            nombre="Producto compuesto",
            categoria="PRODUCTO",
            tipo=self.tipo,
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            tipo_fabricacion="COMPUESTO",
            stock=0,
            activo=True,
        )
        ProductoComponente.objects.create(
            producto=compuesto,
            componente=pieza,
            cantidad=2,
        )
        ProductoInsumo.objects.create(
            producto=compuesto,
            insumo=iman,
            cantidad=Decimal("1"),
        )

        self.assertEqual(
            compuesto.costo_insumos_componentes,
            Decimal("184.0000"),
        )
        self.assertEqual(
            compuesto.costo_insumos_directos,
            Decimal("48.0"),
        )
        self.assertEqual(
            compuesto.costo_insumos_total,
            Decimal("232.0000"),
        )

    def test_formulario_guarda_insumo_y_cantidad(self):
        response = self.client.post(
            reverse("productos:nuevo"),
            {
                "nombre": "Llavero prueba",
                "categoria": "PRODUCTO",
                "tipo": str(self.tipo.id),
                "margen_ganancia": "50",
                "tipo_fabricacion": "SIMPLE",
                "horas": "0",
                "minutos": "0",
                "peso_gramos": "0",
                "stock": "0",
                "activo": "1",
                "insumo_id": [str(self.argolla.id)],
                "insumo_cantidad": ["1.5"],
            },
        )

        producto = Producto.objects.get(nombre="Llavero prueba")
        self.assertRedirects(
            response,
            reverse("productos:detalle", args=[producto.id]),
        )
        relacion = ProductoInsumo.objects.get(producto=producto)
        self.assertEqual(relacion.insumo, self.argolla)
        self.assertEqual(relacion.cantidad, Decimal("1.500"))

    def test_detalle_muestra_desglose_de_insumos(self):
        producto = self._producto()
        ProductoInsumo.objects.create(
            producto=producto,
            insumo=self.argolla,
            cantidad=Decimal("1"),
        )

        response = self.client.get(
            reverse("productos:detalle", args=[producto.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "INSUMOS DIRECTOS")
        self.assertContains(response, "Argolla llavero")
        self.assertContains(response, "Total de insumos por unidad")

    def test_no_permite_asignar_empaque_como_insumo_directo(self):
        bolsa = Insumo.objects.create(
            nombre="Doypack",
            tipo_uso="EMPAQUE",
            precio_compra=Decimal("5000"),
            cantidad_compra=Decimal("50"),
        )

        response = self.client.post(
            reverse("productos:nuevo"),
            {
                "nombre": "Producto inválido",
                "categoria": "PRODUCTO",
                "tipo": str(self.tipo.id),
                "margen_ganancia": "50",
                "tipo_fabricacion": "SIMPLE",
                "horas": "0",
                "minutos": "0",
                "peso_gramos": "0",
                "stock": "0",
                "activo": "1",
                "insumo_id": [str(bolsa.id)],
                "insumo_cantidad": ["1"],
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            Producto.objects.filter(nombre="Producto inválido").exists()
        )
        self.assertContains(
            response,
            "no es válido para productos",
        )
