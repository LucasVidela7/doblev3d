import os
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from kits.models import Kit, KitComponente

from .image_models import ProductoImagen
from .models import Producto, TipoProducto


@override_settings(SECURE_SSL_REDIRECT=False)
class CatalogoRotacionFotosTests(TestCase):
    def setUp(self):
        self.entorno = patch.dict(os.environ, {"APP_ENV": "qa"})
        self.entorno.start()
        self.addCleanup(self.entorno.stop)

        tipo = TipoProducto.objects.create(nombre="Sensorial", activo=True)
        self.producto = Producto.objects.create(
            nombre="Cubo didáctico",
            categoria="PRODUCTO",
            tipo=tipo,
            activo=True,
            solo_produccion=False,
        )
        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="qa",
            file_id="cubo-principal",
            url="https://example.com/cubo-1.jpg",
            orden=1,
        )
        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="qa",
            file_id="cubo-secundaria",
            url="https://example.com/cubo-2.jpg",
            orden=2,
        )
        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="production",
            file_id="cubo-production",
            url="https://example.com/cubo-production.jpg",
            orden=2,
        )

        self.kit = Kit.objects.create(
            nombre="Cubo didáctico x8",
            modalidad="FIJO",
            cantidad_productos=8,
            precio=52000,
            activo=True,
        )
        KitComponente.objects.create(
            kit=self.kit,
            producto=self.producto,
            cantidad=8,
        )

    def test_catalogo_inyecta_rotador_y_dos_fotos_del_producto(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dv-catalog-rotator-script"')
        self.assertContains(response, "https://example.com/cubo-1.jpg")
        self.assertContains(response, "https://example.com/cubo-2.jpg")
        self.assertNotContains(response, "https://example.com/cubo-production.jpg")
        self.assertContains(response, "window.setInterval")

    def test_kit_de_un_solo_producto_se_convierte_en_imagen_completa(self):
        response = self.client.get(reverse("catalogo"))
        html = response.content.decode()

        self.assertIn(".catalog-item[data-kind=\"kit\"] .media", html)
        self.assertIn("buildRotator(media, slides)", html)
        self.assertIn("media.querySelectorAll(':scope > img, :scope > .kit-collage')", html)
