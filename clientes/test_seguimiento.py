from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from pedidos.models import (
    DetallePedido,
    Pedido,
    Presupuesto,
)
from productos.models import ConfiguracionCatalogo, Producto, TipoProducto

from .models import Cliente, ContactoCliente


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
class SeguimientoClientesTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="clientes-seguimiento",
            password="test-pass",
        )
        self.client.force_login(usuario)

        self.cliente = Cliente.objects.create(
            nombre="Cliente Seguimiento",
            telefono="+54 9 11 5555 4444",
            email="seguimiento@example.com",
            activo=True,
        )
        tipo = TipoProducto.objects.create(
            nombre="Preferencias",
        )
        self.producto = Producto.objects.create(
            nombre="Pepino sensorial",
            categoria="PRODUCTO",
            tipo=tipo,
            requiere_impresion=False,
            activo=True,
        )

    def test_whatsapp_listo_registra_apertura_no_envio(self):
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="LISTO",
        )
        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=1,
            precio_unitario=Decimal("5000"),
        )

        respuesta = self.client.get(
            reverse(
                "clientes:whatsapp",
                args=[self.cliente.id],
            ),
            {
                "motivo": "PEDIDO_LISTO",
                "pedido": pedido.id,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(
            respuesta.url.startswith("https://wa.me/")
        )
        contacto = ContactoCliente.objects.get()
        self.assertEqual(
            contacto.motivo,
            "PEDIDO_LISTO",
        )
        self.assertIn(
            "Hola Cliente 👋",
            contacto.mensaje,
        )
        self.assertEqual(
            contacto.referencia,
            pedido.codigo,
        )
        self.assertIn(
            "ya está listo",
            contacto.mensaje,
        )

    def test_detalle_limita_historial_reciente_a_cinco(self):
        for _ in range(7):
            Pedido.objects.create(
                cliente=self.cliente,
                estado="ENTREGADO",
            )

        respuesta = self.client.get(
            reverse(
                "clientes:detalle",
                args=[self.cliente.id],
            )
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            len(respuesta.context["filas_pedidos"]),
            5,
        )
        self.assertTrue(
            respuesta.context["hay_mas_pedidos"]
        )
        self.assertContains(respuesta, "VER TODO")

    def test_historial_de_pedidos_se_pagina(self):
        for _ in range(25):
            Pedido.objects.create(
                cliente=self.cliente,
                estado="ENTREGADO",
            )

        respuesta = self.client.get(
            reverse(
                "clientes:historial",
                args=[self.cliente.id],
            ),
            {"tipo": "pedidos"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            len(respuesta.context["elementos"]),
            20,
        )
        self.assertEqual(
            respuesta.context["pagina"].paginator.num_pages,
            2,
        )

    def test_preferencias_muestran_producto_mas_comprado(self):
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="ENTREGADO",
        )
        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=4,
            precio_unitario=Decimal("3000"),
        )

        respuesta = self.client.get(
            reverse(
                "clientes:detalle",
                args=[self.cliente.id],
            )
        )

        self.assertContains(
            respuesta,
            "PREFERENCIAS DE COMPRA",
        )
        self.assertContains(
            respuesta,
            "Pepino sensorial",
        )
        preferencias = respuesta.context[
            "preferencias"
        ]
        self.assertEqual(
            preferencias[0]["unidades"],
            4,
        )

    def test_fusion_mueve_historial_y_desactiva_duplicado(self):
        duplicado = Cliente.objects.create(
            nombre="Cliente Seguimiento",
            telefono="11 5555-4444",
            observaciones="Ficha anterior",
            activo=True,
        )
        pedido = Pedido.objects.create(
            cliente=duplicado,
            estado="ENTREGADO",
        )
        presupuesto = Presupuesto.objects.create(
            cliente=duplicado,
            estado="PENDIENTE",
        )
        ContactoCliente.objects.create(
            cliente=duplicado,
            motivo="GENERICO",
            mensaje="Prueba",
        )

        respuesta = self.client.post(
            reverse(
                "clientes:fusionar",
                args=[self.cliente.id],
            ),
            {
                "duplicado_id": duplicado.id,
            },
        )

        self.assertRedirects(
            respuesta,
            reverse(
                "clientes:detalle",
                args=[self.cliente.id],
            ),
        )
        duplicado.refresh_from_db()
        pedido.refresh_from_db()
        presupuesto.refresh_from_db()

        self.assertFalse(duplicado.activo)
        self.assertEqual(
            pedido.cliente_id,
            self.cliente.id,
        )
        self.assertEqual(
            presupuesto.cliente_id,
            self.cliente.id,
        )
        self.assertEqual(
            ContactoCliente.objects.get().cliente_id,
            self.cliente.id,
        )

    def test_listado_calcula_totales_sin_historial_precargado(self):
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="ENTREGADO",
        )
        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=2,
            precio_unitario=Decimal("4000"),
        )

        respuesta = self.client.get(
            reverse("clientes:lista")
        )

        self.assertEqual(respuesta.status_code, 200)
        fila = next(
            item
            for item in respuesta.context["filas"]
            if item["cliente"].id == self.cliente.id
        )
        self.assertEqual(
            fila["total_comprado"],
            Decimal("8000"),
        )
        self.assertEqual(
            fila["cantidad_pedidos"],
            1,
        )

    def test_whatsapp_usa_plantilla_configurada_y_variables(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(
            pk=1
        )
        config.whatsapp_mensaje_cliente_saldo = (
            "Hola {nombre} | {codigo} | saldo {saldo} | total {total}"
        )
        config.save(
            update_fields=[
                "whatsapp_mensaje_cliente_saldo",
            ]
        )

        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=2,
            precio_unitario=Decimal("7500"),
        )

        respuesta = self.client.get(
            reverse(
                "clientes:whatsapp",
                args=[self.cliente.id],
            ),
            {
                "motivo": "SALDO",
                "pedido": pedido.id,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        contacto = ContactoCliente.objects.get()
        self.assertIn(
            "Hola Cliente",
            contacto.mensaje,
        )
        self.assertIn(
            pedido.codigo,
            contacto.mensaje,
        )
        self.assertIn(
            "saldo 15.000",
            contacto.mensaje,
        )
        self.assertIn(
            "total 15.000",
            contacto.mensaje,
        )

    def test_seguimiento_unifica_dos_pedidos_y_whatsapp(self):
        pedido_a = Pedido.objects.create(
            cliente=self.cliente,
            estado="LISTO",
        )
        DetallePedido.objects.create(
            pedido=pedido_a,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=1,
            precio_unitario=Decimal("5000"),
        )

        pedido_b = Pedido.objects.create(
            cliente=self.cliente,
            estado="LISTO",
        )
        DetallePedido.objects.create(
            pedido=pedido_b,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=2,
            precio_unitario=Decimal("7500"),
        )

        respuesta = self.client.get(
            reverse(
                "clientes:detalle",
                args=[self.cliente.id],
            )
        )

        self.assertEqual(respuesta.status_code, 200)
        seguimientos_pedidos = [
            item
            for item in respuesta.context["seguimientos"]
            if item["tipo"] in {
                "PEDIDO_LISTO",
                "SALDO",
            }
        ]
        self.assertEqual(
            len(seguimientos_pedidos),
            1,
        )
        seguimiento = seguimientos_pedidos[0]
        self.assertEqual(
            seguimiento["titulo"],
            "2 pedidos listos para entregar",
        )
        self.assertIn(
            pedido_a.codigo,
            seguimiento["detalle"],
        )
        self.assertIn(
            pedido_b.codigo,
            seguimiento["detalle"],
        )
        self.assertIn(
            "Saldo total $ 20,000",
            seguimiento["detalle"],
        )
        self.assertIn(
            "pedidos=",
            seguimiento["url"],
        )

        respuesta_whatsapp = self.client.get(
            reverse(
                "clientes:whatsapp",
                args=[self.cliente.id],
            ),
            {
                "motivo": "PEDIDO_LISTO",
                "pedidos": (
                    f"{pedido_a.id},{pedido_b.id}"
                ),
            },
        )

        self.assertEqual(
            respuesta_whatsapp.status_code,
            302,
        )
        self.assertTrue(
            respuesta_whatsapp.url.startswith(
                "https://wa.me/"
            )
        )

        contacto = ContactoCliente.objects.get()
        self.assertEqual(
            contacto.motivo,
            "PEDIDO_LISTO",
        )
        self.assertIn(
            pedido_a.codigo,
            contacto.mensaje,
        )
        self.assertIn(
            pedido_b.codigo,
            contacto.mensaje,
        )
        self.assertIn(
            "1 × Pepino sensorial",
            contacto.mensaje,
        )
        self.assertIn(
            "2 × Pepino sensorial",
            contacto.mensaje,
        )
        self.assertIn(
            "Saldo total pendiente: $20.000",
            contacto.mensaje,
        )

