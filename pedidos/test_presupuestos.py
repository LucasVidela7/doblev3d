from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from costos.models import ConfiguracionCostos
from kits.models import Kit, KitComponente
from productos.models import Producto, TipoProducto
from productos.image_models import ProductoImagen

from .models import (
    DetallePedido,
    DetallePresupuesto,
    Pedido,
    Presupuesto,
)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    },
)
class PresupuestosTests(TestCase):
    def setUp(self):
        ConfiguracionCostos.objects.create(
            nombre="Costos presupuestos QA",
            coste_plastico_kg=Decimal("20000"),
            coste_plastico_kg_cantidad=Decimal("14000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        self.tipo = TipoProducto.objects.create(
            nombre="Tipo presupuesto QA",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Producto presupuesto QA",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=30,
            peso_gramos=Decimal("100"),
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            personalizable=False,
            stock=5,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=False,
        )
        self.cliente = Cliente.objects.create(
            nombre="Cliente presupuesto QA",
            activo=True,
        )
        self.usuario = get_user_model().objects.create_user(
            username="qa-presupuestos",
            password="ClaveSegura-12345",
        )
        self.client.force_login(self.usuario)

    def _crear_presupuesto(self, cantidad=2, total="9000"):
        return self.client.post(
            reverse("pedidos:nuevo"),
            data={
                "cliente": str(self.cliente.id),
                "fecha_entrega": "",
                "observaciones": "Consulta por WhatsApp",
                "item_indice": ["1"],
                "tipo_item_1": "PRODUCTO",
                "producto_1": str(self.producto.id),
                "cantidad_1": str(cantidad),
                "precio_total_producto_1": total,
                "precio_unitario_1": "",
                "precio_producto_manual_1": "1",
            },
        )

    def test_nuevo_presupuesto_carga_menu_y_tema_global(self):
        respuesta = self.client.get(
            reverse("pedidos:nuevo")
        )

        self.assertEqual(respuesta.status_code, 200)
        contenido = respuesta.content.decode()
        self.assertIn('id="dvManagementMenu"', contenido)
        self.assertRegex(
            contenido,
            r"/static/shared/management_menu(?:\.[0-9a-f]+)?\.css",
        )
        self.assertRegex(
            contenido,
            r"/static/shared/theme(?:\.[0-9a-f]+)?\.css",
        )
        self.assertIn(
            'id="dv-pedido-form-style"',
            contenido,
        )

    def test_nuevo_crea_presupuesto_y_no_pedido(self):
        respuesta = self._crear_presupuesto()

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(Pedido.objects.count(), 0)
        presupuesto = Presupuesto.objects.get()
        self.assertEqual(presupuesto.estado, "PENDIENTE")
        self.assertEqual(presupuesto.cliente, self.cliente)
        self.assertEqual(presupuesto.total, Decimal("9000.00"))
        self.assertEqual(
            respuesta.url,
            reverse(
                "pedidos:presupuesto_detalle",
                args=[presupuesto.id],
            ),
        )

        detalle = DetallePresupuesto.objects.get(
            presupuesto=presupuesto,
        )
        self.assertEqual(detalle.cantidad, 2)
        self.assertEqual(
            detalle.precio_unitario,
            Decimal("4500.00"),
        )

    def test_detalle_muestra_subtotales_y_descuentos(self):
        self._crear_presupuesto()
        presupuesto = Presupuesto.objects.get()

        respuesta = self.client.get(
            reverse(
                "pedidos:presupuesto_detalle",
                args=[presupuesto.id],
            )
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, presupuesto.codigo)
        self.assertContains(respuesta, "SUBTOTAL LISTA")
        self.assertContains(respuesta, "DESCUENTOS")
        self.assertContains(respuesta, "TOTAL PRESUPUESTADO")

    def test_detalle_prioriza_aprobar_y_mueve_editar_al_menu(self):
        self._crear_presupuesto()
        presupuesto = Presupuesto.objects.get()

        respuesta = self.client.get(
            reverse(
                "pedidos:presupuesto_detalle",
                args=[presupuesto.id],
            )
        )

        contenido = respuesta.content.decode()
        self.assertIn("data-dv-primary", contenido)
        self.assertIn(
            "APROBAR Y CREAR PEDIDO",
            contenido,
        )
        self.assertIn(
            'class="dv-page-overflow budget-actions-menu"',
            contenido,
        )
        self.assertGreater(
            contenido.index("EDITAR"),
            contenido.index("dv-page-overflow__menu"),
        )

    def test_mensajes_de_presupuesto_se_renderizan_para_toast(self):
        respuesta = self._crear_presupuesto()
        presupuesto = Presupuesto.objects.get()

        detalle = self.client.get(
            respuesta.url
        )
        self.assertContains(
            detalle,
            'data-dv-toast-type="success"',
        )
        self.assertContains(
            detalle,
            f"{presupuesto.codigo} creado correctamente.",
        )

        self.client.post(
            reverse(
                "pedidos:presupuesto_rechazar",
                args=[presupuesto.id],
            )
        )
        error = self.client.post(
            reverse(
                "pedidos:presupuesto_aprobar",
                args=[presupuesto.id],
            ),
            follow=True,
        )
        self.assertContains(
            error,
            'data-dv-toast-type="error"',
        )
        self.assertContains(
            error,
            "El presupuesto ya fue resuelto.",
        )

    def test_editar_presupuesto_respeta_tema_y_contexto(self):
        self._crear_presupuesto()
        presupuesto = Presupuesto.objects.get()

        respuesta = self.client.get(
            reverse(
                "pedidos:presupuesto_editar",
                args=[presupuesto.id],
            )
        )

        contenido = respuesta.content.decode()
        self.assertIn(
            "const esPresupuesto = true;",
            contenido,
        )
        self.assertIn(
            "Ítems del presupuesto",
            contenido,
        )
        self.assertIn(
            "background:var(--dv-surface,#fff)",
            contenido,
        )
        self.assertIn(
            "background:var(--dv-brand-blue,#134a9a)!important",
            contenido,
        )
        self.assertIn(
            "--dv-form-ink:var(--dv-text,#25282d)",
            contenido,
        )

    def test_presupuesto_pendiente_se_puede_editar(self):
        self._crear_presupuesto()
        presupuesto = Presupuesto.objects.get()

        respuesta = self.client.post(
            reverse(
                "pedidos:presupuesto_editar",
                args=[presupuesto.id],
            ),
            data={
                "cliente": str(self.cliente.id),
                "fecha_entrega": "",
                "observaciones": "Actualizado",
                "item_indice": ["1"],
                "tipo_item_1": "PRODUCTO",
                "producto_1": str(self.producto.id),
                "cantidad_1": "1",
                "precio_total_producto_1": "6000",
                "precio_unitario_1": "",
                "precio_producto_manual_1": "1",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        presupuesto.refresh_from_db()
        self.assertEqual(
            presupuesto.observaciones,
            "Actualizado",
        )
        self.assertEqual(
            presupuesto.total,
            Decimal("6000.00"),
        )
        self.assertEqual(Pedido.objects.count(), 0)

    def test_aprobar_convierte_presupuesto_en_pedido(self):
        self._crear_presupuesto()
        presupuesto = Presupuesto.objects.get()
        precio_cotizado = presupuesto.detalles.get().precio_unitario

        respuesta = self.client.post(
            reverse(
                "pedidos:presupuesto_aprobar",
                args=[presupuesto.id],
            )
        )

        self.assertEqual(respuesta.status_code, 302)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "APROBADO")
        self.assertIsNotNone(presupuesto.pedido_generado_id)

        pedido = Pedido.objects.get()
        self.assertEqual(pedido.cliente, self.cliente)
        detalle = DetallePedido.objects.get(pedido=pedido)
        self.assertEqual(detalle.precio_unitario, precio_cotizado)
        self.assertEqual(
            pedido.presupuesto_origen.id,
            presupuesto.id,
        )
        self.assertEqual(
            respuesta.url,
            reverse("pedidos:detalle", args=[pedido.id]),
        )

    def test_rechazar_no_crea_pedido(self):
        self._crear_presupuesto()
        presupuesto = Presupuesto.objects.get()

        respuesta = self.client.post(
            reverse(
                "pedidos:presupuesto_rechazar",
                args=[presupuesto.id],
            )
        )

        self.assertEqual(respuesta.status_code, 302)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "RECHAZADO")
        self.assertEqual(Pedido.objects.count(), 0)

    def test_listado_filtra_por_estado(self):
        pendiente = Presupuesto.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        rechazado = Presupuesto.objects.create(
            cliente=self.cliente,
            estado="RECHAZADO",
        )

        respuesta = self.client.get(
            reverse("pedidos:presupuestos"),
            {"estado": "PENDIENTE"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, pendiente.codigo)
        self.assertNotContains(respuesta, rechazado.codigo)
        self.assertEqual(
            respuesta.context["estado_seleccionado"],
            "PENDIENTE",
        )

    def test_fotos_aparecen_en_presupuesto_y_formulario(self):
        ProductoImagen.objects.create(
            producto=self.producto,
            file_id="presupuesto-thumb",
            url="https://example.com/presupuesto.jpg",
            thumbnail_url="https://example.com/presupuesto-thumb.jpg",
            orden=1,
        )
        self._crear_presupuesto()
        presupuesto = Presupuesto.objects.get()

        listado = self.client.get(
            reverse("pedidos:presupuestos")
        )
        detalle = self.client.get(
            reverse(
                "pedidos:presupuesto_detalle",
                args=[presupuesto.id],
            )
        )
        nuevo = self.client.get(
            reverse("pedidos:nuevo")
        )

        for respuesta in (listado, detalle, nuevo):
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(
                respuesta,
                "https://example.com/presupuesto-thumb.jpg",
            )

    def test_snapshot_de_kit_se_conserva_al_aprobar_presupuesto(self):
        kit = Kit.objects.create(
            nombre="Kit snapshot presupuesto",
            modalidad="FIJO",
            cantidad_productos=2,
            precio=Decimal("12000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=self.producto,
            cantidad=2,
        )

        respuesta = self.client.post(
            reverse("pedidos:nuevo"),
            data={
                "cliente": str(self.cliente.id),
                "fecha_entrega": "",
                "observaciones": "",
                "item_indice": ["1"],
                "tipo_item_1": "KIT",
                "kit_1": str(kit.id),
                "cantidad_1": "2",
                "precio_kit_manual_1": "0",
            },
        )
        self.assertEqual(respuesta.status_code, 302)

        presupuesto = Presupuesto.objects.get()
        detalle = presupuesto.detalles.get()
        snapshot_original = dict(detalle.kit_snapshot)

        self.assertEqual(
            snapshot_original["nombre"],
            "Kit snapshot presupuesto",
        )
        self.assertEqual(
            snapshot_original["componentes"][0]["cantidad_total"],
            4,
        )

        kit.nombre = "Kit cambiado después"
        kit.precio = Decimal("25000")
        kit.save(update_fields=["nombre", "precio"])

        respuesta = self.client.post(
            reverse(
                "pedidos:presupuesto_aprobar",
                args=[presupuesto.id],
            )
        )
        self.assertEqual(respuesta.status_code, 302)

        pedido = Pedido.objects.get()
        detalle_pedido = pedido.detalles.get()
        self.assertEqual(
            detalle_pedido.kit_snapshot["nombre"],
            "Kit snapshot presupuesto",
        )
        self.assertEqual(
            detalle_pedido.kit_snapshot["precio_base"],
            snapshot_original["precio_base"],
        )



    def test_pedido_aprobado_muestra_paso_para_avisar_al_cliente(self):
        self.cliente.telefono = "11 5555 4444"
        self.cliente.save(update_fields=["telefono"])
        self._crear_presupuesto()
        presupuesto = Presupuesto.objects.get()

        self.client.post(
            reverse(
                "pedidos:presupuesto_aprobar",
                args=[presupuesto.id],
            )
        )
        pedido = Pedido.objects.get()

        detalle = self.client.get(
            reverse("pedidos:detalle", args=[pedido.id])
        )
        self.assertEqual(detalle.status_code, 200)
        self.assertContains(
            detalle,
            "Avisar aprobación al cliente",
        )
        self.assertContains(detalle, "AVISAR POR WHATSAPP")
        self.assertContains(detalle, "VER DETALLE PÚBLICO")

        self.client.get(
            reverse(
                "clientes:whatsapp",
                args=[self.cliente.id],
            ),
            {
                "motivo": "PEDIDO_APROBADO",
                "pedido": pedido.id,
            },
        )

        detalle = self.client.get(
            reverse("pedidos:detalle", args=[pedido.id])
        )
        self.assertContains(
            detalle,
            "Contacto de aprobación iniciado",
        )
        self.assertContains(detalle, "✓ CONTACTO INICIADO")
