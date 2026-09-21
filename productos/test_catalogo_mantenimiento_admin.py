from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from productos.models import ConfiguracionCatalogo


@override_settings(CATALOGO_MANTENIMIENTO=False)
class CatalogoMantenimientoAdminTests(TestCase):
    def setUp(self):
        self.config, _ = ConfiguracionCatalogo.objects.update_or_create(
            pk=1,
            defaults={
                "catalogo_activo": False,
                "mensaje_mantenimiento": "Mantenimiento de prueba.",
            },
        )

    def test_publico_no_puede_ver_catalogo_en_mantenimiento(self):
        respuesta = self.client.get(reverse("catalogo"))

        self.assertEqual(respuesta.status_code, 503)
        self.assertContains(
            respuesta,
            "Estamos haciendo unos ajustes.",
            status_code=503,
        )
        self.assertNotContains(
            respuesta,
            "SOLO ADMIN",
            status_code=503,
        )
        self.assertContains(
            respuesta,
            "height:100dvh",
            status_code=503,
        )
        self.assertContains(
            respuesta,
            "overflow:hidden",
            status_code=503,
        )

    def test_usuario_logueado_no_admin_tampoco_puede_verlo(self):
        usuario = get_user_model().objects.create_user(
            username="usuario",
            password="clave-segura",
            is_staff=False,
        )
        self.client.force_login(usuario)

        respuesta = self.client.get(reverse("catalogo"))

        self.assertEqual(respuesta.status_code, 503)

    def test_admin_puede_ver_catalogo_con_aviso_de_mantenimiento(self):
        admin = get_user_model().objects.create_user(
            username="admin-catalogo",
            password="clave-segura",
            is_staff=True,
        )
        self.client.force_login(admin)

        respuesta = self.client.get(reverse("catalogo"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "Tienda en mantenimiento",
        )
        self.assertContains(
            respuesta,
            "SOLO ADMIN",
        )
        self.assertTrue(
            respuesta.wsgi_request.catalogo_en_mantenimiento
        )

    def test_admin_puede_navegar_productos_durante_mantenimiento(self):
        admin = get_user_model().objects.create_user(
            username="admin-productos",
            password="clave-segura",
            is_staff=True,
        )
        self.client.force_login(admin)

        respuesta = self.client.get(
            reverse("catalogo_productos")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "Tienda en mantenimiento",
        )

    def test_admin_ve_aviso_en_todas_las_paginas_comerciales_principales(self):
        admin = get_user_model().objects.create_user(
            username="admin-tienda-completa",
            password="clave-segura",
            is_staff=True,
        )
        self.client.force_login(admin)

        for nombre_ruta in (
            "catalogo",
            "catalogo_legacy",
            "catalogo_productos",
            "catalogo_kits",
            "catalogo_carrito",
        ):
            with self.subTest(ruta=nombre_ruta):
                respuesta = self.client.get(reverse(nombre_ruta))

                self.assertEqual(respuesta.status_code, 200)
                self.assertContains(
                    respuesta,
                    "Tienda en mantenimiento",
                )
                self.assertContains(
                    respuesta,
                    "SOLO ADMIN",
                )
                self.assertContains(
                    respuesta,
                    "border:4px solid #f59e0b",
                )

    def test_paginas_legales_no_muestran_aviso_admin_de_mantenimiento(self):
        admin = get_user_model().objects.create_user(
            username="admin-legales",
            password="clave-segura",
            is_staff=True,
        )
        self.client.force_login(admin)

        for nombre_ruta in (
            "catalogo_terminos",
            "catalogo_privacidad",
            "catalogo_arrepentimiento",
        ):
            with self.subTest(ruta=nombre_ruta):
                respuesta = self.client.get(reverse(nombre_ruta))

                self.assertEqual(respuesta.status_code, 200)
                self.assertNotContains(
                    respuesta,
                    "Tienda en mantenimiento",
                )
                self.assertNotContains(
                    respuesta,
                    "SOLO ADMIN",
                )

    def test_detalle_publico_de_producto_respeta_mantenimiento(self):
        respuesta = self.client.get(
            reverse(
                "catalogo_producto_detalle",
                args=[999],
            )
        )

        self.assertEqual(respuesta.status_code, 503)

