from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from costos.models import ConfiguracionCostos
from produccion.models import Produccion

from .models import Producto, TipoProducto
from .views import _enriquecer_productos


class CentroProductosTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="centro-productos",
            password="test12345",
        )
        self.client.force_login(usuario)

        self.tipo = TipoProducto.objects.create(
            nombre="Sensoriales",
        )
        ConfiguracionCostos.objects.create(
            nombre="Costos test",
            coste_plastico_kg=Decimal("20000"),
            tasa_fallos=Decimal("10"),
            coste_luz_hora=Decimal("100"),
            coste_amortizacion_hora=Decimal("200"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        self.producto = Producto.objects.create(
            nombre="Pepino sensorial",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=1,
            minutos=20,
            peso_gramos=Decimal("40"),
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            stock=2,
            activo=True,
        )

    def test_margen_producto_se_aplica_sobre_costo_productivo_completo(self):
        costo_productivo = (
            self.producto.costo
            + self.producto.seguro
        )
        precio = self.producto.subtotal
        margen_real = (
            (precio - costo_productivo)
            / precio
            * Decimal("100")
        )
        precio_minimo = (
            costo_productivo
            / (Decimal("1") - Decimal("0.60"))
        )

        self.assertGreaterEqual(
            margen_real,
            Decimal("60"),
        )
        self.assertGreaterEqual(
            precio,
            precio_minimo,
        )
        self.assertLess(
            precio - precio_minimo,
            Decimal("500"),
        )

    def test_listado_renderiza_centro_operativo(self):
        respuesta = self.client.get(
            reverse("productos:lista"),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "Stock, demanda, producción, costos y rentabilidad",
        )
        self.assertContains(respuesta, "NECESITAN ATENCIÓN")
        self.assertContains(respuesta, "Pepino sensorial")
        self.assertIn("metricas", respuesta.context)
        self.assertEqual(
            respuesta.context["metricas"]["total"],
            1,
        )

    def test_listado_filtra_stock_bajo(self):
        respuesta = self.client.get(
            reverse("productos:lista"),
            {"estado": "bajo_stock"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            list(respuesta.context["productos"]),
            [self.producto],
        )

    def test_enriquecimiento_integra_planificacion(self):
        Produccion.objects.create(
            producto=self.producto,
            cantidad=3,
            destino="STOCK",
            estado="PENDIENTE",
            tiempo_impresion_minutos=240,
        )

        producto = (
            Producto.objects
            .select_related("tipo")
            .prefetch_related("imagenes")
            .get(pk=self.producto.pk)
        )
        producto.imagenes_entorno = []
        _enriquecer_productos([producto])

        self.assertEqual(producto.planificadas, 3)
        self.assertEqual(producto.imprimiendo, 0)
        self.assertGreater(producto.costo_productivo, Decimal("0"))
        self.assertGreater(producto.subtotal, Decimal("0"))

    def test_detalle_muestra_estado_operativo(self):
        Produccion.objects.create(
            producto=self.producto,
            cantidad=2,
            destino="STOCK",
            estado="IMPRIMIENDO",
            tiempo_impresion_minutos=160,
        )

        respuesta = self.client.get(
            reverse(
                "productos:detalle",
                args=[self.producto.id],
            ),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "PRODUCCIÓN Y DEMANDA")
        self.assertContains(respuesta, "COSTOS Y RENTABILIDAD")
        self.assertContains(respuesta, "MOVIMIENTOS DE STOCK")
        self.assertEqual(
            respuesta.context["producto"].imprimiendo,
            2,
        )

    def test_formulario_usa_flujo_guiado(self):
        respuesta = self.client.get(
            reverse(
                "productos:editar",
                args=[self.producto.id],
            ),
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "1 · IDENTIDAD")
        self.assertContains(respuesta, "2 · FABRICACIÓN")
        self.assertContains(respuesta, "STOCK DISPONIBLE")
        self.assertContains(respuesta, "GUARDAR CAMBIOS")


class ModificacionMasivaProductosTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="bulk-productos",
            password="test12345",
        )
        self.client.force_login(usuario)
        self.tipo = TipoProducto.objects.create(nombre="Sensoriales bulk")
        self.otro_tipo = TipoProducto.objects.create(nombre="Otros bulk")
        self.a = Producto.objects.create(
            nombre="Estrella bulk",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=1,
            peso_gramos=Decimal("20"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            permite_elegir_color=False,
            personalizable=False,
            activo=True,
        )
        self.b = Producto.objects.create(
            nombre="Dona bulk",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=1,
            peso_gramos=Decimal("20"),
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            permite_elegir_color=False,
            personalizable=False,
            activo=True,
        )

    def test_pantalla_masiva_filtra_y_muestra_productos(self):
        response = self.client.get(
            reverse("productos:modificacion_masiva"),
            {"tipo": self.tipo.id},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Modificación masiva")
        self.assertContains(response, "Estrella bulk")
        self.assertContains(response, "Dona bulk")
        self.assertContains(response, "PREVISUALIZAR CAMBIOS")

    def test_previsualizacion_no_modifica_datos(self):
        response = self.client.post(
            reverse("productos:modificacion_masiva"),
            {
                "accion": "previsualizar",
                "producto_ids": [self.a.id, self.b.id],
                "permite_color": "1",
                "margen_modo": "AJUSTAR",
                "margen_valor": "5",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "PREVISUALIZACIÓN")
        self.assertContains(response, "No →")
        self.a.refresh_from_db()
        self.assertFalse(self.a.permite_elegir_color)
        self.assertEqual(self.a.margen_ganancia, Decimal("50"))

    def test_aplicar_modifica_seleccionados(self):
        response = self.client.post(
            reverse("productos:modificacion_masiva"),
            {
                "accion": "aplicar",
                "producto_ids": [self.a.id, self.b.id],
                "permite_color": "1",
                "personalizable": "1",
                "margen_modo": "AJUSTAR",
                "margen_valor": "5",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.assertTrue(self.a.permite_elegir_color)
        self.assertTrue(self.b.personalizable)
        self.assertEqual(self.a.margen_ganancia, Decimal("55"))
        self.assertEqual(self.b.margen_ganancia, Decimal("65"))

    def test_seleccionar_todos_respeta_filtro(self):
        fuera = Producto.objects.create(
            nombre="Fuera bulk",
            categoria="PRODUCTO",
            tipo=self.otro_tipo,
            horas=1,
            peso_gramos=Decimal("20"),
            margen_ganancia=Decimal("50"),
            activo=True,
        )
        self.client.post(
            reverse("productos:modificacion_masiva"),
            {
                "accion": "aplicar",
                "tipo": str(self.tipo.id),
                "seleccionar_todos_resultados": "1",
                "activo": "0",
            },
        )
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        fuera.refresh_from_db()
        self.assertFalse(self.a.activo)
        self.assertFalse(self.b.activo)
        self.assertTrue(fuera.activo)
