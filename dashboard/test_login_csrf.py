import re

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CSRF_COOKIE_SECURE=False,
    SESSION_COOKIE_SECURE=False,
)
class LoginCsrfTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="admin_prueba",
            password="clave-segura-123",
        )

    def test_doble_envio_login_no_termina_en_403(self):
        client = Client(enforce_csrf_checks=True)
        response = client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)

        match = re.search(
            rb'name="csrfmiddlewaretoken" value="([^"]+)"',
            response.content,
        )
        self.assertIsNotNone(match)
        token_viejo = match.group(1).decode("utf-8")

        primero = client.post(
            reverse("login"),
            {
                "username": "admin_prueba",
                "password": "clave-segura-123",
                "csrfmiddlewaretoken": token_viejo,
            },
        )
        self.assertEqual(primero.status_code, 302)

        segundo = client.post(
            reverse("login"),
            {
                "username": "admin_prueba",
                "password": "clave-segura-123",
                "csrfmiddlewaretoken": token_viejo,
            },
        )

        self.assertEqual(segundo.status_code, 302)
        self.assertEqual(
            segundo.url,
            reverse("dashboard:inicio"),
        )

    def test_login_bloquea_doble_submit_en_frontend(self):
        response = self.client.get(reverse("login"))

        self.assertContains(response, 'id="dvLoginForm"')
        self.assertContains(response, 'id="dvLoginButton"')
        self.assertContains(response, 'button.disabled = true')
        self.assertContains(response, 'INGRESANDO…')
