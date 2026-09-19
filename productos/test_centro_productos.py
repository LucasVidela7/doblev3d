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
