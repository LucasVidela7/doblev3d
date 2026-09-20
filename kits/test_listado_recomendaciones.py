from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from costos.models import ConfiguracionCostos
from productos.models import Producto, TipoProducto

from .engine import KitEngine
from .models import Kit, KitComponente


class CentroKitsTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="kits-centro-test",
            password="test-pass",
        )
        self.client.force_login(usuario)
        ConfiguracionCostos.objects.create(
            nombre="Test Centro Kits",
            coste_plastico_kg=Decimal("1000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        self.tipo = TipoProducto.objects.create(
            nombre="Sensorial Centro",
            activo=True,
        )

    def producto(self, nombre, peso, margen=60):
        return Producto.objects.create(
            nombre=nombre,
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=0,
            peso_gramos=Decimal(str(peso)),
            margen_ganancia=Decimal(str(margen)),
            requiere_impresion=True,
            personalizable=False,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=False,
        )

    def test_centro_es_compacto_y_enlaza_al_detalle(self):
        producto = self.producto("Producto fijo", 500, 65)
        kit = Kit.objects.create(
            nombre="Kit centro fijo",
            modalidad="FIJO",
            cantidad_productos=2,
            precio=Decimal("5000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=producto,
            cantidad=2,
        )

        respuesta = self.client.get(reverse("kits:lista"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "Centro de kits")
        self.assertContains(respuesta, kit.nombre)
        self.assertContains(
            respuesta,
            reverse("kits:detalle", args=[kit.id]),
        )
        self.assertContains(respuesta, "CÁLCULO EXACTO")
        self.assertNotContains(respuesta, "REFERENCIAS DE PRECIO")

    def test_detalle_concentra_composicion_y_escenarios(self):
        producto = self.producto("Producto detalle", 500, 65)
        kit = Kit.objects.create(
            nombre="Kit detalle",
            modalidad="FIJO",
            cantidad_productos=2,
            precio=Decimal("5000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=producto,
            cantidad=2,
        )

        respuesta = self.client.get(
            reverse("kits:detalle", args=[kit.id])
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "ESTADO DEL KIT")
        self.assertContains(respuesta, "COMPOSICIÓN")
        self.assertContains(respuesta, "PRECIO Y RENTABILIDAD")
        self.assertContains(respuesta, "AGRESIVO")
        self.assertContains(respuesta, "RECOMENDADO")
        self.assertContains(respuesta, "CONSERVADOR")
        self.assertContains(respuesta, producto.nombre)

    def test_libre_protegido_expone_incluidos_y_premium(self):
        incluido = self.producto("Incluido protegido", 100, 50)
        premium = self.producto("Premium protegido", 2000, 70)
        kit = Kit.objects.create(
            nombre="Kit libre protegido",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("1000"),
            proteger_rentabilidad_libre=True,
            activo=True,
        )

        respuesta = self.client.get(
            reverse("kits:detalle", args=[kit.id])
        )

        self.assertEqual(respuesta.status_code, 200)
        kit_detalle = respuesta.context["kit"]
        analisis = kit_detalle.opciones_gestion
        por_id = {
            item["producto_id"]: item
            for item in analisis["opciones"]
        }
        self.assertTrue(por_id[incluido.id]["incluido"])
        self.assertFalse(por_id[premium.id]["incluido"])
        self.assertGreater(
            por_id[premium.id]["extra"],
            Decimal("0"),
        )
        self.assertContains(
            respuesta,
            "Protección de rentabilidad",
        )
        self.assertContains(respuesta, "INCLUIDO")

    def test_filtro_atencion_usa_estado_salud(self):
        producto = self.producto("Producto salud", 1000, 70)
        revisar = Kit.objects.create(
            nombre="Kit revisar",
            modalidad="FIJO",
            cantidad_productos=1,
            precio=Decimal("1"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=revisar,
            producto=producto,
            cantidad=1,
        )

        saludable = Kit.objects.create(
            nombre="Kit saludable",
            modalidad="FIJO",
            cantidad_productos=1,
            precio=Decimal("1"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=saludable,
            producto=producto,
            cantidad=1,
        )
        recomendado = KitEngine.recomendacion(
            saludable
        )["precio_recomendado"]
        saludable.precio = recomendado
        saludable.save(update_fields=["precio"])

        respuesta = self.client.get(
            reverse("kits:lista"),
            {"estado": "ATENCION"},
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, revisar.nombre)
        self.assertNotContains(respuesta, saludable.nombre)
