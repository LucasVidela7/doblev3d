from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from clientes.models import Cliente
from costos.models import ConfiguracionCostos
from productos.models import Producto, ProductoComponente, TipoProducto
from productos.image_models import ProductoImagen

from .models import DetallePedido, Pedido


class PrecioProductoApiTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="pedidos-precio-test",
            password="test-pass",
        )
        self.client.force_login(usuario)
        self.tipo = TipoProducto.objects.create(nombre="Test pedidos")
        ConfiguracionCostos.objects.create(
            nombre="Test",
            coste_plastico_kg=Decimal("20000"),
            tasa_fallos=Decimal("10"),
            coste_luz_hora=Decimal("100"),
            coste_amortizacion_hora=Decimal("200"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )

    def pieza(self, nombre, horas, minutos, peso):
        return Producto.objects.create(
            nombre=nombre,
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=horas,
            minutos=minutos,
            peso_gramos=Decimal(str(peso)),
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=True,
        )

    def test_api_calcula_precio_compuesto_desde_sus_piezas(self):
        cuerpo = self.pieza("Cuerpo", 1, 30, 80)
        tapa = self.pieza("Tapa", 0, 20, 15)

        producto = Producto.objects.create(
            nombre="Producto compuesto",
            categoria="PRODUCTO",
            tipo=self.tipo,
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            activo=True,
            tipo_fabricacion="COMPUESTO",
            solo_produccion=False,
        )

        ProductoComponente.objects.create(
            producto=producto,
            componente=cuerpo,
            cantidad=1,
        )
        ProductoComponente.objects.create(
            producto=producto,
            componente=tapa,
            cantidad=2,
        )

        Producto.objects.filter(pk=producto.pk).update(
            horas=0,
            minutos=0,
            peso_gramos=Decimal("0"),
        )

        respuesta = self.client.get(
            reverse("pedidos:precio_producto"),
            {
                "producto_id": producto.id,
                "cantidad": 10,
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()

        self.assertTrue(datos["ok"])
        self.assertTrue(datos["producto"]["es_compuesto"])
        self.assertGreater(datos["producto"]["precio_lista"], 0)
        self.assertGreater(datos["costo_productivo"], 0)
        self.assertGreater(datos["producto"]["peso_gramos"], 0)
        self.assertGreater(datos["producto"]["horas"], 0)

        for estrategia in ("conservador", "recomendado", "agresivo"):
            self.assertIn(estrategia, datos["escenarios"])
            self.assertGreater(
                datos["escenarios"][estrategia]["total_recomendado"],
                0,
            )
            self.assertGreater(
                datos["escenarios"][estrategia]["precio_unitario_pedido"],
                0,
            )


class AccionesPedidoEstadoTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="pedidos-acciones-test",
            password="test-pass",
        )
        self.client.force_login(usuario)
        self.cliente = Cliente.objects.create(
            nombre="Cliente test",
            activo=True,
        )
        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )

    def _estado(self, estado):
        self.pedido.estado = estado
        self.pedido.save(update_fields=["estado"])

    def test_editar_pendiente_carga_menu_y_tema_global(self):
        respuesta = self.client.get(
            reverse("pedidos:editar", args=[self.pedido.id])
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
        self.assertRegex(
            contenido,
            r"/static/shared/toasts(?:\.[0-9a-f]+)?\.js",
        )
        self.assertIn(
            'id="dv-pedido-form-style"',
            contenido,
        )

    def test_detalle_pendiente_muestra_cancelar_y_eliminar(self):
        respuesta = self.client.get(
            reverse("pedidos:detalle", args=[self.pedido.id])
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Cancelar pedido")
        self.assertContains(respuesta, "Eliminar pedido")
        self.assertContains(
            respuesta,
            'name="origen" value="detalle"',
        )

    def test_detalle_optimizado_no_duplica_editar(self):
        respuesta = self.client.get(
            reverse("pedidos:detalle", args=[self.pedido.id])
        )

        self.assertEqual(respuesta.status_code, 200)
        contenido = respuesta.content.decode()
        self.assertIn("PREPARACIÓN", contenido)
        self.assertEqual(contenido.count("Editar pedido"), 1)
        self.assertNotIn("← Dashboard", contenido)

    def test_editar_solo_se_permite_en_pendiente(self):
        for estado in ("PREPARANDO", "LISTO", "ENTREGADO", "CANCELADO"):
            self._estado(estado)
            respuesta = self.client.get(
                reverse("pedidos:editar", args=[self.pedido.id])
            )
            self.assertEqual(respuesta.status_code, 302)
            self.pedido.refresh_from_db()
            self.assertEqual(self.pedido.estado, estado)

    def test_fecha_entrega_se_puede_modificar_en_estados_activos(self):
        for estado in ("PENDIENTE", "PREPARANDO", "LISTO"):
            self._estado(estado)
            respuesta = self.client.post(
                reverse(
                    "pedidos:actualizar_fecha_entrega",
                    args=[self.pedido.id],
                ),
                {"fecha_entrega": "2026-10-15"},
            )
            self.assertRedirects(
                respuesta,
                reverse("pedidos:detalle", args=[self.pedido.id]),
                fetch_redirect_response=False,
            )
            self.pedido.refresh_from_db()
            self.assertEqual(
                self.pedido.fecha_entrega,
                date(2026, 10, 15),
            )

    def test_fecha_entrega_no_se_modifica_en_estados_finales(self):
        for estado in ("ENTREGADO", "CANCELADO"):
            self._estado(estado)
            self.pedido.fecha_entrega = date(2026, 10, 10)
            self.pedido.save(update_fields=["fecha_entrega"])

            respuesta = self.client.post(
                reverse(
                    "pedidos:actualizar_fecha_entrega",
                    args=[self.pedido.id],
                ),
                {"fecha_entrega": "2026-10-20"},
            )

            self.assertEqual(respuesta.status_code, 302)
            self.pedido.refresh_from_db()
            self.assertEqual(
                self.pedido.fecha_entrega,
                date(2026, 10, 10),
            )

    def test_cancelar_se_permite_mientras_pedido_esta_activo(self):
        for estado in ("PENDIENTE", "PREPARANDO", "LISTO"):
            self._estado(estado)
            respuesta = self.client.post(
                reverse("pedidos:cancelar", args=[self.pedido.id])
            )
            self.assertEqual(respuesta.status_code, 302)
            self.pedido.refresh_from_db()
            self.assertEqual(self.pedido.estado, "CANCELADO")

    def test_cancelar_no_se_permite_en_estados_finales(self):
        for estado in ("ENTREGADO", "CANCELADO"):
            self._estado(estado)
            respuesta = self.client.post(
                reverse("pedidos:cancelar", args=[self.pedido.id])
            )
            self.assertEqual(respuesta.status_code, 302)
            self.pedido.refresh_from_db()
            self.assertEqual(self.pedido.estado, estado)

    def test_eliminar_no_se_permite_fuera_de_pendiente(self):
        self._estado("PREPARANDO")
        respuesta = self.client.post(
            reverse("pedidos:eliminar", args=[self.pedido.id])
        )
        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Pedido.objects.filter(pk=self.pedido.id).exists())

    def test_entregar_requiere_estado_listo(self):
        respuesta = self.client.post(
            reverse("pedidos:entregar", args=[self.pedido.id])
        )
        self.assertEqual(respuesta.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, "PENDIENTE")

        self._estado("LISTO")
        respuesta = self.client.post(
            reverse("pedidos:entregar", args=[self.pedido.id])
        )
        self.assertEqual(respuesta.status_code, 302)
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, "ENTREGADO")

    def test_entregar_desde_cliente_vuelve_al_detalle(self):
        self._estado("LISTO")
        respuesta = self.client.post(
            reverse("pedidos:entregar", args=[self.pedido.id]),
            {
                "origen": "cliente",
                "cliente_id": str(self.cliente.id),
            },
        )
        self.assertRedirects(
            respuesta,
            reverse("clientes:detalle", args=[self.cliente.id]),
            fetch_redirect_response=False,
        )
        self.pedido.refresh_from_db()
        self.assertEqual(self.pedido.estado, "ENTREGADO")

    def test_detalle_pedido_muestra_foto_del_producto(self):
        tipo = TipoProducto.objects.create(
            nombre="Tipo detalle pedido",
        )
        producto = Producto.objects.create(
            nombre="Producto detalle pedido",
            categoria="PRODUCTO",
            tipo=tipo,
            requiere_impresion=True,
            activo=True,
        )
        DetallePedido.objects.create(
            pedido=self.pedido,
            tipo_item="PRODUCTO",
            producto=producto,
            cantidad=1,
            precio_unitario=Decimal("2500"),
            estado="PENDIENTE",
        )
        ProductoImagen.objects.create(
            producto=producto,
            file_id="pedido-thumb",
            url="https://example.com/pedido.jpg",
            thumbnail_url="https://example.com/pedido-thumb.jpg",
            orden=1,
        )

        respuesta = self.client.get(
            reverse("pedidos:detalle", args=[self.pedido.id])
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "https://example.com/pedido-thumb.jpg",
        )
        self.assertContains(
            respuesta,
            'class="pedido-thumb"',
        )

