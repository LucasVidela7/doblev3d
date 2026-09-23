from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import resolve, reverse

from costos.models import ConfiguracionCostos
from productos.models import Producto, TipoProducto

from .economia import analizar_opciones_kit, precio_automatico_kit_libre
from .models import Kit, KitComponente


class AnalisisEconomicoKitTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="kits-model-test",
            password="test-pass",
        )
        self.client.force_login(usuario)
        ConfiguracionCostos.objects.create(
            nombre="Test",
            coste_plastico_kg=Decimal("1000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )

        self.tipo = TipoProducto.objects.create(
            nombre="Sensorial",
            activo=True,
        )

    def crear_producto(self, nombre, peso_gramos, solo_produccion=False):
        return Producto.objects.create(
            nombre=nombre,
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=0,
            peso_gramos=Decimal(str(peso_gramos)),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            personalizable=False,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=solo_produccion,
        )

    def test_kit_fijo_calcula_margen_exacto_y_alerta(self):
        producto_a = self.crear_producto("A", 100)
        producto_b = self.crear_producto("B", 200)

        kit = Kit.objects.create(
            nombre="Kit fijo",
            modalidad="FIJO",
            cantidad_productos=3,
            precio=Decimal("1000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=producto_a,
            cantidad=1,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=producto_b,
            cantidad=2,
        )

        analisis = kit.analisis_economico

        self.assertEqual(analisis["tipo_calculo"], "EXACTO")
        self.assertEqual(analisis["costo_estimado"], Decimal("500"))
        self.assertEqual(analisis["margen_estimado"], Decimal("50.0"))
        self.assertFalse(analisis["alerta"])

        kit.precio = Decimal("600")
        kit.save(update_fields=["precio"])
        analisis = kit.analisis_economico

        self.assertEqual(analisis["margen_estimado"], Decimal("16.7"))
        self.assertTrue(analisis["alerta"])
        self.assertEqual(
            analisis["precio_sugerido_minimo"],
            Decimal("1000"),
        )

    def test_kit_libre_usa_promedio_y_peor_caso_de_categoria(self):
        self.crear_producto("Liviano", 100)
        self.crear_producto("Pesado", 300)
        self.crear_producto(
            "Pieza interna",
            1000,
            solo_produccion=True,
        )

        kit = Kit.objects.create(
            nombre="Kit libre",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("1000"),
            activo=True,
        )

        analisis = kit.analisis_economico

        self.assertEqual(analisis["tipo_calculo"], "ESTIMADO")
        self.assertEqual(analisis["costo_estimado"], Decimal("400"))
        self.assertEqual(analisis["costo_peor_caso"], Decimal("600"))
        self.assertEqual(analisis["margen_estimado"], Decimal("60.0"))
        self.assertEqual(analisis["margen_peor_caso"], Decimal("40.0"))
        self.assertFalse(analisis["alerta"])

        kit.precio = Decimal("700")
        kit.save(update_fields=["precio"])
        analisis = kit.analisis_economico

        self.assertEqual(analisis["margen_peor_caso"], Decimal("14.3"))
        self.assertTrue(analisis["alerta"])
        self.assertEqual(
            analisis["precio_sugerido_minimo"],
            Decimal("1000"),
        )

    def test_kit_libre_protegido_separa_incluidos_y_premium(self):
        economico = self.crear_producto("Económico protegido", 100)
        premium = self.crear_producto("Premium protegido", 1000)

        kit = Kit.objects.create(
            nombre="Kit libre protegido",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("1000"),
            proteger_rentabilidad_libre=True,
            activo=True,
        )

        analisis = analizar_opciones_kit(
            kit,
            productos_categoria=[economico, premium],
        )
        por_id = {
            item["producto_id"]: item
            for item in analisis["opciones"]
        }

        self.assertTrue(analisis["disponible"])
        self.assertTrue(por_id[economico.id]["incluido"])
        self.assertEqual(por_id[economico.id]["extra"], Decimal("0"))
        self.assertFalse(por_id[premium.id]["incluido"])
        self.assertGreater(por_id[premium.id]["extra"], Decimal("0"))

        precio = precio_automatico_kit_libre(
            kit,
            [economico, premium],
        )
        self.assertEqual(
            precio,
            kit.precio + por_id[premium.id]["extra"],
        )

    def test_kit_libre_sin_proteccion_incluye_toda_la_categoria(self):
        economico = self.crear_producto("Económico libre", 100)
        caro = self.crear_producto("Caro libre", 1000)

        kit = Kit.objects.create(
            nombre="Kit libre sin protección",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("1000"),
            proteger_rentabilidad_libre=False,
            activo=True,
        )

        analisis = analizar_opciones_kit(
            kit,
            productos_categoria=[economico, caro],
        )

        self.assertEqual(analisis["cantidad_incluidos"], 2)
        self.assertEqual(analisis["cantidad_premium"], 0)
        self.assertGreaterEqual(
            analisis["cantidad_requieren_extra"],
            1,
        )
        self.assertEqual(
            precio_automatico_kit_libre(
                kit,
                [economico, caro],
            ),
            kit.precio,
        )

    def test_formulario_guarda_proteccion_de_kit_libre(self):
        self.crear_producto("Opción formulario A", 100)
        self.crear_producto("Opción formulario B", 120)

        respuesta = self.client.post(
            reverse("kits:nuevo"),
            data={
                "nombre": "Kit protegido formulario",
                "modalidad": "LIBRE_CATEGORIA",
                "tipo_producto": str(self.tipo.id),
                "cantidad_productos": "2",
                "max_repeticiones_producto": "1",
                "precio": "9000",
                "activo": "1",
                "proteger_rentabilidad_libre": "1",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        kit = Kit.objects.get(nombre="Kit protegido formulario")
        self.assertTrue(kit.proteger_rentabilidad_libre)
        self.assertEqual(kit.max_repeticiones_producto, 1)

    def test_formulario_permita_configurar_hasta_dos_repeticiones(self):
        self.crear_producto("Opción repetible formulario", 100)

        respuesta = self.client.post(
            reverse("kits:nuevo"),
            data={
                "nombre": "Kit repetible formulario",
                "modalidad": "LIBRE_CATEGORIA",
                "tipo_producto": str(self.tipo.id),
                "cantidad_productos": "2",
                "max_repeticiones_producto": "2",
                "precio": "9000",
                "activo": "1",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        kit = Kit.objects.get(nombre="Kit repetible formulario")
        self.assertEqual(kit.max_repeticiones_producto, 2)

    def test_formulario_rechaza_limite_que_no_permite_completar_kit(self):
        self.crear_producto("Única opción formulario", 100)

        respuesta = self.client.post(
            reverse("kits:nuevo"),
            data={
                "nombre": "Kit imposible formulario",
                "modalidad": "LIBRE_CATEGORIA",
                "tipo_producto": str(self.tipo.id),
                "cantidad_productos": "4",
                "max_repeticiones_producto": "2",
                "precio": "9000",
                "activo": "1",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "no hay suficientes productos activos",
        )
        self.assertFalse(
            Kit.objects.filter(nombre="Kit imposible formulario").exists()
        )

    def test_editar_kit_precarga_precio_valido_para_input_number(self):
        kit = Kit.objects.create(
            nombre="Kit precio",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("12500.50"),
            activo=True,
        )

        respuesta = self.client.get(
            reverse(
                "kits:editar",
                args=[kit.id],
            )
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            'value="12500.50"',
        )
        self.assertNotContains(
            respuesta,
            'value="12500,50"',
        )

    def test_nuevo_y_editar_muestran_recomendacion_de_precio(self):
        producto = self.crear_producto("Producto recomendación", 250)
        kit = Kit.objects.create(
            nombre="Kit recomendación",
            modalidad="FIJO",
            cantidad_productos=1,
            precio=Decimal("1000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=kit,
            producto=producto,
            cantidad=1,
        )

        nueva = self.client.get(
            reverse("kits:nuevo")
        )
        editar = self.client.get(
            reverse(
                "kits:editar",
                args=[kit.id],
            )
        )

        for respuesta in (nueva, editar):
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(
                respuesta,
                "RECOMENDACIÓN DE PRECIO",
            )
            self.assertContains(
                respuesta,
                'id="precio_recomendado"',
            )
            self.assertContains(
                respuesta,
                "kits/precios_fijos.js",
            )
            self.assertContains(
                respuesta,
                reverse("kits:recomendacion_fija"),
            )
            self.assertContains(
                respuesta,
                reverse("kits:recomendacion_libre"),
            )

    def test_ruta_de_kits_esta_expuesta(self):
        self.assertEqual(
            resolve(reverse("kits:lista")).view_name,
            "kits:lista",
        )
