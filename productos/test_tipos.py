from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import TipoProducto


class CrearTipoProductoTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="tester-productos",
            password="test12345",
        )
        self.client.force_login(usuario)

    def test_crear_tipo_desde_api(self):
        respuesta = self.client.post(
            reverse("productos:crear_tipo"),
            {"nombre": "Llaveros"},
        )

        self.assertEqual(respuesta.status_code, 200)
        data = respuesta.json()
        self.assertTrue(data["ok"])
        self.assertTrue(data["creado"])
        self.assertTrue(
            TipoProducto.objects.filter(
                nombre="Llaveros",
                activo=True,
            ).exists()
        )

    def test_tipo_existente_inactivo_se_reactiva(self):
        tipo = TipoProducto.objects.create(
            nombre="Macetas",
            activo=False,
        )

        respuesta = self.client.post(
            reverse("productos:crear_tipo"),
            {"nombre": "macetas"},
        )

        self.assertEqual(respuesta.status_code, 200)
        tipo.refresh_from_db()
        self.assertTrue(tipo.activo)
        self.assertFalse(respuesta.json()["creado"])

    def test_formulario_producto_inyecta_creacion_de_tipo(self):
        respuesta = self.client.get(reverse("productos:nuevo"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "dv-tipos-producto-script")
        self.assertContains(respuesta, "＋ NUEVO TIPO")
