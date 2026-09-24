from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from pedidos.models import Gasto
from productos.models import CompraInsumo, CompraInsumoItem, Insumo


@override_settings(SECURE_SSL_REDIRECT=False)
class ComprasInsumosTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="qa-compras-insumos",
            password="test",
            is_staff=True,
        )
        self.client.force_login(usuario)
        self.insumo = Insumo.objects.create(
            nombre="Argolla compra QA",
            tipo_uso="PRODUCTO",
            unidad_medida="UNIDAD",
            precio_compra=Decimal("1000"),
            cantidad_compra=Decimal("10"),
            costo_promedio_unitario=Decimal("100"),
            stock=Decimal("10"),
            activo=True,
        )

    def _registrar(self, insumo=None, cantidad="10", monto="2000"):
        insumo = insumo or self.insumo
        return self.client.post(
            reverse("productos:compra_insumo_registrar"),
            {
                "fecha_compra": timezone.localdate().isoformat(),
                "proveedor": "Proveedor QA",
                "medio_pago": "TRANSFERENCIA",
                "cantidad_cuotas": "1",
                "observaciones": "Compra test",
                "origen": "insumos",
                "insumo_id": [str(insumo.id)],
                "cantidad": [cantidad],
                "monto_linea": [monto],
            },
        )

    def test_compra_actualiza_stock_y_costo_promedio(self):
        respuesta = self._registrar()

        self.assertEqual(respuesta.status_code, 302)
        self.insumo.refresh_from_db()
        self.assertEqual(self.insumo.stock, Decimal("20.000"))
        self.assertEqual(
            self.insumo.costo_promedio_unitario,
            Decimal("150.0000"),
        )
        self.assertEqual(
            self.insumo.precio_compra,
            Decimal("2000.00"),
        )
        self.assertEqual(
            self.insumo.cantidad_compra,
            Decimal("10.000"),
        )

        compra = CompraInsumo.objects.get()
        item = CompraInsumoItem.objects.get(compra=compra)
        self.assertEqual(item.stock_anterior, Decimal("10.000"))
        self.assertEqual(
            item.costo_promedio_anterior,
            Decimal("100.0000"),
        )
        self.assertEqual(
            item.costo_promedio_nuevo,
            Decimal("150.0000"),
        )

    def test_compra_crea_gasto_y_movimiento_de_caja(self):
        self._registrar()

        compra = CompraInsumo.objects.select_related("gasto").get()
        gasto = compra.gasto
        self.assertEqual(gasto.tipo, "OPERATIVO")
        self.assertEqual(gasto.categoria, "INSUMOS")
        self.assertEqual(gasto.monto_total, Decimal("2000.00"))
        self.assertEqual(gasto.cuotas.count(), 1)
        cuota = gasto.cuotas.get()
        self.assertTrue(cuota.pagada)
        self.assertEqual(cuota.monto, Decimal("2000.00"))

    def test_compra_solo_empaque_se_clasifica_como_embalaje(self):
        bolsa = Insumo.objects.create(
            nombre="Bolsa compra QA",
            tipo_uso="EMPAQUE",
            unidad_medida="UNIDAD",
            precio_compra=Decimal("1000"),
            cantidad_compra=Decimal("10"),
            costo_promedio_unitario=Decimal("100"),
            stock=Decimal("5"),
            activo=True,
        )

        self._registrar(bolsa, cantidad="20", monto="4000")

        gasto = Gasto.objects.get()
        self.assertEqual(gasto.categoria, "EMBALAJE")

    def test_compra_stock_no_duplica_gasto_operativo(self):
        self._registrar()

        respuesta = self.client.get(
            reverse("pedidos:finanzas"),
            {"vista": "gastos"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.context["compras_stock_periodo"],
            Decimal("2000"),
        )
        self.assertEqual(
            respuesta.context["gastos_operativos"],
            Decimal("0"),
        )

    def test_gasto_enlazado_no_se_puede_eliminar_desde_finanzas(self):
        self._registrar()
        gasto = Gasto.objects.get()

        respuesta = self.client.post(
            reverse("pedidos:eliminar_gasto", args=[gasto.id]),
            {
                "periodo": timezone.localdate().strftime("%Y-%m"),
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        self.assertTrue(Gasto.objects.filter(id=gasto.id).exists())
        self.assertTrue(
            CompraInsumo.objects.filter(gasto_id=gasto.id).exists()
        )

    def test_tarjeta_genera_cuotas_pendientes(self):
        respuesta = self.client.post(
            reverse("productos:compra_insumo_registrar"),
            {
                "fecha_compra": timezone.localdate().isoformat(),
                "proveedor": "Proveedor tarjeta QA",
                "medio_pago": "TARJETA_CREDITO",
                "cantidad_cuotas": "3",
                "fecha_primera_cuota": timezone.localdate().isoformat(),
                "observaciones": "",
                "origen": "insumos",
                "insumo_id": [str(self.insumo.id)],
                "cantidad": ["30"],
                "monto_linea": ["3000"],
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        gasto = Gasto.objects.get()
        self.assertEqual(gasto.cuotas.count(), 3)
        self.assertFalse(gasto.cuotas.filter(pagada=True).exists())
        self.assertEqual(
            sum(
                (cuota.monto for cuota in gasto.cuotas.all()),
                Decimal("0"),
            ),
            Decimal("3000.00"),
        )
