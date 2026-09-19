from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from clientes.telefonos import (
    buscar_cliente_por_telefono,
    normalizar_telefono,
)


TEST_STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STORAGES=TEST_STORAGES,
)
class TelefonoClienteTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="telefono-cliente-tests",
            password="test-pass-seguro",
        )
        self.client.force_login(self.usuario)
        self.existente = Cliente.objects.create(
            nombre="Cliente existente",
            telefono="11 6476-0709",
            activo=True,
        )

    def test_normaliza_formatos_argentinos_equivalentes(self):
        self.assertEqual(
            normalizar_telefono("11 6476-0709"),
            "1164760709",
        )
        self.assertEqual(
            normalizar_telefono("+54 11 6476-0709"),
            "1164760709",
        )
        self.assertEqual(
            normalizar_telefono("+54 9 11 6476-0709"),
            "1164760709",
        )

    def test_busqueda_detecta_telefono_con_otro_formato(self):
        cliente = buscar_cliente_por_telefono(
            "+54 9 11 6476-0709"
        )
        self.assertEqual(cliente, self.existente)

    def test_nuevo_presupuesto_no_duplica_cliente_por_telefono(self):
        respuesta = self.client.post(
            reverse("pedidos:nuevo"),
            {
                "cliente": "NUEVO",
                "nuevo_cliente_nombre": "Duplicado",
                "nuevo_cliente_telefono": "+54 9 11 6476-0709",
                "nuevo_cliente_email": "",
                "fecha_entrega": "",
                "observaciones": "",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Cliente.objects.count(), 1)
        self.assertIn(
            f"cliente={self.existente.id}",
            respuesta.url,
        )

    def test_editar_cliente_no_permite_telefono_ajeno(self):
        otro = Cliente.objects.create(
            nombre="Otro cliente",
            telefono="11 5555-1111",
            activo=True,
        )

        respuesta = self.client.post(
            reverse(
                "clientes:detalle",
                args=[otro.id],
            ),
            {
                "nombre": otro.nombre,
                "telefono": "+54 9 11 6476-0709",
                "email": "",
                "observaciones": "",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        otro.refresh_from_db()
        self.assertEqual(otro.telefono, "11 5555-1111")
