from django.test import TestCase, override_settings
from django.urls import reverse

from .models import (
    ConfiguracionCatalogo,
    SolicitudArrepentimiento,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    CATALOGO_MANTENIMIENTO=False,
)
class CatalogoLegalTests(TestCase):
    def setUp(self):
        self.config, _ = ConfiguracionCatalogo.objects.update_or_create(
            pk=1,
            defaults={
                "catalogo_activo": True,
                "razon_social": "Responsable de prueba",
                "cuit": "20-12345678-9",
                "domicilio_legal": "Domicilio de prueba",
                "email_legal": "legal@example.com",
            },
        )

    def test_catalogo_inyecta_footer_y_boton_de_arrepentimiento(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'id="dv-catalog-legal-footer"',
        )
        self.assertContains(
            response,
            "Términos de compra",
        )
        self.assertContains(
            response,
            "Privacidad",
        )
        self.assertContains(
            response,
            "BOTÓN DE ARREPENTIMIENTO",
        )
        self.assertContains(
            response,
            reverse("catalogo_arrepentimiento"),
        )

    def test_boton_de_arrepentimiento_visible_en_paginas_comerciales(self):
        for nombre_ruta in (
            "catalogo",
            "catalogo_productos",
            "catalogo_kits",
            "catalogo_carrito",
        ):
            response = self.client.get(reverse(nombre_ruta))

            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Cambios y arrepentimiento")
            self.assertContains(
                response,
                "BOTÓN DE ARREPENTIMIENTO",
            )

    def test_terminos_muestran_datos_configurados_y_personalizados(self):
        response = self.client.get(
            reverse("catalogo_terminos")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Responsable de prueba")
        self.assertContains(response, "20-12345678-9")
        self.assertContains(response, "Productos personalizados")
        self.assertContains(
            response,
            "garantía legal",
        )

    def test_privacidad_explica_datos_y_derechos(self):
        response = self.client.get(
            reverse("catalogo_privacidad")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Política de privacidad")
        self.assertContains(response, "rectificación")
        self.assertContains(response, "supresión")
        self.assertContains(response, "legal@example.com")

    def test_arrepentimiento_es_publico_y_no_requiere_login(self):
        response = self.client.get(
            reverse("catalogo_arrepentimiento")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "No necesitás registrarte",
        )
        self.assertContains(
            response,
            "ENVIAR SOLICITUD DE ARREPENTIMIENTO",
        )

    def test_arrepentimiento_registra_solicitud_y_codigo(self):
        response = self.client.post(
            reverse("catalogo_arrepentimiento"),
            {
                "nombre": "Cliente Prueba",
                "contacto": "+54 11 5555 4444",
                "referencia": "PED0012",
                "detalle": "Quiero solicitar la revocación.",
                "website": "",
            },
        )

        self.assertRedirects(
            response,
            reverse("catalogo_arrepentimiento_gracias"),
        )
        solicitud = SolicitudArrepentimiento.objects.get()
        self.assertEqual(solicitud.nombre, "Cliente Prueba")
        self.assertEqual(solicitud.referencia, "PED0012")
        self.assertEqual(solicitud.estado, "NUEVA")

        gracias = self.client.get(
            reverse("catalogo_arrepentimiento_gracias")
        )
        self.assertContains(gracias, solicitud.codigo)
        self.assertContains(gracias, "Solicitud recibida")

    def test_paginas_legales_siguen_accesibles_en_mantenimiento(self):
        self.config.catalogo_activo = False
        self.config.save(update_fields=["catalogo_activo"])

        terminos = self.client.get(
            reverse("catalogo_terminos")
        )
        arrepentimiento = self.client.get(
            reverse("catalogo_arrepentimiento")
        )

        self.assertEqual(terminos.status_code, 200)
        self.assertEqual(arrepentimiento.status_code, 200)

    def test_checkout_enlaza_informacion_legal(self):
        response = self.client.get(
            reverse("catalogo_carrito")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("catalogo_terminos"),
        )
        self.assertContains(
            response,
            reverse("catalogo_privacidad"),
        )
        self.assertContains(
            response,
            reverse("catalogo_arrepentimiento"),
        )
