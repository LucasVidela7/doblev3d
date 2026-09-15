from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(SECURE_SSL_REDIRECT=False)
class AutenticacionTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="lucas",
            password="ClaveSegura-12345",
        )

    def test_login_es_publico(self):
        respuesta = self.client.get(reverse("login"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Doble V 3D")
        self.assertContains(respuesta, "USUARIO")
        self.assertContains(respuesta, "CONTRASEÑA")

    def test_dashboard_redirige_a_login_sin_sesion(self):
        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertRedirects(
            respuesta,
            f'{reverse("login")}?next={reverse("dashboard:inicio")}',
            fetch_redirect_response=False,
        )

    def test_login_correcto_permite_entrar_al_dashboard(self):
        respuesta = self.client.post(
            reverse("login"),
            {
                "username": "lucas",
                "password": "ClaveSegura-12345",
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("dashboard:inicio"),
            fetch_redirect_response=False,
        )

        respuesta_dashboard = self.client.get(
            reverse("dashboard:inicio")
        )
        self.assertEqual(respuesta_dashboard.status_code, 200)

    def test_dashboard_muestra_usuario_y_cerrar_sesion(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("dashboard:inicio"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "👤 lucas")
        self.assertContains(respuesta, "CERRAR SESIÓN")
        self.assertContains(respuesta, f'action="{reverse("logout")}"')

    def test_login_incorrecto_no_inicia_sesion(self):
        respuesta = self.client.post(
            reverse("login"),
            {
                "username": "lucas",
                "password": "incorrecta",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "Usuario o contraseña incorrectos",
        )

        respuesta_dashboard = self.client.get(
            reverse("dashboard:inicio")
        )
        self.assertEqual(respuesta_dashboard.status_code, 302)

    def test_login_respeta_next(self):
        destino = reverse("clientes:lista")

        respuesta = self.client.post(
            reverse("login"),
            {
                "username": "lucas",
                "password": "ClaveSegura-12345",
                "next": destino,
            },
        )

        self.assertRedirects(
            respuesta,
            destino,
            fetch_redirect_response=False,
        )

    def test_logout_cierra_la_sesion(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.post(reverse("logout"))

        self.assertRedirects(
            respuesta,
            reverse("login"),
            fetch_redirect_response=False,
        )

        respuesta_dashboard = self.client.get(
            reverse("dashboard:inicio")
        )
        self.assertEqual(respuesta_dashboard.status_code, 302)
