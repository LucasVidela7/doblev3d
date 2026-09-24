from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import ConfiguracionCatalogo, Insumo


@override_settings(SECURE_SSL_REDIRECT=False)
class InsumosGestionTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="qa-insumos",
            password="test",
            is_staff=True,
        )
        self.client.force_login(self.user)
        self.config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        self.config.incremento_insumos_por_defecto = Decimal("15.00")
        self.config.save(update_fields=["incremento_insumos_por_defecto"])

    def test_costo_unitario_y_provision_general(self):
        insumo = Insumo.objects.create(
            nombre="Argolla llavero",
            tipo_uso="PRODUCTO",
            precio_compra=Decimal("8000"),
            cantidad_compra=Decimal("100"),
            stock=Decimal("100"),
        )

        self.assertEqual(insumo.costo_unitario, Decimal("80"))
        self.assertEqual(insumo.incremento_efectivo, Decimal("15.00"))
        self.assertEqual(insumo.costo_unitario_aplicado, Decimal("92.0000"))
        self.assertTrue(insumo.usa_incremento_general)

    def test_incremento_particular_reemplaza_general(self):
        insumo = Insumo.objects.create(
            nombre="Imán circular",
            tipo_uso="PRODUCTO",
            precio_compra=Decimal("8000"),
            cantidad_compra=Decimal("100"),
            incremento_personalizado=Decimal("20"),
        )

        self.assertEqual(insumo.incremento_efectivo, Decimal("20"))
        self.assertEqual(insumo.costo_unitario_aplicado, Decimal("96.0"))
        self.assertFalse(insumo.usa_incremento_general)

    def test_puede_crear_insumo_de_empaque_desde_gestion(self):
        response = self.client.post(
            reverse("productos:insumo_nuevo"),
            {
                "nombre": "Doypack mediana",
                "tipo_uso": "EMPAQUE",
                "unidad_medida": "UNIDAD",
                "precio_compra": "12500",
                "cantidad_compra": "50",
                "stock": "30",
                "proveedor": "Proveedor packaging",
                "url_referencia": "https://example.com/doypack",
                "incremento_personalizado": "",
                "activo": "on",
            },
        )

        self.assertRedirects(response, reverse("productos:insumos"))
        insumo = Insumo.objects.get(nombre="Doypack mediana")
        self.assertEqual(insumo.tipo_uso, "EMPAQUE")
        self.assertEqual(insumo.costo_unitario, Decimal("250"))
        self.assertEqual(insumo.incremento_efectivo, Decimal("15.00"))
        self.assertEqual(insumo.proveedor, "Proveedor packaging")

    def test_listado_muestra_costos_y_submenu(self):
        Insumo.objects.create(
            nombre="Argolla test",
            tipo_uso="PRODUCTO",
            precio_compra=Decimal("8000"),
            cantidad_compra=Decimal("100"),
            stock=Decimal("20"),
        )

        response = self.client.get(reverse("productos:insumos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Argolla test")
        self.assertContains(response, "COSTO UNITARIO")
        self.assertContains(response, "COSTO APLICADO")
        self.assertContains(response, "PRODUCTOS")
        self.assertContains(response, "INSUMOS")
        self.assertContains(response, "15")

    def test_configuracion_actualiza_incremento_general(self):
        response = self.client.post(
            reverse("dashboard:configuracion"),
            {
                "config_seccion": "costos",
                "incremento_insumos_por_defecto": "18.5",
                "redondeo_precio_producto": "100",
                "metricas_retencion_dias": "180",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("#costos", response.url)
        self.config.refresh_from_db()
        self.assertEqual(
            self.config.incremento_insumos_por_defecto,
            Decimal("18.50"),
        )

    def test_editar_precio_recalcula_costo(self):
        insumo = Insumo.objects.create(
            nombre="Bolsa despacho",
            tipo_uso="DESPACHO",
            precio_compra=Decimal("10000"),
            cantidad_compra=Decimal("100"),
            stock=Decimal("50"),
        )

        response = self.client.post(
            reverse("productos:insumo_editar", args=[insumo.id]),
            {
                "nombre": insumo.nombre,
                "tipo_uso": "DESPACHO",
                "unidad_medida": "UNIDAD",
                "precio_compra": "12000",
                "cantidad_compra": "100",
                "stock": "50",
                "proveedor": "",
                "url_referencia": "",
                "incremento_personalizado": "",
                "activo": "on",
            },
        )

        self.assertRedirects(response, reverse("productos:insumos"))
        insumo.refresh_from_db()
        self.assertEqual(insumo.costo_unitario, Decimal("120"))
        self.assertEqual(insumo.costo_unitario_aplicado, Decimal("138.0000"))
