from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from clientes.models import Cliente
from costos.models import ConfiguracionCostos
from kits.models import Kit, KitComponente
from productos.models import Producto, TipoProducto

from .kits_volumen import (
    CANTIDAD_MINIMA_KITS_VOLUMEN,
    calcular_precio_volumen_kits,
)
from .models import DetalleKitProducto, DetallePedido, Pedido


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STORAGES={
        "default": {
            "BACKEND": "django.core.files.storage.FileSystemStorage",
        },
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
        },
    },
)
class PrecioVolumenKitsTests(TestCase):
    def setUp(self):
        ConfiguracionCostos.objects.create(
            nombre="Costo mayorista kits",
            coste_plastico_kg=Decimal("20000"),
            coste_plastico_kg_cantidad=Decimal("14000"),
            tasa_fallos=Decimal("0"),
            coste_luz_hora=Decimal("0"),
            coste_amortizacion_hora=Decimal("0"),
            fecha_desde=date(2026, 1, 1),
            activa=True,
        )
        self.tipo = TipoProducto.objects.create(
            nombre="Piezas mayoristas",
            activo=True,
        )
        self.producto = Producto.objects.create(
            nombre="Pieza base",
            categoria="PRODUCTO",
            tipo=self.tipo,
            horas=0,
            minutos=1,
            peso_gramos=Decimal("100"),
            margen_ganancia=Decimal("60"),
            requiere_impresion=True,
            personalizable=False,
            stock=0,
            activo=True,
            tipo_fabricacion="SIMPLE",
            solo_produccion=False,
        )
        self.kit8 = Kit.objects.create(
            nombre="Kit x8",
            modalidad="FIJO",
            cantidad_productos=8,
            precio=Decimal("30000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=self.kit8,
            producto=self.producto,
            cantidad=8,
        )
        self.kit4 = Kit.objects.create(
            nombre="Kit x4",
            modalidad="FIJO",
            cantidad_productos=4,
            precio=Decimal("16000"),
            activo=True,
        )
        KitComponente.objects.create(
            kit=self.kit4,
            producto=self.producto,
            cantidad=4,
        )
        self.cliente = Cliente.objects.create(nombre="Cliente mayorista")
        self.usuario = get_user_model().objects.create_user(
            username="qa-kits",
            password="ClaveSegura-12345",
        )

    def _item(self, kit, cantidad):
        componentes = [
            {
                "producto": componente.producto,
                "cantidad": componente.cantidad * cantidad,
            }
            for componente in kit.componentes.all()
        ]
        return {
            "key": kit.nombre,
            "kit": kit,
            "cantidad": cantidad,
            "componentes": componentes,
        }

    def test_hasta_cuatro_kits_mantiene_precio_de_lista(self):
        resumen = calcular_precio_volumen_kits([
            self._item(self.kit8, 4),
        ])

        self.assertFalse(resumen["elegible"])
        self.assertEqual(CANTIDAD_MINIMA_KITS_VOLUMEN, 5)
        self.assertEqual(resumen["total_kits"], 4)
        self.assertEqual(resumen["total_piezas"], 32)
        self.assertEqual(
            resumen["precio_final_total"],
            resumen["precio_lista_total"],
        )
        self.assertEqual(resumen["ahorro"], Decimal("0"))

    def test_cinco_kits_usan_las_piezas_agrupadas_para_el_margen(self):
        resumen = calcular_precio_volumen_kits([
            self._item(self.kit8, 5),
        ])

        self.assertTrue(resumen["elegible"])
        self.assertEqual(resumen["total_kits"], 5)
        self.assertEqual(resumen["total_piezas"], 40)
        self.assertLess(
            resumen["margen_objetivo"],
            resumen["margen_tope_ponderado"],
        )
        self.assertGreater(resumen["ahorro"], Decimal("0"))
        self.assertLess(
            resumen["precio_final_total"],
            resumen["precio_lista_total"],
        )
        self.assertGreaterEqual(
            resumen["margen_real"],
            resumen["margen_minimo"],
        )

    def test_dos_kits_mas_tres_kits_distintos_califican_juntos(self):
        resumen = calcular_precio_volumen_kits([
            self._item(self.kit8, 2),
            self._item(self.kit4, 3),
        ])

        self.assertTrue(resumen["elegible"])
        self.assertEqual(resumen["total_kits"], 5)
        self.assertEqual(resumen["total_piezas"], 28)
        self.assertGreater(resumen["ahorro"], Decimal("0"))

    def test_mas_piezas_bajan_mas_el_margen_con_igual_cantidad_de_kits(self):
        poco_volumen = calcular_precio_volumen_kits([
            self._item(self.kit4, 5),
        ])
        mucho_volumen = calcular_precio_volumen_kits([
            self._item(self.kit8, 5),
        ])

        self.assertEqual(poco_volumen["total_kits"], mucho_volumen["total_kits"])
        self.assertEqual(poco_volumen["total_piezas"], 20)
        self.assertEqual(mucho_volumen["total_piezas"], 40)
        self.assertLess(
            mucho_volumen["margen_objetivo"],
            poco_volumen["margen_objetivo"],
        )

    def test_signal_aplica_el_precio_al_detalle_guardado(self):
        pedido = Pedido.objects.create(
            cliente=self.cliente,
            estado="PENDIENTE",
        )
        detalle = DetallePedido.objects.create(
            pedido=pedido,
            tipo_item="KIT",
            kit=self.kit8,
            cantidad=5,
            precio_unitario=self.kit8.precio,
            estado="PENDIENTE",
        )

        DetalleKitProducto.objects.create(
            detalle=detalle,
            producto=self.producto,
            cantidad=40,
        )

        detalle.refresh_from_db()
        self.assertLess(detalle.precio_unitario, self.kit8.precio)
        self.assertGreater(detalle.precio_unitario, Decimal("0"))

    def test_api_previsualiza_el_mismo_volumen(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.post(
            reverse("pedidos:precio_kits_volumen"),
            data={
                "items": [
                    {
                        "key": "1",
                        "kit_id": self.kit8.id,
                        "cantidad": 5,
                        "productos": [],
                    }
                ]
            },
            content_type="application/json",
        )

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertTrue(datos["ok"])
        self.assertTrue(datos["elegible"])
        self.assertEqual(datos["total_kits"], 5)
        self.assertEqual(datos["total_piezas"], 40)
        self.assertGreater(datos["ahorro"], 0)

    def test_api_kit_libre_usa_los_productos_realmente_seleccionados(self):
        self.client.force_login(self.usuario)
        kit_libre = Kit.objects.create(
            nombre="Kit libre x2",
            modalidad="LIBRE_CATEGORIA",
            tipo_producto=self.tipo,
            cantidad_productos=2,
            precio=Decimal("12000"),
            activo=True,
        )

        respuesta = self.client.post(
            reverse("pedidos:precio_kits_volumen"),
            data={
                "items": [
                    {
                        "key": "libre",
                        "kit_id": kit_libre.id,
                        "cantidad": 5,
                        "productos": [
                            self.producto.id,
                            self.producto.id,
                        ],
                    }
                ]
            },
            content_type="application/json",
        )

        self.assertEqual(respuesta.status_code, 200)
        datos = respuesta.json()
        self.assertTrue(datos["elegible"])
        self.assertEqual(datos["total_kits"], 5)
        self.assertEqual(datos["total_piezas"], 10)
        self.assertGreater(datos["ahorro"], 0)

    def test_nuevo_pedido_inyecta_resumen_visual(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse("pedidos:nuevo"))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, "dv-kit-volume-style")
        self.assertContains(respuesta, "dv-kit-volume-script")
        self.assertContains(respuesta, "Compra mayorista de kits")
