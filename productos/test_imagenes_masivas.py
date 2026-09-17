import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .image_models import ProductoImagen
from .models import Producto, TipoProducto


TEST_STORAGES = {
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    }
}


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
    STORAGES=TEST_STORAGES,
)
class CargaMasivaImagenesTests(TestCase):
    def setUp(self):
        self.entorno = patch.dict(os.environ, {"APP_ENV": "qa"})
        self.entorno.start()
        self.addCleanup(self.entorno.stop)

        usuario = get_user_model().objects.create_user(
            username="tester-masivo",
            password="test",
        )
        self.client.force_login(usuario)

        tipo = TipoProducto.objects.create(nombre="Sensorial")
        self.producto = Producto.objects.create(
            nombre="Piña sensorial",
            categoria="PRODUCTO",
            tipo=tipo,
            horas=0,
            minutos=0,
            peso_gramos=0,
            margen_ganancia=60,
            requiere_impresion=False,
            activo=True,
        )
        self.pieza = Producto.objects.create(
            nombre="Pieza interna",
            categoria="PRODUCTO",
            tipo=tipo,
            horas=0,
            minutos=0,
            peso_gramos=0,
            margen_ganancia=60,
            requiere_impresion=False,
            activo=True,
            solo_produccion=True,
        )
        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="qa",
            file_id="masiva-qa",
            url="https://ik.imagekit.io/demo/masiva-qa.jpg",
            orden=1,
        )
        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="production",
            file_id="masiva-prod",
            url="https://ik.imagekit.io/demo/masiva-prod.jpg",
            orden=1,
        )

    def test_pantalla_masiva_lista_productos_y_cuenta_fotos_del_entorno(self):
        response = self.client.get(reverse("productos:imagenes_masivas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Carga masiva de fotos")
        self.assertContains(response, self.producto.codigo)
        self.assertContains(response, "Piña sensorial")
        self.assertNotContains(response, "Pieza interna")

        producto_json = next(
            item
            for item in response.context["productos_json"]
            if item["id"] == self.producto.id
        )
        self.assertEqual(producto_json["fotos"], 1)

    def test_lista_productos_muestra_acceso_a_carga_masiva(self):
        response = self.client.get(reverse("productos:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CARGA MASIVA")
        self.assertContains(response, reverse("productos:imagenes_masivas"))
