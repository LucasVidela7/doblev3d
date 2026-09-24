import os
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse

from costos.models import ConfiguracionCostos
from kits.models import Kit, KitComponente

from .image_models import ProductoImagen
from .models import ConfiguracionCatalogo, Producto, TipoProducto


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

    def test_catalogo_incluye_loader_de_navegacion(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-dv-site-loader")
        self.assertContains(response, "Preparando la tienda")

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

    def test_configuracion_puede_ocultar_productos_sin_foto(self):
        sin_imagen = Producto.objects.create(
            nombre="Producto sin foto ocultable",
            categoria="PRODUCTO",
            tipo=self.tipo,
            activo=True,
            solo_produccion=False,
        )
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.mostrar_productos_sin_foto = False
        config.save(update_fields=["mostrar_productos_sin_foto"])

        response = self.client.get(reverse("catalogo_productos"))

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.producto, response.context["productos"])
        self.assertNotIn(sin_imagen, response.context["productos"])
        self.assertIn(self.kit, response.context["kits"])

        detalle = self.client.get(
            reverse("catalogo_producto_detalle", args=[sin_imagen.id])
        )
        self.assertEqual(detalle.status_code, 404)

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
        response = self.client.get(reverse("catalogo_kits"))

        self.assertEqual(response.status_code, 200)
        detalle_url = reverse("catalogo_kit_detalle", args=[self.kit.id])
        self.assertContains(response, detalle_url)
        self.assertContains(response, "VER DETALLE")
        self.assertContains(response, 'class="catalog-media-link"')
        self.assertContains(
            response,
            'href="' + detalle_url + '"',
        )

    def test_detalle_kit_no_muestra_salto_de_linea_literal(self):
        response = self.client.get(
            reverse("catalogo_kit_detalle", args=[self.kit.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(
            response,
            '<body class="dv-kit-configurable-page">\\n',
        )

    def test_agregar_kit_confirma_sin_abrir_carrito_automaticamente(self):
        script_path = os.path.join(
            os.path.dirname(__file__),
            "static",
            "productos",
            "catalog_cart.js",
        )
        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()

        kit_handler = script.split(
            "addButton?.addEventListener('click', () => {",
            1,
        )[1].split("updateKit();", 1)[0]
        self.assertNotIn("open();", kit_handler)
        self.assertIn("cartAction: true", script)

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
        self.assertContains(response, "Elegí los productos de tu kit")
        self.assertContains(response, "Usá")
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
        self.assertContains(response, "data-dv-kit-progress-fill")
        self.assertContains(response, "data-dv-kit-add")
        self.assertContains(response, "data-dv-kit-options-grid")
        self.assertContains(response, "dv-kit-cart-panel--simple")
        self.assertNotContains(response, "TOTAL DE LISTA")
        self.assertNotContains(response, "CANTIDAD DE KITS")

    def test_detalle_publico_no_expone_kit_inactivo(self):
        self.kit.activo = False
        self.kit.save(update_fields=["activo"])

        response = self.client.get(
            reverse("catalogo_kit_detalle", args=[self.kit.id])
        )

        self.assertEqual(response.status_code, 404)


    def test_kit_fijo_con_componente_inactivo_no_se_publica(self):
        self.producto.activo = False
        self.producto.save(update_fields=["activo"])

        listado = self.client.get(reverse("catalogo_kits"))
        self.assertEqual(listado.status_code, 200)
        self.assertNotContains(listado, self.kit.nombre)

        detalle = self.client.get(
            reverse("catalogo_kit_detalle", args=[self.kit.id])
        )
        self.assertEqual(detalle.status_code, 404)

    def test_banner_inicio_incluye_circulos_de_marca(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, ".hero-card::before")
        self.assertContains(response, ".hero-card::after")

    def test_detalle_publico_kit_fijo_muestra_composicion(self):
        response = self.client.get(
            reverse("catalogo_kit_detalle", args=[self.kit.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "COMPOSICIÓN DEL KIT")
        self.assertContains(response, self.producto.nombre)
        self.assertContains(response, "1 unidad")


    def test_catalogo_como_comprar_muestra_solo_los_cuatro_pasos(self):
        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "¿Cómo comprar?")
        self.assertContains(response, "Explorá productos y/o kits")
        self.assertContains(response, "Armá tu carrito")
        self.assertContains(response, "Solicitá el presupuesto")
        self.assertContains(response, "Confirmamos y preparamos")
        self.assertNotContains(response, "Entregas y retiro")
        self.assertNotContains(response, "Motomensajería")
        self.assertNotContains(response, "Cualquier costo de entrega")
        self.assertContains(response, "ENTENDIDO")

    def test_detalle_de_kit_reutiliza_modal_como_comprar(self):
        response = self.client.get(
            reverse("catalogo_kit_detalle", args=[self.kit.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "¿Cómo comprar?")
        self.assertContains(response, "Confirmamos y preparamos")
        self.assertNotContains(response, "Entregas y retiro")

    def test_catalogo_informa_plazo_de_entrega_configurado(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.mensaje_plazo_entrega = (
            "Plazo de prueba: 3 a 10 días hábiles desde la confirmación."
        )
        config.save(update_fields=["mensaje_plazo_entrega"])

        portada = self.client.get(reverse("catalogo"))
        productos = self.client.get(reverse("catalogo_productos"))
        kits = self.client.get(reverse("catalogo_kits"))
        detalle = self.client.get(
            reverse("catalogo_kit_detalle", args=[self.kit.id])
        )

        for respuesta in [portada, productos, kits, detalle]:
            self.assertEqual(respuesta.status_code, 200)
            self.assertContains(
                respuesta,
                "3 a 10 días hábiles desde la confirmación",
            )

        self.assertContains(productos, "delivery-banner")
        self.assertContains(kits, "delivery-banner")
        self.assertNotContains(productos, "delivery-card-note")
        self.assertNotContains(kits, "delivery-card-note")
        self.assertContains(detalle, "Plazo de entrega")

    def test_producto_tiene_detalle_publico_y_ayuda_de_compra(self):
        response = self.client.get(
            reverse(
                "catalogo_producto_detalle",
                args=[self.producto.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.producto.nombre)
        self.assertContains(response, self.tipo.nombre)
        self.assertContains(
            response,
            "https://example.com/qa-pina.jpg",
        )
        self.assertNotContains(
            response,
            "https://example.com/prod-pina.jpg",
        )
        self.assertContains(response, "¿No encontrás lo que buscás?")
        self.assertContains(
            response,
            "?motivo=producto_especial",
        )
        self.assertContains(response, "data-dv-cart-root")
        self.assertContains(response, "data-dv-how-buy-open")

    def test_producto_con_color_muestra_surtido_y_eleccion(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.colores_disponibles = "Rojo\nAzul\n#12AB34"
        config.save(update_fields=["colores_disponibles"])
        self.producto.permite_elegir_color = True
        self.producto.save(update_fields=["permite_elegir_color"])

        response = self.client.get(
            reverse(
                "catalogo_producto_detalle",
                args=[self.producto.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "¿Cómo querés el color?")
        self.assertContains(response, "Colores surtidos")
        self.assertContains(response, "Elegir un color")
        self.assertContains(response, "preparación más rápida")
        self.assertContains(response, "mayor tiempo de preparación")
        self.assertContains(response, 'data-dv-color-swatch')
        self.assertContains(response, 'data-color-value="Rojo"')
        self.assertContains(response, 'data-color-hex="#EF1111"')
        self.assertContains(response, 'data-color-value="Azul"')
        self.assertContains(response, 'data-color-hex="#0B66C3"')
        self.assertContains(response, 'data-color-value="#12AB34"')
        self.assertContains(response, 'data-color-hex="#12AB34"')
        self.assertContains(response, 'data-dv-color-current')
        self.assertNotContains(response, '<select id="dv-product-color-')

        listado = self.client.get(reverse("catalogo_productos"))
        self.assertContains(listado, "Color a elección")

    def test_producto_muestra_nombre_de_color_personalizado_y_su_hex(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.colores_disponibles = "Verde manzana|#12AB34"
        config.save(update_fields=["colores_disponibles"])
        self.producto.permite_elegir_color = True
        self.producto.save(update_fields=["permite_elegir_color"])

        response = self.client.get(
            reverse(
                "catalogo_producto_detalle",
                args=[self.producto.id],
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'data-color-value="Verde manzana"',
        )
        self.assertContains(
            response,
            'data-color-hex="#12AB34"',
        )
        self.assertContains(
            response,
            'aria-label="Verde manzana"',
        )

    def test_kit_libre_muestra_adicional_por_mismo_color(self):
        config, _ = ConfiguracionCatalogo.objects.get_or_create(pk=1)
        config.colores_disponibles = "Rojo\nAzul"
        config.adicional_color_kit_base = Decimal("1000")
        config.adicional_color_kit_por_producto = Decimal("500")
        config.save(
            update_fields=[
                "colores_disponibles",
                "adicional_color_kit_base",
                "adicional_color_kit_por_producto",
            ]
        )
        kit = Kit.objects.create(
            nombre="Kit libre color detalle",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("9000"),
            permite_elegir_color=True,
            activo=True,
        )

        response = self.client.get(
            reverse("catalogo_kit_detalle", args=[kit.id])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Todo del mismo color")
        self.assertContains(response, "2.000")
        self.assertContains(response, "Producción especial")
        self.assertContains(response, 'data-dv-color-swatch')
        self.assertContains(response, 'data-color-value="Rojo"')
        self.assertContains(response, 'data-color-value="Azul"')
        self.assertNotContains(response, '<select id="dv-kit-color-')

        listado = self.client.get(reverse("catalogo_kits"))
        self.assertContains(
            listado,
            "Permite elegir un color para todo el kit",
        )

    def test_producto_inactivo_no_tiene_detalle_publico(self):
        self.producto.activo = False
        self.producto.save(update_fields=["activo"])

        response = self.client.get(
            reverse(
                "catalogo_producto_detalle",
                args=[self.producto.id],
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_listado_producto_enlaza_a_su_detalle(self):
        response = self.client.get(
            reverse("catalogo_productos")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            reverse(
                "catalogo_producto_detalle",
                args=[self.producto.id],
            ),
        )
        self.assertContains(response, "Precio unitario")

    def test_inicio_mantiene_dos_columnas_y_muestra_dos_fotos_del_producto(self):
        ProductoImagen.objects.create(
            producto=self.producto,
            ambiente="qa",
            file_id="qa-pina-2",
            url="https://example.com/qa-pina-2.jpg",
            thumbnail_url="https://example.com/qa-pina-2-thumb.jpg",
            orden=2,
        )

        response = self.client.get(reverse("catalogo"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            "grid-template-columns:repeat(2,minmax(0,1fr))",
        )
        self.assertContains(
            response,
            "https://example.com/qa-pina.jpg",
        )
        self.assertContains(
            response,
            "https://example.com/qa-pina-2.jpg",
        )
        self.assertContains(response, "preview-media dual")

    def test_agregar_producto_confirma_sin_abrir_carrito_automaticamente(self):
        response = self.client.get(reverse("catalogo_productos"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-dv-cart-toast-message")
        self.assertContains(response, "data-dv-cart-toast-open")
        self.assertContains(response, "VER CARRITO")

        script_path = os.path.join(
            os.path.dirname(__file__),
            "static",
            "productos",
            "catalog_cart.js",
        )
        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()

        self.assertNotIn("window.setTimeout(open, 90)", script)
        self.assertIn("cartAction: true", script)
        self.assertIn("pulseCartOpeners()", script)

    def test_carrito_informa_eliminacion_al_restar_de_uno_a_cero(self):
        script_path = os.path.join(
            os.path.dirname(__file__),
            "static",
            "productos",
            "catalog_cart.js",
        )
        style_path = os.path.join(
            os.path.dirname(__file__),
            "static",
            "productos",
            "catalog_cart.css",
        )

        with open(script_path, encoding="utf-8") as script_file:
            script = script_file.read()
        with open(style_path, encoding="utf-8") as style_file:
            styles = style_file.read()

        self.assertIn("removedByDecrement", script)
        self.assertIn("eliminado del carrito", script)
        self.assertIn("grid-template-columns:repeat(3,minmax(0,1fr))", styles)
        self.assertIn("background:#17233a", styles)
        self.assertIn("background:#f0393b", styles)

    def test_tarjeta_producto_muestra_ver_y_agregar_legibles(self):
        response = self.client.get(
            reverse("catalogo_productos")
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'class="product-actions"',
        )
        self.assertContains(
            response,
            ">VER</a>",
            html=True,
        )
        self.assertContains(
            response,
            ">AGREGAR</button>",
            html=True,
        )
        self.assertContains(
            response,
            "grid-template-columns:minmax(58px,.7fr) minmax(0,1.3fr)",
        )


    @override_settings(DEBUG=False)
    def test_404_publica_mantiene_al_cliente_en_la_tienda(self):
        response = self.client.get("/pagina-que-no-existe/")

        self.assertEqual(response.status_code, 404)
        self.assertContains(
            response,
            "Volvamos a la tienda",
            status_code=404,
        )
        self.assertContains(
            response,
            reverse("catalogo"),
            status_code=404,
        )
        self.assertContains(
            response,
            reverse("catalogo_productos"),
            status_code=404,
        )
        self.assertContains(
            response,
            reverse("catalogo_kits"),
            status_code=404,
        )
        self.assertNotContains(
            response,
            "/gestion/login/",
            status_code=404,
        )

    @override_settings(DEBUG=False)
    def test_404_de_gestion_sigue_protegida_por_login(self):
        response = self.client.get("/gestion/ruta-inexistente/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/gestion/login/", response.url)

