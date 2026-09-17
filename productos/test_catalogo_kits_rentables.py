import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from config.catalog_rotator_middleware import _kit_image_pools
from costos.models import ConfiguracionCostos
from kits.elegibilidad_catalogo import (
    adicional_producto_kit,
    costo_maximo_unitario,
    productos_elegibles_para_kit,
)
from kits.models import Kit

from .image_models import ProductoImagen
from .models import Producto, TipoProducto


@override_settings(SECURE_SSL_REDIRECT=False)
class CatalogoKitsRentablesTests(TestCase):
    def setUp(self):
        self.entorno = patch.dict(os.environ, {"APP_ENV": "qa"})
        self.entorno.start()
        self.addCleanup(self.entorno.stop)

        ConfiguracionCostos.objects.create(
            nombre="Costos prueba kits rentables",
            coste_plastico_kg=Decimal("10000"),
            coste_plastico_kg_cantidad=Decimal("10000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date.today(),
            activa=True,
        )

        self.tipo = TipoProducto.objects.create(
            nombre="Sensoriales rentables",
            activo=True,
        )
        self.economico = Producto.objects.create(
            nombre="Producto rentable",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("300"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            activo=True,
            solo_produccion=False,
        )
        self.caro = Producto.objects.create(
            nombre="Producto caro",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("500"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            activo=True,
            solo_produccion=False,
        )

        ProductoImagen.objects.create(
            producto=self.economico,
            ambiente="qa",
            file_id="rentable",
            url="https://example.com/rentable.jpg",
            thumbnail_url="https://example.com/rentable-thumb.jpg",
            orden=1,
        )
        ProductoImagen.objects.create(
            producto=self.caro,
            ambiente="qa",
            file_id="caro",
            url="https://example.com/caro.jpg",
            thumbnail_url="https://example.com/caro-thumb.jpg",
            orden=1,
        )

        self.kit = Kit.objects.create(
            nombre="2 sensoriales por 9000",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("9000"),
            activo=True,
        )

    def test_limite_y_adicional_conservan_margen_minimo(self):
        self.assertEqual(
            costo_maximo_unitario(self.kit),
            Decimal("3600"),
        )

        elegibles = productos_elegibles_para_kit(
            self.kit,
            [self.economico, self.caro],
        )

        self.assertEqual(elegibles, [self.economico])
        self.assertEqual(
            adicional_producto_kit(self.kit, self.economico),
            Decimal("0"),
        )
        self.assertEqual(
            adicional_producto_kit(self.kit, self.caro),
            Decimal("2000"),
        )

    def test_catalogo_muestra_incluidas_y_premium(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        kit_catalogo = response.context["kits"][0]

        self.assertEqual(kit_catalogo.catalogo_cantidad_opciones, 1)
        self.assertEqual(kit_catalogo.catalogo_cantidad_premium, 1)
        self.assertEqual(kit_catalogo.catalogo_cantidad_total, 2)

        nombres = [
            visual["producto"].nombre
            for visual in kit_catalogo.productos_visuales
        ]
        self.assertEqual(
            nombres,
            ["Producto rentable", "Producto caro"],
        )

        # Ambos siguen también a la venta como productos individuales.
        self.assertContains(response, "Producto rentable")
        self.assertContains(response, "Producto caro")
        self.assertContains(response, "algunas con adicional")
        self.assertContains(response, "Ver opciones")

    def test_rotador_del_kit_usa_todas_las_opciones_seleccionables(self):
        pools = _kit_image_pools()

        self.assertEqual(len(pools), 1)
        urls = {foto["src"] for foto in pools[0]}
        self.assertIn("https://example.com/rentable.jpg", urls)
        self.assertIn("https://example.com/caro.jpg", urls)

    def test_kit_con_todas_opciones_premium_sigue_publicado(self):
        self.economico.peso_gramos = Decimal("500")
        self.economico.save(update_fields=["peso_gramos"])

        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["kits"]), 1)
        kit_catalogo = response.context["kits"][0]
        self.assertEqual(kit_catalogo.catalogo_cantidad_opciones, 0)
        self.assertEqual(kit_catalogo.catalogo_cantidad_premium, 2)
        self.assertEqual(kit_catalogo.catalogo_cantidad_total, 2)
        self.assertContains(response, "2 sensoriales por 9000")

    def test_detalle_publico_muestra_incluidas_y_premium(self):
        response = self.client.get(
            reverse(
                "catalogo_kit_detalle",
                args=[self.kit.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Productos para elegir")
        self.assertContains(response, "Producto rentable")
        self.assertContains(response, "Producto caro")
        self.assertContains(response, "Incluido en el precio")
        self.assertContains(response, "Opción premium")
        self.assertContains(response, "+ $2000")
        self.assertContains(response, "https://example.com/rentable.jpg")
        self.assertContains(response, "https://example.com/caro.jpg")

    def test_catalogo_enlaza_al_detalle_publico_del_kit(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse(
                "catalogo_kit_detalle",
                args=[self.kit.id],
            ),
        )
        self.assertContains(response, "Ver opciones")
