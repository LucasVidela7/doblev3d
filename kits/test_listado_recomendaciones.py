from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from costos.models import ConfiguracionCostos
from productos.models import Producto, TipoProducto

from .economia import recomendacion_kit
from .models import Kit, KitComponente


class ListadoRecomendacionesKitTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="kits-listado-test",
            password="test-pass",
        )
        self.client.force_login(usuario)
        ConfiguracionCostos.objects.create(
            nombre="Test listado kits",
            coste_plastico_kg=Decimal("1000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        self.tipo = TipoProducto.objects.create(
            nombre="Sensorial listado",
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

    def test_estado_precio_usa_agresivo_y_recomendado(self):
        producto = self.producto(
            "Producto margen",
            1000,
            margen=70,
        )
        kit = Kit.objects.create(
            nombre="Kit estados",
            modalidad="FIJO",
            cantidad_productos=1,
            precio=Decimal("1"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=producto,
            cantidad=1,
        )

        recomendacion = recomendacion_kit(kit)
        agresivo = recomendacion["precio_agresivo"]
        recomendado = recomendacion["precio_recomendado"]

        self.assertEqual(
            recomendacion["estado"],
            "REVISAR",
        )

        kit.precio = agresivo
        recomendacion = recomendacion_kit(kit)

        if agresivo < recomendado:
            self.assertEqual(
                recomendacion["estado"],
                "ADVERTENCIA",
            )

        kit.precio = recomendado
        recomendacion = recomendacion_kit(kit)
        self.assertEqual(
            recomendacion["estado"],
            "OK",
        )
        self.assertFalse(recomendacion["alerta"])

    def test_listado_muestra_tres_escenarios_y_no_formula_vieja(self):
        producto_a = self.producto("Producto A", 500, 65)
        self.producto("Producto B", 1000, 70)

        fijo = Kit.objects.create(
            nombre="Kit fijo listado",
            modalidad="FIJO",
            cantidad_productos=2,
            precio=Decimal("5000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=fijo,
            producto=producto_a,
            cantidad=2,
        )

        Kit.objects.create(
            nombre="Kit libre listado",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("5000"),
            activo=True,
        )

        respuesta = self.client.get(
            reverse("kits:lista")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'class="escenario agresivo"', count=2)
        self.assertContains(respuesta, 'class="escenario recomendado"', count=2)
        self.assertContains(respuesta, 'class="escenario conservador"', count=2)
        self.assertContains(
            respuesta,
            "Peor caso actual",
        )
        self.assertNotContains(
            respuesta,
            "Precio mínimo sugerido para sostener",
        )
        self.assertNotContains(
            respuesta,
            "Piso de alerta: 20%",
        )
