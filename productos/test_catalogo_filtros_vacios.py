import os
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Producto, TipoProducto


@override_settings(SECURE_SSL_REDIRECT=False)
class CatalogoFiltrosVaciosTests(TestCase):
    def setUp(self):
        self.entorno = patch.dict(os.environ, {"APP_ENV": "qa"})
        self.entorno.start()
        self.addCleanup(self.entorno.stop)

    def test_catalogo_incluye_control_de_filtros_sin_resultados(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dv-catalog-empty-filters-script"')
        self.assertContains(response, "button.hidden")
        self.assertContains(response, "categories.hidden")
        self.assertContains(response, "segments.hidden")

    def test_categoria_sin_productos_publicables_no_se_ofrece(self):
        visible = TipoProducto.objects.create(nombre="Sensoriales", activo=True)
        vacia = TipoProducto.objects.create(nombre="Decoración", activo=True)

        Producto.objects.create(
            nombre="Piña sensorial",
            categoria="PRODUCTO",
            tipo=visible,
            activo=True,
            solo_produccion=False,
        )
        Producto.objects.create(
            nombre="Decoración interna",
            categoria="PRODUCTO",
            tipo=vacia,
            activo=True,
            solo_produccion=True,
        )

        response = self.client.get(reverse("catalogo"))

        self.assertIn("Sensoriales", response.context["categorias"])
        self.assertNotIn("Decoración", response.context["categorias"])
        self.assertContains(response, 'data-category="sensoriales"')
        self.assertNotContains(response, 'data-category="decoración"')
