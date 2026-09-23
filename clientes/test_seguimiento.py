from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from pedidos.models import (
    DetallePedido,
    Pago,
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
                "PEDIDO_LISTO_SALDO",
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
            "2 pedidos requieren seguimiento",
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
        self.assertNotIn(
            "1 × Pepino sensorial",
            contacto.mensaje,
        )
        self.assertNotIn(
            "2 × Pepino sensorial",
            contacto.mensaje,
        )
        self.assertIn(
            "Saldo total pendiente: $20.000",
            contacto.mensaje,
        )
        self.assertIn(
            "http://testserver"
            + reverse(
                "pedido_publico",
                args=[pedido_a.public_token],
            ),
            contacto.mensaje,
        )
        self.assertIn(
            "http://testserver"
            + reverse(
                "pedido_publico",
                args=[pedido_b.public_token],
            ),
            contacto.mensaje,
        )

    def test_whatsapp_multiples_pedidos_usa_plantilla_configurada(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.whatsapp_mensaje_cliente_multiples_pedidos = (
            "Hola {nombre} | {cantidad_pedidos} pedidos | "
            "{pedidos} | total pendiente {saldo_total}"
        )
        config.save(
            update_fields=[
                "whatsapp_mensaje_cliente_multiples_pedidos",
            ]
        )

        pedidos = []
        for precio in (Decimal("4000"), Decimal("6000")):
            pedido = Pedido.objects.create(
                cliente=self.cliente,
                estado="PENDIENTE",
            )
            DetallePedido.objects.create(
                pedido=pedido,
                tipo_item="PRODUCTO",
                producto=self.producto,
                cantidad=1,
                precio_unitario=precio,
            )
            pedidos.append(pedido)

        respuesta = self.client.get(
            reverse(
                "clientes:whatsapp",
                args=[self.cliente.id],
            ),
            {
                "motivo": "SALDO",
                "pedidos": ",".join(
                    str(pedido.id)
                    for pedido in pedidos
                ),
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        contacto = ContactoCliente.objects.get()
        self.assertIn("Hola Cliente | 2 pedidos", contacto.mensaje)
        self.assertIn("total pendiente 10.000", contacto.mensaje)
        for pedido in pedidos:
            self.assertIn(pedido.codigo, contacto.mensaje)
            self.assertIn(
                "http://testserver"
                + reverse(
                    "pedido_publico",
                    args=[pedido.public_token],
                ),
                contacto.mensaje,
            )



    def test_whatsapp_pedido_aprobado_incluye_url_publica_y_registra_contacto(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.whatsapp_mensaje_cliente_pedido_aprobado = (
            "Hola {nombre} | pedido {codigo} aprobado | {url} | total {total}"
        )
        config.save(
            update_fields=[
                "whatsapp_mensaje_cliente_pedido_aprobado",
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
            cantidad=1,
            precio_unitario=Decimal("9000"),
        )

        respuesta = self.client.get(
            reverse(
                "clientes:whatsapp",
                args=[self.cliente.id],
            ),
            {
                "motivo": "PEDIDO_APROBADO",
                "pedido": pedido.id,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        contacto = ContactoCliente.objects.get()
        self.assertEqual(contacto.motivo, "PEDIDO_APROBADO")
        self.assertEqual(contacto.referencia, pedido.codigo)
        self.assertIn(
            "http://testserver"
            + reverse(
                "pedido_publico",
                args=[pedido.public_token],
            ),
            contacto.mensaje,
        )
        self.assertIn(pedido.codigo, contacto.mensaje)
        self.assertIn("total 9.000", contacto.mensaje)


    def test_ahora_pedido_listo_con_saldo_coordina_pago_y_entrega(self):
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
                "clientes:detalle",
                args=[self.cliente.id],
            )
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "COORDINAR PAGO Y ENTREGA · WHATSAPP",
            count=1,
        )
        seguimientos = [
            item
            for item in respuesta.context["seguimientos"]
            if item["tipo"] == "PEDIDO_LISTO_SALDO"
        ]
        self.assertEqual(len(seguimientos), 1)
        self.assertEqual(
            seguimientos[0]["accion"],
            "COORDINAR PAGO Y ENTREGA",
        )
        self.assertIn(
            "motivo=PEDIDO_LISTO",
            seguimientos[0]["url"],
        )

    def test_detalle_pedido_listo_muestra_paso_de_entrega_y_registra_contacto(self):
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

        detalle = self.client.get(
            reverse("pedidos:detalle", args=[pedido.id])
        )
        self.assertEqual(detalle.status_code, 200)
        self.assertContains(detalle, "COMUNICACIÓN CON CLIENTE")
        self.assertContains(detalle, "Coordinar saldo y entrega")
        self.assertContains(
            detalle,
            "COORDINAR PAGO Y ENTREGA · WHATSAPP",
        )

        self.client.get(
            reverse(
                "clientes:whatsapp",
                args=[self.cliente.id],
            ),
            {
                "motivo": "PEDIDO_LISTO",
                "pedido": pedido.id,
            },
        )

        detalle = self.client.get(
            reverse("pedidos:detalle", args=[pedido.id])
        )
        self.assertContains(
            detalle,
            "Contacto con el cliente iniciado",
        )
        self.assertContains(
            detalle,
            "✓ CONTACTO INICIADO",
        )

    def test_whatsapp_listo_con_un_pago_incluye_pago_saldo_y_url(self):
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="LISTO",
        )
        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=1,
            precio_unitario=Decimal("10000"),
        )
        Pago.objects.create(
            pedido=pedido,
            monto=Decimal("3000"),
            medio="TRANSFERENCIA",
        )

        self.client.get(
            reverse(
                "clientes:whatsapp",
                args=[self.cliente.id],
            ),
            {
                "motivo": "PEDIDO_LISTO",
                "pedido": pedido.id,
            },
        )

        contacto = ContactoCliente.objects.get()
        self.assertIn("Hola Cliente", contacto.mensaje)
        self.assertIn("1 pago registrado", contacto.mensaje)
        self.assertIn("Pagado: $3.000", contacto.mensaje)
        self.assertIn("Saldo pendiente: $7.000", contacto.mensaje)
        self.assertIn(
            "Alias: doblev3d.mp - Lucas Andrés Videla",
            contacto.mensaje,
        )
        self.assertIn(
            "http://testserver"
            + reverse(
                "pedido_publico",
                args=[pedido.public_token],
            ),
            contacto.mensaje,
        )
        self.assertIn(
            "saldo pendiente y la entrega",
            contacto.mensaje,
        )

    def test_whatsapp_listo_con_dos_pagos_incluye_total_abonado(self):
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="LISTO",
        )
        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=1,
            precio_unitario=Decimal("15000"),
        )
        Pago.objects.create(
            pedido=pedido,
            monto=Decimal("4000"),
            medio="TRANSFERENCIA",
        )
        Pago.objects.create(
            pedido=pedido,
            monto=Decimal("6000"),
            medio="EFECTIVO",
        )

        self.client.get(
            reverse(
                "clientes:whatsapp",
                args=[self.cliente.id],
            ),
            {
                "motivo": "PEDIDO_LISTO",
                "pedido": pedido.id,
            },
        )

        contacto = ContactoCliente.objects.get()
        self.assertIn("2 pagos registrados", contacto.mensaje)
        self.assertIn("Pagado: $10.000", contacto.mensaje)
        self.assertIn("Saldo pendiente: $5.000", contacto.mensaje)
        self.assertIn(
            "Alias: doblev3d.mp - Lucas Andrés Videla",
            contacto.mensaje,
        )

    def test_whatsapp_multiple_muestra_pagos_y_url_de_cada_pedido(self):
        pedido_a = Pedido.objects.create(
            cliente=self.cliente,
            estado="LISTO",
        )
        DetallePedido.objects.create(
            pedido=pedido_a,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=1,
            precio_unitario=Decimal("10000"),
        )
        Pago.objects.create(
            pedido=pedido_a,
            monto=Decimal("10000"),
            medio="TRANSFERENCIA",
        )

        pedido_b = Pedido.objects.create(
            cliente=self.cliente,
            estado="PREPARANDO",
        )
        DetallePedido.objects.create(
            pedido=pedido_b,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=1,
            precio_unitario=Decimal("12000"),
        )
        Pago.objects.create(
            pedido=pedido_b,
            monto=Decimal("3000"),
            medio="TRANSFERENCIA",
        )
        Pago.objects.create(
            pedido=pedido_b,
            monto=Decimal("4000"),
            medio="EFECTIVO",
        )

        self.client.get(
            reverse(
                "clientes:whatsapp",
                args=[self.cliente.id],
            ),
            {
                "motivo": "PEDIDO_LISTO",
                "pedidos": f"{pedido_a.id},{pedido_b.id}",
            },
        )

        contacto = ContactoCliente.objects.get()
        self.assertIn("1 pago registrado", contacto.mensaje)
        self.assertIn("2 pagos registrados", contacto.mensaje)
        self.assertIn("Saldo pendiente: $5.000", contacto.mensaje)
        self.assertIn("Saldo total pendiente: $5.000", contacto.mensaje)
        self.assertEqual(
            contacto.mensaje.count(
                "Alias: doblev3d.mp - Lucas Andrés Videla"
            ),
            1,
        )
        for pedido in (pedido_a, pedido_b):
            self.assertIn(
                "http://testserver"
                + reverse(
                    "pedido_publico",
                    args=[pedido.public_token],
                ),
                contacto.mensaje,
            )

    def test_entregado_con_saldo_sigue_apareciendo_en_ahora(self):
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="ENTREGADO",
        )
        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=1,
            precio_unitario=Decimal("10000"),
        )
        Pago.objects.create(
            pedido=pedido,
            monto=Decimal("4000"),
            medio="TRANSFERENCIA",
        )

        respuesta = self.client.get(
            reverse(
                "clientes:detalle",
                args=[self.cliente.id],
            )
        )

        seguimientos = [
            item
            for item in respuesta.context["seguimientos"]
            if item["tipo"] == "SALDO"
        ]
        self.assertEqual(len(seguimientos), 1)
        self.assertIn("entregado", seguimientos[0]["titulo"])
        self.assertEqual(
            seguimientos[0]["accion"],
            "RECORDAR PAGO",
        )
        self.assertIn(
            "motivo=SALDO",
            seguimientos[0]["url"],
        )

    def test_alias_y_titular_configurados_se_usan_en_saldo(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.whatsapp_pago_alias = "doblev3d.test"
        config.whatsapp_pago_titular = "Titular Configurado"
        config.save(
            update_fields=[
                "whatsapp_pago_alias",
                "whatsapp_pago_titular",
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
            cantidad=1,
            precio_unitario=Decimal("8000"),
        )

        self.client.get(
            reverse(
                "clientes:whatsapp",
                args=[self.cliente.id],
            ),
            {
                "motivo": "SALDO",
                "pedido": pedido.id,
            },
        )

        contacto = ContactoCliente.objects.get()
        self.assertIn(
            "Alias: doblev3d.test - Titular Configurado",
            contacto.mensaje,
        )

    def test_pedido_listo_pagado_solo_coordina_entrega(self):
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
        Pago.objects.create(
            pedido=pedido,
            monto=Decimal("5000"),
            medio="TRANSFERENCIA",
        )

        respuesta = self.client.get(
            reverse(
                "clientes:detalle",
                args=[self.cliente.id],
            )
        )

        seguimientos = [
            item
            for item in respuesta.context["seguimientos"]
            if item["tipo"] == "PEDIDO_LISTO"
        ]
        self.assertEqual(len(seguimientos), 1)
        self.assertEqual(
            seguimientos[0]["accion"],
            "COORDINAR ENTREGA",
        )
        self.assertContains(
            respuesta,
            "COORDINAR ENTREGA · WHATSAPP",
            count=1,
        )

        self.client.get(
            reverse(
                "clientes:whatsapp",
                args=[self.cliente.id],
            ),
            {
                "motivo": "PEDIDO_LISTO",
                "pedido": pedido.id,
            },
        )
        contacto = ContactoCliente.objects.get()
        self.assertNotIn("Alias:", contacto.mensaje)

