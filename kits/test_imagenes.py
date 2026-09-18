import os
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from productos.image_models import ProductoImagen
from productos.models import Producto, TipoProducto

from .models import Kit, KitComponente


@override_settings(
    SECURE_SSL_REDIRECT=False,
    SESSION_COOKIE_SECURE=False,
    CSRF_COOKIE_SECURE=False,
)
@patch.dict(os.environ, {"APP_ENV": "qa"}, clear=False)
class KitImagenesTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="tester-kits-imagenes",
            password="test",
        )
        self.client.force_login(usuario)
        self.tipo = TipoProducto.objects.create(nombre="Sensorial kits fotos")
        self.producto_a = Producto.objects.create(
            nombre="Piña sensorial",
            categoria="PRODUCTO",
            tipo=self.tipo,
            requiere_impresion=False,
            margen_ganancia=50,
            activo=True,
            solo_produccion=False,
        )
        self.producto_b = Producto.objects.create(
            nombre="Cubo sensorial",
            categoria="PRODUCTO",
            tipo=self.tipo,
            requiere_impresion=False,
            margen_ganancia=50,
            activo=True,
            solo_produccion=False,
        )
        self.interno = Producto.objects.create(
            nombre="Pieza interna oculta",
            categoria="PRODUCTO",
            tipo=self.tipo,
            requiere_impresion=False,
            margen_ganancia=50,
            activo=True,
            solo_produccion=True,
        )

    def _imagen(self, producto, ambiente, sufijo, orden=1):
        return ProductoImagen.objects.create(
            producto=producto,
            ambiente=ambiente,
            file_id=f"{producto.id}-{ambiente}-{sufijo}",
            url=f"https://ik.imagekit.io/demo/{ambiente}-{sufijo}.jpg",
            thumbnail_url=f"https://ik.imagekit.io/demo/thumb-{ambiente}-{sufijo}.jpg",
            orden=orden,
        )

    def test_kit_fijo_reutiliza_principal_qa_y_no_production(self):
        kit = Kit.objects.create(
            nombre="Kit fijo fotos",
            modalidad="FIJO",
            cantidad_productos=2,
            precio=Decimal("10000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=self.producto_a,
            cantidad=2,
        )
        self._imagen(self.producto_a, "qa", "pina-principal", orden=1)
        self._imagen(self.producto_a, "qa", "pina-secundaria", orden=2)
        self._imagen(self.producto_a, "production", "pina-production", orden=1)

        response = self.client.get(reverse("kits:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PRODUCTOS DEL KIT")
        self.assertContains(response, "https://ik.imagekit.io/demo/qa-pina-principal.jpg")
        self.assertNotContains(response, "https://ik.imagekit.io/demo/qa-pina-secundaria.jpg")
        self.assertNotContains(response, "https://ik.imagekit.io/demo/production-pina-production.jpg")
        self.assertContains(response, "Piña sensorial")
        self.assertContains(response, "x 2")

    def test_kit_libre_reutiliza_fotos_de_productos_comerciales_de_categoria(self):
        Kit.objects.create(
            nombre="Kit libre fotos",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("10000"),
            activo=True,
        )
        self._imagen(self.producto_a, "qa", "pina")
        self._imagen(self.producto_b, "qa", "cubo")
        self._imagen(self.interno, "qa", "interna")
        self._imagen(self.producto_a, "production", "pina-production")

        response = self.client.get(reverse("kits:lista"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "OPCIONES DISPONIBLES")
        self.assertContains(response, "https://ik.imagekit.io/demo/qa-pina.jpg")
        self.assertContains(response, "https://ik.imagekit.io/demo/qa-cubo.jpg")
        self.assertNotContains(response, "https://ik.imagekit.io/demo/qa-interna.jpg")
        self.assertNotContains(response, "thumb-production-pina-production.jpg")
        self.assertContains(response, "Piña sensorial")
        self.assertContains(response, "Cubo sensorial")
