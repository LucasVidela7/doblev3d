import os
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import ConfiguracionCatalogo


@override_settings(SECURE_SSL_REDIRECT=False)
class CatalogoContactoTests(TestCase):
    def setUp(self):
        self.entorno = patch.dict(os.environ, {"APP_ENV": "qa"})
        self.entorno.start()
        self.addCleanup(self.entorno.stop)

        self.config, _ = ConfiguracionCatalogo.objects.update_or_create(
            pk=1,
            defaults={
                "instagram_usuario": "doblev3d",
                "mostrar_instagram": True,
                "whatsapp_numero": "5491164760709",
                "mostrar_whatsapp": True,
                "whatsapp_mensaje": "Hola! Te escribo desde el catálogo.",
            },
        )

    def test_catalogo_muestra_instagram_y_whatsapp_configurados(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "https://www.instagram.com/doblev3d/")
        self.assertContains(response, "@doblev3d")
        self.assertContains(response, "https://wa.me/5491164760709")
        self.assertContains(response, "dv-catalog-contact__link--whatsapp")

    def test_catalogo_permite_ocultar_cada_canal_desde_configuracion(self):
        self.config.mostrar_instagram = False
        self.config.mostrar_whatsapp = False
        self.config.save()

        response = self.client.get(reverse("catalogo"))

        self.assertNotContains(response, "dv-catalog-contact__link--instagram")
        self.assertNotContains(response, "dv-catalog-contact__link--whatsapp")

    def test_configuracion_normaliza_usuario_y_numero(self):
        self.config.instagram_usuario = "@doblev3d"
        self.config.whatsapp_numero = "+54 9 11 6476-0709"
        self.config.save()
        self.config.refresh_from_db()

        self.assertEqual(self.config.instagram_usuario, "doblev3d")
        self.assertEqual(self.config.whatsapp_numero, "5491164760709")
