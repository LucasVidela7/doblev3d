import os
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from kits.models import Kit, KitComponente

from .image_models import ProductoImagen
from .models import Producto, TipoProducto


@override_settings(SECURE_SSL_REDIRECT=False)
class CatalogoPublicoTests(TestCase):
    def setUp(self):
        self.entorno = patch.dict(os.environ, {"APP_ENV": "qa"})
        self.entorno.start()
        self.addCleanup(self.entorno.stop)

        self.tipo = TipoProducto.objects.create(
            nombre="Sensoriales",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Piña sensorial",
            categoria="PRODUCTO",
            tipo=self.tipo,
            activo=True,
            solo_produccion=False,
        )
        self.oculto = Producto.objects.create(
            nombre="Pieza interna",
            categoria="PRODUCTO",
            tipo=self.tipo,
            activo=True,
            solo_produccion=True,
        )

        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="qa",
            file_id="qa-pina",
            url="https://example.com/qa-pina.jpg",
            thumbnail_url="https://example.com/qa-pina-thumb.jpg",
            orden=1,
        )
        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="production",
            file_id="prod-pina",
            url="https://example.com/prod-pina.jpg",
            thumbnail_url="https://example.com/prod-pina-thumb.jpg",
            orden=1,
        )

        self.kit = Kit.objects.create(
            nombre="Kit sensorial",
            modalidad="FIJO",
            cantidad_productos=1,
            precio=12000,
            activo=True,
        )
        KitComponente.objects.create(
            kit=self.kit,
            producto=self.producto,
            cantidad=1,
        )

    def test_catalogo_es_publico_y_muestra_solo_oferta_comercial(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Piña sensorial")
        self.assertContains(response, "Kit sensorial")
        self.assertNotContains(response, "Pieza interna")

    def test_catalogo_respeta_aislamiento_de_imagenes_qa(self):
        response = self.client.get(reverse("catalogo"))

        self.assertContains(
            response,
            "https://example.com/qa-pina.jpg",
        )
        self.assertNotContains(
            response,
            "https://example.com/prod-pina.jpg",
        )
