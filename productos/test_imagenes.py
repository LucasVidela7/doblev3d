from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
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
class ProductoImagenTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="tester-imagenes",
            password="test",
        )
        self.client.force_login(usuario)
        tipo = TipoProducto.objects.create(nombre="Sensorial")
        self.producto = Producto.objects.create(
            nombre="Cubo sensorial",
            categoria="PRODUCTO",
            tipo=tipo,
            horas=0,
            minutos=0,
            peso_gramos=0,
            margen_ganancia=60,
            requiere_impresion=False,
            stock=0,
            activo=True,
        )

    def _datos_imagen(self, sufijo, orden):
        return ProductoImagen.objects.create(
            producto=self.producto,
            file_id=f"file-{sufijo}",
            url=f"https://ik.imagekit.io/demo/{sufijo}.jpg",
            thumbnail_url=f"https://ik.imagekit.io/demo/thumb-{sufijo}.jpg",
            nombre_archivo=f"{sufijo}.jpg",
            orden=orden,
        )

    def test_modelo_limita_a_dos_fotos(self):
        self._datos_imagen("uno", 1)
        self._datos_imagen("dos", 2)
        with self.assertRaises(ValidationError):
            ProductoImagen.objects.create(
                producto=self.producto,
                file_id="file-tres",
                url="https://ik.imagekit.io/demo/tres.jpg",
                orden=3,
            )

    def test_pantalla_muestra_dos_slots(self):
        response = self.client.get(
            reverse("productos:imagenes", args=[self.producto.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "0/2 fotos cargadas")
        self.assertContains(response, "SUBIR A IMAGEKIT")

    def test_editar_producto_integra_galeria_drag_and_drop(self):
        self._datos_imagen("uno", 1)
        response = self.client.get(
            reverse("productos:editar", args=[self.producto.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dv-editar-fotos"')
        self.assertContains(response, "Arrastrá o seleccioná fotos")
        self.assertContains(response, 'id="dv-edit-product-photos-script"')
        self.assertContains(response, "thumb-uno.jpg")
        self.assertContains(response, "imagen_subir" if False else "/imagenes/subir/")

    @patch("productos.imagenes_views.subir_imagen_producto")
    def test_subida_guarda_referencia_de_imagekit(self, subir_mock):
        subir_mock.return_value = {
            "file_id": "ik-123",
            "url": "https://ik.imagekit.io/demo/cubo.jpg",
            "thumbnail_url": "https://ik.imagekit.io/demo/thumb-cubo.jpg",
            "nombre_archivo": "cubo.jpg",
            "ancho": 1200,
            "alto": 900,
            "tamano_bytes": 120000,
        }
        archivo = SimpleUploadedFile(
            "cubo.jpg",
            b"imagen-de-prueba",
            content_type="image/jpeg",
        )
        response = self.client.post(
            reverse("productos:imagen_subir", args=[self.producto.id]),
            {"imagen": archivo},
        )
        self.assertEqual(response.status_code, 302)
        imagen = ProductoImagen.objects.get(producto=self.producto)
        self.assertEqual(imagen.file_id, "ik-123")
        self.assertEqual(imagen.orden, 1)

    @patch("productos.imagenes_views.subir_imagen_producto")
    def test_subida_ajax_devuelve_galeria_actualizada(self, subir_mock):
        subir_mock.return_value = {
            "file_id": "ik-ajax",
            "url": "https://ik.imagekit.io/demo/ajax.jpg",
            "thumbnail_url": "https://ik.imagekit.io/demo/thumb-ajax.jpg",
            "nombre_archivo": "ajax.jpg",
            "ancho": 1000,
            "alto": 1000,
            "tamano_bytes": 90000,
        }
        archivo = SimpleUploadedFile(
            "ajax.jpg",
            b"imagen-de-prueba",
            content_type="image/jpeg",
        )
        response = self.client.post(
            reverse("productos:imagen_subir", args=[self.producto.id]),
            {"imagen": archivo},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["imagenes"]), 1)
        self.assertTrue(payload["imagenes"][0]["principal"])
        self.assertEqual(payload["imagenes"][0]["url"], "https://ik.imagekit.io/demo/ajax.jpg")

    @patch("productos.imagenes_views.subir_imagen_producto")
    def test_tercera_foto_se_rechaza_antes_de_imagekit(self, subir_mock):
        self._datos_imagen("uno", 1)
        self._datos_imagen("dos", 2)
        archivo = SimpleUploadedFile(
            "tres.jpg",
            b"imagen-de-prueba",
            content_type="image/jpeg",
        )
        response = self.client.post(
            reverse("productos:imagen_subir", args=[self.producto.id]),
            {"imagen": archivo},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(ProductoImagen.objects.filter(producto=self.producto).count(), 2)
        subir_mock.assert_not_called()

    def test_hacer_secundaria_principal_intercambia_orden(self):
        principal = self._datos_imagen("uno", 1)
        secundaria = self._datos_imagen("dos", 2)
        response = self.client.post(
            reverse(
                "productos:imagen_principal",
                args=[self.producto.id, secundaria.id],
            )
        )
        self.assertEqual(response.status_code, 302)
        principal.refresh_from_db()
        secundaria.refresh_from_db()
        self.assertEqual(secundaria.orden, 1)
        self.assertEqual(principal.orden, 2)

    def test_hacer_principal_ajax_devuelve_orden_actualizado(self):
        self._datos_imagen("uno", 1)
        secundaria = self._datos_imagen("dos", 2)
        response = self.client.post(
            reverse(
                "productos:imagen_principal",
                args=[self.producto.id, secundaria.id],
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        principal = next(item for item in payload["imagenes"] if item["principal"])
        self.assertEqual(principal["id"], secundaria.id)

    @patch("productos.imagenes_views.eliminar_imagen_imagekit")
    def test_eliminar_principal_promueve_secundaria(self, eliminar_mock):
        principal = self._datos_imagen("uno", 1)
        secundaria = self._datos_imagen("dos", 2)
        response = self.client.post(
            reverse(
                "productos:imagen_eliminar",
                args=[self.producto.id, principal.id],
            )
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(ProductoImagen.objects.filter(pk=principal.pk).exists())
        secundaria.refresh_from_db()
        self.assertEqual(secundaria.orden, 1)
        eliminar_mock.assert_called_once_with("file-uno")

    @patch("productos.imagenes_views.eliminar_imagen_imagekit")
    def test_eliminar_ajax_devuelve_galeria_actualizada(self, eliminar_mock):
        principal = self._datos_imagen("uno", 1)
        secundaria = self._datos_imagen("dos", 2)
        response = self.client.post(
            reverse(
                "productos:imagen_eliminar",
                args=[self.producto.id, principal.id],
            ),
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["imagenes"]), 1)
        self.assertEqual(payload["imagenes"][0]["id"], secundaria.id)
        self.assertTrue(payload["imagenes"][0]["principal"])

    def test_detalle_muestra_galeria_y_edita_fotos_desde_producto(self):
        self._datos_imagen("uno", 1)
        response = self.client.get(
            reverse("productos:detalle", args=[self.producto.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "FOTOS 1/2")
        self.assertContains(response, "FOTOS DEL PRODUCTO")
        self.assertContains(response, "EDITAR FOTOS")
        self.assertContains(response, "#dv-editar-fotos")
        self.assertContains(response, "thumb-uno.jpg")
        self.assertNotContains(response, "ADMINISTRAR FOTOS")
