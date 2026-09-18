import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from costos.models import ConfiguracionCostos
from kits.models import Kit, KitComponente

from .image_models import ProductoImagen
from .models import Producto, TipoProducto


@override_settings(SECURE_SSL_REDIRECT=False)
class CatalogoPublicoTests(TestCase):
    def setUp(self):
        self.entorno = patch.dict(os.environ, {"APP_ENV": "qa"})
        self.entorno.start()
        self.addCleanup(self.entorno.stop)

        self.tipo = TipoProducto.objects.create(
            nombre="Sensoriales",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Piña sensorial",
            categoria="PRODUCTO",
            tipo=self.tipo,
            activo=True,
            solo_produccion=False,
        )
        self.oculto = Producto.objects.create(
            nombre="Pieza interna",
            categoria="PRODUCTO",
            tipo=self.tipo,
            activo=True,
            solo_produccion=True,
        )

        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="qa",
            file_id="qa-pina",
            url="https://example.com/qa-pina.jpg",
            thumbnail_url="https://example.com/qa-pina-thumb.jpg",
            orden=1,
        )
        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="production",
            file_id="prod-pina",
            url="https://example.com/prod-pina.jpg",
            thumbnail_url="https://example.com/prod-pina-thumb.jpg",
            orden=1,
        )

        self.kit = Kit.objects.create(
            nombre="Kit sensorial",
            modalidad="FIJO",
            cantidad_productos=1,
            precio=12000,
            activo=True,
        )
        KitComponente.objects.create(
            kit=self.kit,
            producto=self.producto,
            cantidad=1,
        )

    def test_catalogo_es_la_pagina_principal_publica(self):
        self.assertEqual(reverse("catalogo"), "/")

        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Piña sensorial")
        self.assertContains(response, "Kit sensorial")
        self.assertNotContains(response, "Pieza interna")

    def test_alias_catalogo_sigue_publico_para_links_compartidos(self):
        response = self.client.get(
            reverse("catalogo_legacy"),
            {"tipo": "producto", "categoria": "sensoriales"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Piña sensorial")

    def test_catalogo_mantiene_filtros_compartibles_en_la_url(self):
        response = self.client.get(
            reverse("catalogo"),
            {
                "tipo": "kit",
                "categoria": "sensoriales",
                "q": "Kit sensorial",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'params.get("tipo")')
        self.assertContains(response, 'params.get("categoria")')
        self.assertContains(response, 'params.get("q")')
        self.assertContains(response, "window.history.replaceState")
        self.assertContains(response, 'data-kind="kit"')
        self.assertContains(response, 'data-category="sensoriales"')

    def test_kit_fijo_hereda_categoria_si_todos_sus_componentes_coinciden(self):
        response = self.client.get(reverse("catalogo"))

        kit_catalogo = response.context["kits"][0]
        self.assertEqual(kit_catalogo.tipo_producto, self.tipo)
        self.assertContains(response, 'data-category="sensoriales"')

    def test_catalogo_comunica_opciones_premium_del_kit_libre(self):
        ConfiguracionCostos.objects.create(
            nombre="Costos catálogo premium",
            coste_plastico_kg=Decimal("1000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        incluido = Producto.objects.create(
            nombre="Opción incluida catálogo",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("100"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            activo=True,
            solo_produccion=False,
        )
        premium = Producto.objects.create(
            nombre="Opción premium catálogo",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("2000"),
            margen_ganancia=Decimal("70"),
            requiere_impresion=True,
            activo=True,
            solo_produccion=False,
        )
        kit = Kit.objects.create(
            nombre="Kit libre catálogo premium",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("1000"),
            proteger_rentabilidad_libre=True,
            activo=True,
        )

        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        kit_catalogo = next(
            item
            for item in response.context["kits"]
            if item.id == kit.id
        )
        analisis = kit_catalogo.opciones_libres_analisis
        self.assertGreaterEqual(analisis["cantidad_incluidos"], 1)
        self.assertGreaterEqual(analisis["cantidad_premium"], 1)
        self.assertContains(response, "opciones incluidas")
        self.assertContains(response, "con adicional")
        self.assertContains(
            response,
            "Algunas opciones tienen un adicional",
        )
        self.assertIn(
            incluido.id,
            {
                item["producto_id"]
                for item in analisis["incluidos"]
            },
        )
        self.assertIn(
            premium.id,
            {
                item["producto_id"]
                for item in analisis["premium"]
            },
        )

    def test_catalogo_muestra_libre_eleccion_en_kit_sin_proteccion(self):
        kit_libre = Kit.objects.create(
            nombre="Kit libre elección",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("9000"),
            proteger_rentabilidad_libre=False,
            activo=True,
        )

        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Kit libre elección")
        self.assertContains(response, "Libre elección")
        self.assertContains(
            response,
            "Elegí cualquiera de las opciones disponibles sin restricciones ni adicionales.",
        )

    def test_productos_con_imagen_aparecen_antes_que_los_sin_imagen(self):
        sin_imagen = Producto.objects.create(
            nombre="Abeja sin foto",
            categoria="PRODUCTO",
            tipo=self.tipo,
            activo=True,
            solo_produccion=False,
        )

        response = self.client.get(reverse("catalogo"))

        productos = response.context["productos"]
        self.assertEqual(productos[0], self.producto)
        self.assertEqual(productos[-1], sin_imagen)

    def test_gestion_interna_usa_prefijo_y_login_separado(self):
        self.assertEqual(reverse("dashboard:inicio"), "/gestion/")
        self.assertEqual(reverse("login"), "/gestion/login/")

        response = self.client.get(reverse("dashboard:inicio"))

        self.assertEqual(response.status_code, 302)
        self.assertIn("/gestion/login/", response.url)

    def test_catalogo_respeta_aislamiento_de_imagenes_qa(self):
        response = self.client.get(reverse("catalogo"))

        self.assertContains(
            response,
            "https://example.com/qa-pina.jpg",
        )
        self.assertNotContains(
            response,
            "https://example.com/prod-pina.jpg",
        )


    def test_catalogo_kit_tiene_enlace_a_detalle_publico(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse("catalogo_kit_detalle", args=[self.kit.id]),
        )
        self.assertContains(response, "VER DETALLE")

    def test_detalle_publico_kit_libre_muestra_incluidos_antes_de_adicionales(self):
        ConfiguracionCostos.objects.create(
            nombre="Costos detalle catálogo",
            coste_plastico_kg=Decimal("1000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        incluido = Producto.objects.create(
            nombre="A Opción incluida detalle",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("100"),
            margen_ganancia=Decimal("50"),
            requiere_impresion=True,
            activo=True,
            solo_produccion=False,
        )
        premium = Producto.objects.create(
            nombre="Z Opción adicional detalle",
            categoria="PRODUCTO",
            tipo=self.tipo,
            peso_gramos=Decimal("2000"),
            margen_ganancia=Decimal("70"),
            requiere_impresion=True,
            activo=True,
            solo_produccion=False,
        )
        kit = Kit.objects.create(
            nombre="Kit público detalle",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("1000"),
            proteger_rentabilidad_libre=True,
            activo=True,
        )

        response = self.client.get(
            reverse("catalogo_kit_detalle", args=[kit.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "OPCIONES INCLUIDAS")
        self.assertContains(response, "OPCIONES CON ADICIONAL")
        self.assertEqual(
            response.context["seleccionables"][0]["producto_id"],
            incluido.id,
        )
        self.assertEqual(
            response.context["adicionales"][0]["producto_id"],
            premium.id,
        )
        self.assertGreater(
            response.context["adicionales"][0]["extra"],
            Decimal("0"),
        )

        contenido = response.content.decode()
        self.assertLess(
            contenido.index(incluido.nombre),
            contenido.index(premium.nombre),
        )
        self.assertIn("ADICIONAL +$", contenido)

    def test_detalle_publico_no_expone_kit_inactivo(self):
        self.kit.activo = False
        self.kit.save(update_fields=["activo"])

        response = self.client.get(
            reverse("catalogo_kit_detalle", args=[self.kit.id])
        )

        self.assertEqual(response.status_code, 404)

    def test_detalle_publico_kit_fijo_muestra_composicion(self):
        response = self.client.get(
            reverse("catalogo_kit_detalle", args=[self.kit.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "COMPOSICIÓN DEL KIT")
        self.assertContains(response, self.producto.nombre)
        self.assertContains(response, "1 unidad")


    def test_catalogo_informa_como_comprar_y_retiro(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "¿Cómo comprar?")
        self.assertContains(response, "¿Cómo comprar?")
        self.assertContains(response, "Explorá productos y/o kits")
        self.assertContains(response, "Confirmamos por WhatsApp")
        self.assertContains(response, "Preparamos tu pedido")
        self.assertContains(response, "Correo")
        self.assertContains(response, "Motomensajería")
        self.assertContains(response, "Retiro coordinado en domicilio")
        self.assertContains(
            response,
            "La dirección exacta y el horario se informan al confirmar",
        )
        self.assertContains(
            response,
            "Cualquier costo de entrega",
        )

    def test_detalle_de_kit_reutiliza_modal_como_comprar(self):
        response = self.client.get(
            reverse("catalogo_kit_detalle", args=[self.kit.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "¿Cómo comprar?")
        self.assertContains(response, "Entregas y retiro")
