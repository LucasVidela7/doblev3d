import os
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from auditoria.models import RegistroAuditoria

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

    def test_catalogo_muestra_contactos_flotantes_con_rutas_auditables(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="dv-catalog-contact-links"')
        self.assertContains(
            response,
            reverse("catalogo_contacto", kwargs={"canal": "instagram"}),
        )
        self.assertContains(
            response,
            reverse("catalogo_contacto", kwargs={"canal": "whatsapp"}),
        )
        self.assertContains(response, "dv-catalog-contact__link--instagram")
        self.assertContains(response, "dv-catalog-contact__link--whatsapp")
        self.assertContains(response, "position:fixed")
        self.assertContains(response, "bottom:calc(18px")
        self.assertContains(response, 'aria-label="Abrir Instagram @doblev3d"')
        self.assertContains(response, 'aria-label="Escribir por WhatsApp"')

    def test_clicks_de_instagram_y_whatsapp_se_registran_en_auditoria(self):
        instagram = self.client.get(
            reverse("catalogo_contacto", kwargs={"canal": "instagram"}),
            REMOTE_ADDR="127.0.0.8",
        )
        whatsapp = self.client.get(
            reverse("catalogo_contacto", kwargs={"canal": "whatsapp"}),
            REMOTE_ADDR="127.0.0.9",
        )

        self.assertEqual(instagram.status_code, 302)
        self.assertEqual(instagram["Location"], "https://www.instagram.com/doblev3d/")
        self.assertEqual(whatsapp.status_code, 302)
        self.assertTrue(whatsapp["Location"].startswith("https://wa.me/5491164760709"))

        registros = RegistroAuditoria.objects.filter(
            accion="CLICK_CONTACTO_CATALOGO",
        ).order_by("fecha", "id")
        self.assertEqual(registros.count(), 2)
        self.assertIsNone(registros[0].usuario)
        self.assertEqual(registros[0].usuario_nombre, "Visitante")
        self.assertEqual(registros[0].objeto_representacion, "Catálogo · Instagram")
        self.assertEqual(registros[0].cambios["canal"], "Instagram")
        self.assertEqual(registros[0].ruta, "/contacto/instagram/")
        self.assertEqual(registros[0].ip, "127.0.0.8")
        self.assertIsNone(registros[1].usuario)
        self.assertEqual(registros[1].usuario_nombre, "Visitante")
        self.assertEqual(registros[1].objeto_representacion, "Catálogo · WhatsApp")
        self.assertEqual(registros[1].cambios["canal"], "WhatsApp")

    def test_click_publico_no_se_asocia_a_usuario_aunque_haya_sesion(self):
        User = get_user_model()
        usuario = User.objects.create_user(username="tester", password="clave-segura")
        self.client.force_login(usuario)

        response = self.client.get(
            reverse("catalogo_contacto", kwargs={"canal": "whatsapp"}),
            REMOTE_ADDR="127.0.0.10",
        )

        self.assertEqual(response.status_code, 302)
        registro = RegistroAuditoria.objects.get(accion="CLICK_CONTACTO_CATALOGO")
        self.assertIsNone(registro.usuario)
        self.assertEqual(registro.usuario_nombre, "Visitante")
        self.assertEqual(registro.cambios["canal"], "WhatsApp")

    def test_head_no_se_cuenta_como_click(self):
        response = self.client.head(
            reverse("catalogo_contacto", kwargs={"canal": "instagram"}),
        )

        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            RegistroAuditoria.objects.filter(
                accion="CLICK_CONTACTO_CATALOGO",
            ).exists()
        )

    def test_catalogo_permite_ocultar_cada_canal_desde_configuracion(self):
        self.config.mostrar_instagram = False
        self.config.mostrar_whatsapp = False
        self.config.save()

        response = self.client.get(reverse("catalogo"))

        self.assertNotContains(response, 'id="dv-catalog-contact-links"')
        self.assertNotContains(response, "dv-catalog-contact__link--instagram")
        self.assertNotContains(response, "dv-catalog-contact__link--whatsapp")

        instagram = self.client.get(
            reverse("catalogo_contacto", kwargs={"canal": "instagram"}),
        )
        self.assertEqual(instagram.status_code, 404)

    def test_configuracion_normaliza_usuario_y_numero(self):
        self.config.instagram_usuario = "@doblev3d"
        self.config.whatsapp_numero = "+54 9 11 6476-0709"
        self.config.save()
        self.config.refresh_from_db()

        self.assertEqual(self.config.instagram_usuario, "doblev3d")
        self.assertEqual(self.config.whatsapp_numero, "5491164760709")
