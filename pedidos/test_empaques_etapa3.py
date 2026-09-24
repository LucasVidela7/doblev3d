from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from kits.models import Kit
from kits.precio_fijo_combinado import calcular_escenarios_kit_fijo
from productos.models import (
    ConfiguracionCatalogo,
    Insumo,
    Producto,
    ProductoInsumo,
    TipoProducto,
)

from .empaques import sugerir_regla_empaque
from .models import (
    DetallePedido,
    Pedido,
    PedidoEmpaque,
    ReglaEmpaque,
)


@override_settings(SECURE_SSL_REDIRECT=False)
class EmpaquesEtapa3Tests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="qa-empaques",
            password="test",
            is_staff=True,
        )
        self.client.force_login(usuario)

        self.cliente = Cliente.objects.create(
            nombre="Cliente empaque",
            activo=True,
        )
        self.tipo = TipoProducto.objects.create(
            nombre="Tipo empaque",
            activo=True,
        )
        self.config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        self.config.incremento_insumos_por_defecto = Decimal("0")
        self.config.provision_empaque_unitaria = Decimal("50")
        self.config.redondeo_precio_producto = 100
        self.config.save(
            update_fields=[
                "incremento_insumos_por_defecto",
                "provision_empaque_unitaria",
                "redondeo_precio_producto",
            ]
        )
        cache.clear()

        self.producto = Producto.objects.create(
            nombre="Llavero empaque",
            categoria="PRODUCTO",
            tipo=self.tipo,
            margen_ganancia=Decimal("50"),
            requiere_impresion=False,
            activo=True,
            solo_produccion=False,
            stock=20,
        )
        self.argolla = Insumo.objects.create(
            nombre="Argolla etapa 3",
            tipo_uso="PRODUCTO",
            unidad_medida="UNIDAD",
            precio_compra=Decimal("1000"),
            cantidad_compra=Decimal("10"),
            stock=Decimal("100"),
            incremento_personalizado=Decimal("0"),
        )
        ProductoInsumo.objects.create(
            producto=self.producto,
            insumo=self.argolla,
            cantidad=Decimal("1"),
        )

        self.doypack_chica = Insumo.objects.create(
            nombre="Doypack chica",
            tipo_uso="EMPAQUE",
            unidad_medida="UNIDAD",
            precio_compra=Decimal("2000"),
            cantidad_compra=Decimal("20"),
            stock=Decimal("10"),
            incremento_personalizado=Decimal("0"),
        )
        self.doypack_grande = Insumo.objects.create(
            nombre="Doypack grande",
            tipo_uso="EMPAQUE",
            unidad_medida="UNIDAD",
            precio_compra=Decimal("6000"),
            cantidad_compra=Decimal("20"),
            stock=Decimal("8"),
            incremento_personalizado=Decimal("0"),
        )

    def _pedido_suelto(self, cantidad=6, precio="300"):
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="PRODUCTO",
            producto=self.producto,
            cantidad=cantidad,
            precio_unitario=Decimal(precio),
            costo_unitario=Decimal("100"),
            estado="PENDIENTE",
        )
        return pedido

    def test_provision_empaque_entra_al_precio_pero_no_al_costo_productivo(self):
        self.assertEqual(
            self.producto.costo_productivo_total,
            Decimal("100"),
        )
        self.assertEqual(
            self.producto.provision_empaque_comercial,
            Decimal("50"),
        )
        self.assertEqual(
            self.producto.costo_comercial_total,
            Decimal("150"),
        )
        self.assertEqual(
            self.producto.subtotal,
            Decimal("300"),
        )

    def test_catalogo_no_expone_concepto_empaque_al_cliente(self):
        response = self.client.get(reverse("catalogo_productos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.producto.nombre)
        self.assertContains(response, "$ 300")
        self.assertNotContains(response, "Provisión comercial de empaque")
        self.assertNotContains(response, "Costo de empaque")
        self.assertNotContains(response, "Doypack")

    def test_kit_fijo_aplica_provision_una_sola_vez(self):
        otro = Producto.objects.create(
            nombre="Segundo producto kit",
            categoria="PRODUCTO",
            tipo=self.tipo,
            margen_ganancia=Decimal("50"),
            requiere_impresion=False,
            activo=True,
            solo_produccion=False,
        )
        ProductoInsumo.objects.create(
            producto=otro,
            insumo=self.argolla,
            cantidad=Decimal("1"),
        )

        calculo = calcular_escenarios_kit_fijo(
            [
                {"producto": self.producto, "cantidad": 1},
                {"producto": otro, "cantidad": 1},
            ]
        )

        self.assertEqual(calculo["provision_empaque"], Decimal("50"))
        self.assertEqual(calculo["costo_total"], Decimal("250"))

    def test_regla_general_sugiere_empaque_por_cantidad(self):
        ReglaEmpaque.objects.create(
            nombre="Chica 1 a 2",
            insumo=self.doypack_chica,
            desde_unidades=1,
            hasta_unidades=2,
            prioridad=100,
        )
        ReglaEmpaque.objects.create(
            nombre="Grande 6 a 10",
            insumo=self.doypack_grande,
            desde_unidades=6,
            hasta_unidades=10,
            prioridad=100,
        )

        self.assertEqual(
            sugerir_regla_empaque(2).insumo,
            self.doypack_chica,
        )
        self.assertEqual(
            sugerir_regla_empaque(6).insumo,
            self.doypack_grande,
        )

    def test_regla_especifica_de_kit_prioriza_sobre_general(self):
        kit = Kit.objects.create(
            nombre="Kit especial empaque",
            modalidad="FIJO",
            precio=Decimal("5000"),
            activo=True,
        )
        general = ReglaEmpaque.objects.create(
            nombre="General",
            insumo=self.doypack_chica,
            alcance="GENERAL",
            desde_unidades=1,
            hasta_unidades=10,
            prioridad=1,
        )
        especifica = ReglaEmpaque.objects.create(
            nombre="Kit especial",
            insumo=self.doypack_grande,
            alcance="KIT",
            kit=kit,
            desde_unidades=1,
            hasta_unidades=10,
            prioridad=100,
        )

        sugerida = sugerir_regla_empaque(2, kit=kit)

        self.assertNotEqual(sugerida, general)
        self.assertEqual(sugerida, especifica)

    def test_detalle_sugiere_empaque_para_seis_productos_sueltos(self):
        pedido = self._pedido_suelto(cantidad=6)
        ReglaEmpaque.objects.create(
            nombre="Grande 6 a 10",
            insumo=self.doypack_grande,
            desde_unidades=6,
            hasta_unidades=10,
        )

        response = self.client.get(
            reverse("pedidos:detalle", args=[pedido.id])
        )

        self.assertEqual(response.status_code, 200)
        paquete = response.context["paquete_sueltos"]
        self.assertIsNotNone(paquete)
        self.assertEqual(paquete["unidades_contenido"], 6)
        self.assertEqual(
            paquete["empaque_sugerido"],
            self.doypack_grande,
        )
        self.assertContains(response, "EMPAQUE SUGERIDO")
        self.assertContains(response, "Doypack grande")

    def test_usar_empaque_descuenta_stock_y_no_modifica_total_comercial(self):
        pedido = self._pedido_suelto(cantidad=6)
        total_antes = pedido.total

        response = self.client.post(
            reverse("pedidos:usar_empaque", args=[pedido.id]),
            {
                "clave_paquete": "sueltos",
                "insumo_id": self.doypack_grande.id,
                "cantidad": "1",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.doypack_grande.refresh_from_db()
        pedido.refresh_from_db()
        uso = PedidoEmpaque.objects.get(
            pedido=pedido,
            clave_paquete="sueltos",
        )

        self.assertEqual(self.doypack_grande.stock, Decimal("7"))
        self.assertEqual(uso.cantidad, Decimal("1.000"))
        self.assertEqual(
            uso.costo_unitario_snapshot,
            Decimal("300.0000"),
        )
        self.assertEqual(
            uso.costo_total_snapshot,
            Decimal("300.0000"),
        )
        self.assertEqual(
            pedido.costo_empaque_real,
            Decimal("300.0000"),
        )
        self.assertEqual(pedido.total, total_antes)

    def test_cambiar_empaque_restaura_anterior_y_descuenta_nuevo(self):
        pedido = self._pedido_suelto(cantidad=2)

        self.client.post(
            reverse("pedidos:usar_empaque", args=[pedido.id]),
            {
                "clave_paquete": "sueltos",
                "insumo_id": self.doypack_chica.id,
                "cantidad": "1",
            },
        )
        self.client.post(
            reverse("pedidos:usar_empaque", args=[pedido.id]),
            {
                "clave_paquete": "sueltos",
                "insumo_id": self.doypack_grande.id,
                "cantidad": "1",
            },
        )

        self.doypack_chica.refresh_from_db()
        self.doypack_grande.refresh_from_db()
        uso = PedidoEmpaque.objects.get(
            pedido=pedido,
            clave_paquete="sueltos",
        )

        self.assertEqual(self.doypack_chica.stock, Decimal("10"))
        self.assertEqual(self.doypack_grande.stock, Decimal("7"))
        self.assertEqual(uso.insumo, self.doypack_grande)

    def test_liberar_empaque_devuelve_stock(self):
        pedido = self._pedido_suelto(cantidad=6)
        self.client.post(
            reverse("pedidos:usar_empaque", args=[pedido.id]),
            {
                "clave_paquete": "sueltos",
                "insumo_id": self.doypack_grande.id,
                "cantidad": "1",
            },
        )

        response = self.client.post(
            reverse("pedidos:liberar_empaque", args=[pedido.id]),
            {"clave_paquete": "sueltos"},
        )

        self.assertEqual(response.status_code, 302)
        self.doypack_grande.refresh_from_db()
        self.assertEqual(self.doypack_grande.stock, Decimal("8"))
        self.assertFalse(
            PedidoEmpaque.objects.filter(pedido=pedido).exists()
        )

    def test_cancelar_pedido_devuelve_stock_de_empaque(self):
        pedido = self._pedido_suelto(cantidad=6)
        self.client.post(
            reverse("pedidos:usar_empaque", args=[pedido.id]),
            {
                "clave_paquete": "sueltos",
                "insumo_id": self.doypack_grande.id,
                "cantidad": "1",
            },
        )

        response = self.client.post(
            reverse("pedidos:cancelar", args=[pedido.id]),
            {"origen": "detalle"},
        )

        self.assertEqual(response.status_code, 302)
        self.doypack_grande.refresh_from_db()
        pedido.refresh_from_db()
        self.assertEqual(self.doypack_grande.stock, Decimal("8"))
        self.assertEqual(pedido.estado, "CANCELADO")
        self.assertFalse(
            PedidoEmpaque.objects.filter(pedido=pedido).exists()
        )

    def test_finanzas_suma_empaque_real_al_costo_del_pedido(self):
        pedido = self._pedido_suelto(cantidad=1, precio="300")
        PedidoEmpaque.objects.create(
            pedido=pedido,
            clave_paquete="sueltos",
            descripcion="Productos fuera de kits",
            unidades_contenido=1,
            insumo=self.doypack_chica,
            cantidad=Decimal("1"),
            costo_unitario_snapshot=Decimal("100"),
            costo_total_snapshot=Decimal("100"),
        )

        response = self.client.get(
            reverse("pedidos:finanzas"),
            {"vista": "rentabilidad"},
        )

        self.assertEqual(response.status_code, 200)
        filas = list(response.context["rentabilidad_pagina"])
        fila = next(
            item
            for item in filas
            if item["pedido"].id == pedido.id
        )
        self.assertEqual(fila["costo_empaque"], Decimal("100"))
        self.assertEqual(fila["costo"], Decimal("200"))
