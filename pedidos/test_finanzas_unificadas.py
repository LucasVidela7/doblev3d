from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from clientes.models import Cliente
from productos.models import Producto, TipoProducto

from .models import DetallePedido, Gasto, Pago, Pedido


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
class FinanzasUnificadasTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="finanzas-unificadas",
            password="ClaveSegura-12345",
        )
        self.client.force_login(usuario)

        self.cliente = Cliente.objects.create(
            nombre="Cliente finanzas QA",
            activo=True,
        )
        tipo = TipoProducto.objects.create(
            nombre="Tipo finanzas QA",
            activo=True,
        )
        producto = Producto.objects.create(
            nombre="Producto finanzas QA",
            categoria="PRODUCTO",
            tipo=tipo,
            peso_gramos=Decimal("100"),
            requiere_impresion=True,
            activo=True,
            solo_produccion=False,
        )
        self.pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        DetallePedido.objects.create(
            pedido=self.pedido,
            tipo_item="PRODUCTO",
            producto=producto,
            cantidad=1,
            precio_unitario=Decimal("5000"),
            costo_unitario=Decimal("1000"),
            estado="PENDIENTE",
        )

    def test_finanzas_incluye_cobros_y_acciones_en_modales(self):
        respuesta = self.client.get(
            reverse("pedidos:finanzas")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Centro financiero")
        self.assertContains(respuesta, "NECESITAN ATENCIÓN")
        self.assertContains(respuesta, "REGISTRAR COBRO")
        self.assertContains(respuesta, "modalCobro")
        self.assertContains(respuesta, "modalGasto")
        self.assertContains(respuesta, "modalCaja")
        self.assertEqual(
            respuesta.context["saldo_total_actual"],
            Decimal("5000"),
        )
        self.assertEqual(
            respuesta.context["pedidos_con_saldo_actual"],
            1,
        )

    def test_registrar_cobro_desde_finanzas_vuelve_a_cobros(self):
        periodo = timezone.localdate().strftime("%Y-%m")

        respuesta = self.client.post(
            reverse(
                "pedidos:registrar_pago",
                args=[self.pedido.id],
            ),
            data={
                "origen": "finanzas",
                "periodo": periodo,
                "monto": "2000",
                "medio": "TRANSFERENCIA",
                "observaciones": "Cobro desde Finanzas",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            respuesta.url,
            (
                f"{reverse('pedidos:finanzas')}"
                f"?periodo={periodo}#cobros"
            ),
        )
        self.assertEqual(Pago.objects.count(), 1)

        self.pedido.refresh_from_db()
        self.assertEqual(
            self.pedido.saldo_pendiente,
            Decimal("3000"),
        )

    def test_detalle_permite_registrar_pago_y_vuelve_al_pedido(self):
        detalle = self.client.get(
            reverse("pedidos:detalle", args=[self.pedido.id])
        )

        self.assertEqual(detalle.status_code, 200)
        self.assertContains(detalle, "REGISTRAR PAGO")
        self.assertContains(
            detalle,
            reverse(
                "pedidos:registrar_pago",
                args=[self.pedido.id],
            ),
        )

        respuesta = self.client.post(
            reverse(
                "pedidos:registrar_pago",
                args=[self.pedido.id],
            ),
            data={
                "origen": "detalle",
                "monto": "1500",
                "medio": "TRANSFERENCIA",
                "observaciones": "Cobro desde detalle",
            },
        )

        self.assertRedirects(
            respuesta,
            reverse("pedidos:detalle", args=[self.pedido.id]),
            fetch_redirect_response=False,
        )
        self.assertEqual(Pago.objects.count(), 1)
        self.assertEqual(
            Pago.objects.get().monto,
            Decimal("1500"),
        )

    def test_ruta_legacy_pagos_redirige_a_finanzas(self):
        respuesta = self.client.get(
            reverse("pedidos:pagos")
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertEqual(
            respuesta.url,
            f"{reverse('pedidos:finanzas')}#cobros",
        )

    def test_cobros_usa_vista_paginada_y_saldo_sql(self):
        respuesta = self.client.get(
            reverse("pedidos:finanzas"),
            {"vista": "cobros"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.context["vista"],
            "cobros",
        )
        self.assertEqual(
            respuesta.context["saldo_total_actual"],
            Decimal("5000"),
        )
        pagina = respuesta.context["cobros_pagina"]
        self.assertIsNotNone(pagina)
        self.assertEqual(
            pagina.paginator.per_page,
            20,
        )
        self.assertEqual(
            pagina.object_list[0].id,
            self.pedido.id,
        )

    def test_gastos_se_paginan_de_a_20(self):
        hoy = timezone.localdate()

        for numero in range(25):
            Gasto.objects.create(
                fecha_compra=hoy,
                tipo="OPERATIVO",
                categoria="OTRO",
                descripcion=f"Gasto {numero}",
                monto_total=Decimal("100"),
                medio_pago="EFECTIVO",
                cantidad_cuotas=1,
            )

        respuesta = self.client.get(
            reverse("pedidos:finanzas"),
            {"vista": "gastos"},
        )

        self.assertEqual(respuesta.status_code, 200)
        pagina = respuesta.context["gastos_pagina"]
        self.assertIsNotNone(pagina)
        self.assertEqual(
            pagina.paginator.per_page,
            20,
        )
        self.assertEqual(
            pagina.paginator.count,
            25,
        )
        self.assertEqual(len(pagina.object_list), 20)

    def test_resumen_no_carga_rentabilidad_historica_detallada(self):
        respuesta = self.client.get(
            reverse("pedidos:finanzas"),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.context["vista"],
            "resumen",
        )
        self.assertIsNone(
            respuesta.context["rentabilidad_pagina"],
        )
        self.assertIsNone(
            respuesta.context["gastos_pagina"],
        )
        self.assertIsNone(
            respuesta.context["cuotas_pagina"],
        )

