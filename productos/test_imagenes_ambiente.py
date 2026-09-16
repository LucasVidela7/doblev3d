import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .image_models import ProductoImagen
from .imagekit_service import carpeta_producto_imagekit
from .models import Producto, TipoProducto


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
@patch.dict(os.environ, {"APP_ENV": "qa"}, clear=False)
class ProductoImagenAmbienteTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="tester-imagenes-ambiente",
            password="test",
        )
        self.client.force_login(usuario)
        tipo = TipoProducto.objects.create(nombre="Sensorial ambiente")
        self.producto = Producto.objects.create(
            nombre="Producto ambiente",
            categoria="PRODUCTO",
            tipo=tipo,
            requiere_impresion=False,
            margen_ganancia=50,
            activo=True,
        )

    def _imagen(self, ambiente, sufijo, orden=1):
        return ProductoImagen.objects.create(
            producto=self.producto,
            ambiente=ambiente,
            file_id=f"{ambiente}-{sufijo}",
            url=f"https://ik.imagekit.io/demo/{ambiente}-{sufijo}.jpg",
            thumbnail_url=f"https://ik.imagekit.io/demo/thumb-{ambiente}-{sufijo}.jpg",
            orden=orden,
        )

    def test_mismo_producto_puede_tener_principal_separada_por_ambiente(self):
        qa = self._imagen("qa", "uno")
        production = self._imagen("production", "uno")

        self.assertEqual(qa.orden, 1)
        self.assertEqual(production.orden, 1)
        self.assertEqual(ProductoImagen.objects.count(), 2)

    def test_qa_solo_muestra_sus_fotos(self):
        self._imagen("qa", "visible")
        self._imagen("production", "oculta")

        response = self.client.get(
            reverse("productos:imagenes", args=[self.producto.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "thumb-qa-visible.jpg")
        self.assertNotContains(response, "thumb-production-oculta.jpg")
        self.assertContains(response, "1/2 fotos cargadas")

    @patch("productos.imagenes_views.eliminar_imagen_imagekit")
    def test_qa_no_puede_eliminar_foto_de_production(self, eliminar_mock):
        production = self._imagen("production", "protegida")

        response = self.client.post(
            reverse(
                "productos:imagen_eliminar",
                args=[self.producto.id, production.id],
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(ProductoImagen.objects.filter(pk=production.pk).exists())
        eliminar_mock.assert_not_called()

    @patch.dict(
        os.environ,
        {
            "APP_ENV": "qa",
            "IMAGEKIT_FOLDER_ROOT": "/doblev3d",
        },
        clear=False,
    )
    def test_carpeta_imagekit_incluye_ambiente(self):
        self.assertEqual(
            carpeta_producto_imagekit(self.producto),
            f"/doblev3d/qa/productos/{self.producto.id}",
        )
