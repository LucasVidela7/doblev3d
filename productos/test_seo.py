import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from costos.models import ConfiguracionCostos
from kits.models import Kit, KitComponente

from .image_models import ProductoImagen
from .models import Producto, TipoProducto


@override_settings(SECURE_SSL_REDIRECT=False)
class SEOTestCase(TestCase):
    def setUp(self):
        self.entorno = patch.dict(
            os.environ,
            {"APP_ENV": "qa"},
        )
        self.entorno.start()
        self.addCleanup(self.entorno.stop)

        ConfiguracionCostos.objects.create(
            nombre="SEO test",
            coste_plastico_kg=Decimal("1000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )

        self.tipo = TipoProducto.objects.create(
            nombre="Sensoriales",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Piña sensorial SEO",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=1,
            peso_gramos=Decimal("100"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            personalizable=False,
            activo=True,
            solo_produccion=False,
        )
        self.interno = Producto.objects.create(
            nombre="Pieza interna SEO",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=1,
            peso_gramos=Decimal("50"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            personalizable=False,
            activo=True,
            solo_produccion=True,
        )
        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="qa",
            file_id="seo-producto-qa",
            url="https://example.com/seo-producto.jpg",
            thumbnail_url="https://example.com/seo-producto-thumb.jpg",
            orden=1,
        )

        self.kit = Kit.objects.create(
            nombre="Kit sensorial SEO",
            modalidad="FIJO",
            cantidad_productos=1,
            precio=Decimal("5000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=self.kit,
            producto=self.producto,
            cantidad=1,
        )

    def test_portada_publica_canonical_y_organization_schema(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            '<link rel="canonical" href="http://testserver/">',
            html=True,
        )
        self.assertContains(
            response,
            "Doble V 3D | Productos y kits impresos en 3D",
        )
        self.assertContains(response, '"@type":"Organization"')
        self.assertContains(response, '"@type":"WebSite"')

    def test_producto_publica_product_offer_y_breadcrumb_schema(self):
        response = self.client.get(
            reverse(
                "catalogo_producto_detalle",
                args=[self.producto.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"@type":"Product"')
        self.assertContains(response, '"@type":"Offer"')
        self.assertContains(
            response,
            '"priceCurrency":"ARS"',
        )
        self.assertContains(
            response,
            '"@type":"BreadcrumbList"',
        )
        self.assertContains(
            response,
            self.producto.codigo,
        )

    def test_kit_publica_product_offer_y_breadcrumb_schema(self):
        response = self.client.get(
            reverse(
                "catalogo_kit_detalle",
                args=[self.kit.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '"@type":"Product"')
        self.assertContains(response, '"@type":"Offer"')
        self.assertContains(
            response,
            '"priceCurrency":"ARS"',
        )
        self.assertContains(
            response,
            '"@type":"BreadcrumbList"',
        )
        self.assertContains(response, self.kit.codigo)

    @override_settings(APP_ENV="production")
    def test_robots_produccion_publica_sitemap_y_bloquea_gestion(self):
        response = self.client.get(reverse("robots_txt"))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("Allow: /", body)
        self.assertIn("Disallow: /gestion/", body)
        self.assertIn(
            "Sitemap: http://testserver/sitemap.xml",
            body,
        )
        self.assertNotEqual(
            body.strip(),
            "User-agent: *\nDisallow: /",
        )

    @override_settings(APP_ENV="qa")
    def test_qa_bloquea_indexacion_globalmente(self):
        response = self.client.get(
            reverse(
                "catalogo_producto_detalle",
                args=[self.producto.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["X-Robots-Tag"],
            "noindex, nofollow",
        )

        robots = self.client.get(reverse("robots_txt"))
        self.assertEqual(
            robots.content.decode("utf-8"),
            "User-agent: *\nDisallow: /\n",
        )

    @override_settings(APP_ENV="production")
    def test_paginas_transaccionales_siguen_noindex_en_produccion(self):
        response = self.client.get(
            reverse("catalogo_arrepentimiento")
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["X-Robots-Tag"],
            "noindex, nofollow",
        )
        self.assertContains(
            response,
            'meta name="robots" content="noindex,follow"',
        )

    @override_settings(APP_ENV="production")
    def test_sitemap_incluye_catalogo_productos_y_kits_publicos(self):
        response = self.client.get(reverse("sitemap_xml"))

        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn(
            "http://testserver/productos/"
            + str(self.producto.id)
            + "/",
            body,
        )
        self.assertIn(
            "http://testserver/kits/"
            + str(self.kit.id)
            + "/",
            body,
        )
        self.assertNotIn(
            "http://testserver/productos/"
            + str(self.interno.id)
            + "/",
            body,
        )
        self.assertNotIn("/carrito/", body)
        self.assertNotIn("/solicitud/", body)
