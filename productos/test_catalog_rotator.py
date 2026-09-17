import os
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from config.catalog_rotator_middleware import _kit_image_pools
from kits.models import Kit, KitComponente

from .image_models import ProductoImagen
from .models import Producto, TipoProducto


@override_settings(SECURE_SSL_REDIRECT=False)
class CatalogRotatorTests(TestCase):
    def setUp(self):
        self.entorno = patch.dict(os.environ, {"APP_ENV": "qa"})
        self.entorno.start()
        self.addCleanup(self.entorno.stop)

        self.tipo = TipoProducto.objects.create(
            nombre="Sensorial",
            activo=True,
        )
        self.productos = []
        for indice in range(1, 4):
            producto = Producto.objects.create(
                nombre=f"Sensorial {indice}",
                categoria="PRODUCTO",
                tipo=self.tipo,
                activo=True,
                solo_produccion=False,
            )
            self.productos.append(producto)
            for orden in (1, 2):
                ProductoImagen.objects.create(
                    producto=producto,
                    ambiente="qa",
                    file_id=f"qa-{indice}-{orden}",
                    url=f"https://example.com/qa-{indice}-{orden}.jpg",
                    thumbnail_url=f"https://example.com/qa-{indice}-{orden}-thumb.jpg",
                    orden=orden,
                )

        ProductoImagen.objects.create(
            producto=self.productos[0],
            ambiente="production",
            file_id="prod-no-mezclar",
            url="https://example.com/prod-no-mezclar.jpg",
            thumbnail_url="https://example.com/prod-no-mezclar-thumb.jpg",
            orden=1,
        )

        self.kit = Kit.objects.create(
            nombre="Kit sensorial rotativo",
            modalidad="FIJO",
            cantidad_productos=3,
            precio=25000,
            activo=True,
        )
        for producto in self.productos:
            KitComponente.objects.create(
                kit=self.kit,
                producto=producto,
                cantidad=1,
            )

    def test_pool_del_kit_incluye_mas_de_cuatro_fotos_solo_del_entorno(self):
        pools = _kit_image_pools()

        self.assertEqual(len(pools), 1)
        self.assertEqual(len(pools[0]), 6)
        urls = {foto["src"] for foto in pools[0]}
        self.assertIn("https://example.com/qa-1-1.jpg", urls)
        self.assertIn("https://example.com/qa-3-2.jpg", urls)
        self.assertNotIn("https://example.com/prod-no-mezclar.jpg", urls)

    def test_catalogo_inyecta_reglas_del_collage_sensorial(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "dv-sensory-grid")
        self.assertContains(response, "total === 4")
        self.assertContains(response, "total < 4")
        self.assertContains(response, "slotCursor")
        self.assertContains(response, 'data-category="sensorial"')
        self.assertContains(response, "https://example.com/qa-3-2.jpg")
        self.assertNotContains(response, "https://example.com/prod-no-mezclar.jpg")
