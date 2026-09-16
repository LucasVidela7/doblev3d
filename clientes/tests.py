from django.test import TestCase, override_settings
from django.urls import reverse

from pedidos.models import Pedido

from .models import Cliente


@override_settings(SECURE_SSL_REDIRECT=False)
class DetalleClienteAccionesPedidoTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombre="Cliente historial",
            telefono="1122334455",
            email="cliente@ejemplo.com",
            observaciones="Cliente frecuente",
            activo=True,
        )
        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        self.url = reverse(
            "clientes:detalle",
            args=[self.cliente.id],
        )

    def test_pendiente_muestra_editar_cancelar_y_eliminar(self):
        respuesta = self.client.get(self.url)

        self.assertContains(respuesta, "EDITAR PEDIDO")
        self.assertContains(respuesta, "CANCELAR PEDIDO")
        self.assertContains(respuesta, "ELIMINAR PEDIDO")
        self.assertNotContains(respuesta, "ENTREGAR PEDIDO")

    def test_listo_muestra_entregar_y_oculta_edicion(self):
        self.pedido.estado = "LISTO"
        self.pedido.save(update_fields=["estado"])

        respuesta = self.client.get(self.url)

        self.assertContains(respuesta, "ENTREGAR PEDIDO")
        self.assertNotContains(respuesta, "EDITAR PEDIDO")
        self.assertNotContains(respuesta, "CANCELAR PEDIDO")
        self.assertNotContains(respuesta, "ELIMINAR PEDIDO")

    def test_preparando_no_permite_acciones_de_modificacion(self):
        self.pedido.estado = "PREPARANDO"
        self.pedido.save(update_fields=["estado"])

        respuesta = self.client.get(self.url)

        self.assertNotContains(respuesta, "EDITAR PEDIDO")
        self.assertNotContains(respuesta, "CANCELAR PEDIDO")
        self.assertNotContains(respuesta, "ELIMINAR PEDIDO")
        self.assertNotContains(respuesta, "ENTREGAR PEDIDO")

    def test_detalle_abre_en_modo_consulta(self):
        respuesta = self.client.get(self.url)

        self.assertTemplateUsed(respuesta, "clientes/detalle_v2.html")
        self.assertContains(respuesta, "Modo consulta")
        self.assertContains(respuesta, 'id="perfilResumen"')
        self.assertContains(respuesta, 'id="editorCliente" hidden')
        self.assertContains(respuesta, 'id="btnEditarCliente"')

    def test_parametro_editar_abre_formulario(self):
        respuesta = self.client.get(f"{self.url}?editar=1")

        self.assertContains(respuesta, "Editando datos")
        self.assertContains(respuesta, 'id="perfilResumen" hidden')
        self.assertContains(respuesta, 'id="editorCliente"')

    def test_actualizar_cliente_conserva_flujo(self):
        respuesta = self.client.post(
            self.url,
            {
                "nombre": "Cliente actualizado",
                "telefono": "1199999999",
                "email": "nuevo@ejemplo.com",
                "observaciones": "Nueva observación",
            },
        )

        self.assertRedirects(respuesta, self.url)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre, "Cliente actualizado")
        self.assertEqual(self.cliente.telefono, "1199999999")
        self.assertEqual(self.cliente.email, "nuevo@ejemplo.com")
        self.assertEqual(self.cliente.observaciones, "Nueva observación")


@override_settings(SECURE_SSL_REDIRECT=False)
class ListaClientesUXTests(TestCase):
    def setUp(self):
        self.cliente = Cliente.objects.create(
            nombre="Ana Cliente",
            telefono="1144444444",
            activo=True,
        )
        Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        self.url = reverse("clientes:lista")

    def test_listado_usa_nueva_vista_y_resumen(self):
        respuesta = self.client.get(self.url)

        self.assertTemplateUsed(respuesta, "clientes/lista_v2.html")
        self.assertContains(respuesta, "TOTAL COMPRADO")
        self.assertContains(respuesta, "SALDO PENDIENTE")
        self.assertContains(respuesta, "Ana Cliente")
        self.assertContains(respuesta, self.cliente.codigo)

    def test_busqueda_sigue_filtrando(self):
        Cliente.objects.create(nombre="Otro cliente", activo=True)

        respuesta = self.client.get(self.url, {"q": "Ana"})

        self.assertContains(respuesta, "Ana Cliente")
        self.assertNotContains(respuesta, "Otro cliente")
