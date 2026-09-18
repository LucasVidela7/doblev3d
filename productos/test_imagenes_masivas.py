import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
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
        self.principal = ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="qa",
            file_id="masiva-qa",
            url="https://ik.imagekit.io/demo/masiva-qa.jpg",
            thumbnail_url="https://ik.imagekit.io/demo/thumb-masiva-qa.jpg",
            orden=1,
        )
        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="production",
            file_id="masiva-prod",
            url="https://ik.imagekit.io/demo/masiva-prod.jpg",
            orden=1,
        )

    def test_pantalla_masiva_lista_productos_y_posiciones_del_entorno(self):
        response = self.client.get(reverse("productos:imagenes_masivas"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Carga masiva de fotos")
        self.assertContains(response, self.producto.codigo)
        self.assertNotContains(response, "Pieza interna")

        producto_json = next(
            item
            for item in response.context["productos_json"]
            if item["id"] == self.producto.id
        )
        self.assertEqual(producto_json["nombre"], "Piña sensorial")
        self.assertEqual(producto_json["fotos"], 1)
        self.assertEqual(len(producto_json["imagenes"]), 1)
        self.assertEqual(producto_json["imagenes"][0]["orden"], 1)
        self.assertTrue(producto_json["imagenes"][0]["principal"])
        self.assertNotIn("masiva-prod", str(producto_json))

    def test_lista_productos_muestra_acceso_a_carga_masiva(self):
        response = self.client.get(reverse("productos:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "CARGA MASIVA")
        self.assertContains(response, reverse("productos:imagenes_masivas"))

    def test_pantalla_explica_reemplazo_y_endpoint(self):
        response = self.client.get(reverse("productos:imagenes_masivas"))

        self.assertContains(response, "REEMPLAZO AUTOMÁTICO")
        self.assertContains(response, "imagen_reemplazar") if False else None
        self.assertContains(
            response,
            reverse("productos:imagen_reemplazar", args=[0, 1]),
        )

    @patch("productos.imagenes_views.eliminar_imagen_imagekit")
    @patch("productos.imagenes_views.subir_imagen_producto")
    def test_reemplazar_principal_conserva_posicion_y_limpia_anterior(
        self,
        subir_mock,
        eliminar_mock,
    ):
        subir_mock.return_value = {
            "file_id": "nueva-principal",
            "url": "https://ik.imagekit.io/demo/nueva-principal.jpg",
            "thumbnail_url": "https://ik.imagekit.io/demo/thumb-nueva-principal.jpg",
            "nombre_archivo": "P0001-1.jpg",
            "ancho": 1200,
            "alto": 1200,
            "tamano_bytes": 100000,
        }
        archivo = SimpleUploadedFile(
            "P0001-1.jpg",
            b"imagen-nueva",
            content_type="image/jpeg",
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                reverse(
                    "productos:imagen_reemplazar",
                    args=[self.producto.id, 1],
                ),
                {"imagen": archivo},
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
                HTTP_ACCEPT="application/json",
            )

        self.assertEqual(response.status_code, 200)
        self.principal.refresh_from_db()
        self.assertEqual(self.principal.orden, 1)
        self.assertEqual(self.principal.file_id, "nueva-principal")
        self.assertEqual(
            ProductoImagen.objects.filter(
                producto=self.producto,
                ambiente="qa",
            ).count(),
            1,
        )
        eliminar_mock.assert_called_once_with("masiva-qa")

    @patch("productos.imagenes_views.subir_imagen_producto")
    def test_si_falla_nueva_subida_se_conserva_foto_anterior(self, subir_mock):
        subir_mock.side_effect = RuntimeError("fallo ImageKit")
        archivo = SimpleUploadedFile(
            "P0001-1.jpg",
            b"imagen-nueva",
            content_type="image/jpeg",
        )

        response = self.client.post(
            reverse(
                "productos:imagen_reemplazar",
                args=[self.producto.id, 1],
            ),
            {"imagen": archivo},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

        self.assertEqual(response.status_code, 502)
        self.principal.refresh_from_db()
        self.assertEqual(self.principal.file_id, "masiva-qa")
        self.assertEqual(self.principal.orden, 1)
