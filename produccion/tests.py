from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from productos.models import Producto, TipoProducto
from productos.image_models import ProductoImagen

from .models import Impresora, Produccion


ARGENTINA_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


class PlanificacionProduccionTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="produccion-test",
            password="test-pass",
        )
        self.client.force_login(usuario)
        tipo = TipoProducto.objects.create(
            nombre="Test producción",
        )
        self.producto = Producto.objects.create(
            nombre="Producto test",
            categoria="PRODUCTO",
            tipo=tipo,
            horas=2,
            minutos=30,
            requiere_impresion=True,
            activo=True,
        )
        self.impresora = Impresora.objects.create(
            nombre="A1 test",
        )

    @patch("produccion.views.timezone.now")
    def test_nueva_planificacion_de_dia_anterior_comienza_ahora(
        self,
        ahora_mock,
    ):
        ahora = datetime(
            2026,
            9,
            15,
            10,
            30,
            tzinfo=ARGENTINA_TZ,
        )
        ahora_mock.return_value = ahora

        respuesta = self.client.post(
            reverse("produccion:nueva"),
            {
                "producto": self.producto.id,
                "cantidad": "1",
                "destino": "STOCK",
                "inicio_impresion": "2026-09-14T18:00",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        produccion = Produccion.objects.get()
        self.assertEqual(produccion.estado, "PENDIENTE")
        self.assertEqual(produccion.inicio_impresion, ahora)
        self.assertEqual(
            produccion.fin_estimado,
            ahora + timedelta(minutes=150),
        )

    @patch("produccion.views.timezone.now")
    def test_lista_actualiza_planificacion_vencida_y_recalcula_fin(
        self,
        ahora_mock,
    ):
        ahora = datetime(
            2026,
            9,
            15,
            9,
            45,
            tzinfo=ARGENTINA_TZ,
        )
        ahora_mock.return_value = ahora
        produccion = Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            estado="PENDIENTE",
            inicio_impresion=ahora - timedelta(days=1),
            tiempo_impresion_minutos=150,
        )

        respuesta = self.client.get(
            reverse("produccion:lista")
        )

        self.assertEqual(respuesta.status_code, 200)
        produccion.refresh_from_db()
        self.assertEqual(produccion.inicio_impresion, ahora)
        self.assertEqual(
            produccion.fin_estimado,
            ahora + timedelta(minutes=150),
        )

    @patch("produccion.views.timezone.now")
    def test_reprogramar_lista_crea_pendiente_sin_impresora(
        self,
        ahora_mock,
    ):
        ahora = datetime(
            2026,
            9,
            15,
            11,
            0,
            tzinfo=ARGENTINA_TZ,
        )
        ahora_mock.return_value = ahora
        original = Produccion.objects.create(
            producto=self.producto,
            cantidad=3,
            impresora=self.impresora,
            destino="STOCK",
            estado="LISTO",
            inicio_impresion=ahora - timedelta(hours=8),
            tiempo_impresion_minutos=210,
        )

        respuesta = self.client.post(
            reverse(
                "produccion:repetir",
                args=[original.id],
            )
        )

        self.assertEqual(respuesta.status_code, 302)
        nueva = Produccion.objects.exclude(
            id=original.id
        ).get()
        self.assertEqual(nueva.estado, "PENDIENTE")
        self.assertIsNone(nueva.impresora)
        self.assertEqual(nueva.inicio_impresion, ahora)
        self.assertEqual(
            nueva.fin_estimado,
            ahora + timedelta(minutes=210),
        )

    def test_centro_produccion_prioriza_ahora_necesidad_y_cola(self):
        respuesta = self.client.get(
            reverse("produccion:lista")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "Centro de producción",
        )
        self.assertContains(
            respuesta,
            "Qué imprimir",
        )
        self.assertContains(
            respuesta,
            "MÁS OPCIONES · PRODUCIR PARA STOCK",
        )
        self.assertContains(
            respuesta,
            "Cola",
        )
        self.assertContains(
            respuesta,
            "Historial",
        )

    def test_filtro_predeterminado_muestra_imprimiendo_y_planificadas(self):
        Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            estado="PENDIENTE",
            tiempo_impresion_minutos=150,
        )
        Produccion.objects.create(
            producto=self.producto,
            cantidad=2,
            impresora=self.impresora,
            estado="IMPRIMIENDO",
            tiempo_impresion_minutos=150,
        )
        Produccion.objects.create(
            producto=self.producto,
            cantidad=3,
            estado="LISTO",
            tiempo_impresion_minutos=150,
        )

        respuesta = self.client.get(
            reverse("produccion:lista")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(
            respuesta.context["estado_filtro"],
            "ACTIVAS",
        )
        estados = {
            produccion.estado
            for produccion in respuesta.context["producciones"]
        }
        self.assertEqual(
            estados,
            {"PENDIENTE", "IMPRIMIENDO"},
        )
        self.assertEqual(
            len(respuesta.context["cola_pendiente"]),
            1,
        )
        self.assertContains(
            respuesta,
            "SIGUIENTE EN COLA",
        )

    @patch(
        "pedidos.impresiones_stock.obtener_impresiones_por_producto"
    )
    def test_accion_rapida_agrega_trabajo_a_cola(
        self,
        necesidades_mock,
    ):
        necesidades_mock.return_value = [
            {
                "producto": self.producto,
                "falta_normal_planificar": 3,
            }
        ]

        respuesta = self.client.post(
            reverse("produccion:accion_rapida"),
            {
                "producto": self.producto.id,
                "cantidad": "2",
                "accion": "PLANIFICAR",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        produccion = Produccion.objects.get()
        self.assertEqual(produccion.estado, "PENDIENTE")
        self.assertIsNone(produccion.impresora)
        self.assertEqual(produccion.cantidad, 2)
        self.assertEqual(
            produccion.tiempo_impresion_minutos,
            300,
        )

    @patch(
        "pedidos.impresiones_stock.obtener_impresiones_por_producto"
    )
    def test_accion_rapida_permite_excedente_para_stock(
        self,
        necesidades_mock,
    ):
        necesidades_mock.return_value = [
            {
                "producto": self.producto,
                "falta_normal_planificar": 3,
            }
        ]

        respuesta = self.client.post(
            reverse("produccion:accion_rapida"),
            {
                "producto": self.producto.id,
                "cantidad": "80",
                "accion": "PLANIFICAR",
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        produccion = Produccion.objects.get()
        self.assertEqual(produccion.destino, "STOCK")
        self.assertEqual(produccion.cantidad, 80)
        self.assertEqual(produccion.estado, "PENDIENTE")
        self.assertEqual(
            produccion.tiempo_impresion_minutos,
            12000,
        )

    @patch(
        "pedidos.impresiones_stock.obtener_impresiones_por_producto"
    )
    def test_accion_rapida_puede_iniciar_en_impresora_libre(
        self,
        necesidades_mock,
    ):
        necesidades_mock.return_value = [
            {
                "producto": self.producto,
                "falta_normal_planificar": 2,
            }
        ]

        respuesta = self.client.post(
            reverse("produccion:accion_rapida"),
            {
                "producto": self.producto.id,
                "cantidad": "1",
                "accion": "INICIAR",
                "impresora": self.impresora.id,
            },
        )

        self.assertEqual(respuesta.status_code, 302)
        produccion = Produccion.objects.get()
        self.assertEqual(produccion.estado, "IMPRIMIENDO")
        self.assertEqual(produccion.impresora, self.impresora)
        self.assertEqual(
            produccion.tiempo_impresion_minutos,
            150,
        )

    @patch(
        "produccion.views._archivo_fisico_disponible",
        return_value=True,
    )
    def test_iniciar_bambu_encola_print_y_espera_telemetria(
        self,
        disponible_mock,
    ):
        archivo = ArchivoImpresion.objects.create(
            producto=self.producto,
            nombre="Pepino x1",
            cantidad_unidades=1,
            archivo="productos/P0001/test.gcode.3mf",
            nombre_original="PEPINO_plate_1.gcode.3mf",
            tamano_bytes=12345,
            sha256="a" * 64,
            placas=[1],
            activo=True,
            predeterminado=True,
        )

        estado_bambu = (
            ImpresoraEstadoBambu.objects.create(
                impresora=self.impresora,
                serial="TEST-A1-PRINT",
                nombre_bridge="A1-test",
                conectada=True,
                estado="FINISH",
                carrete_externo={
                    "tray_type": "PLA",
                    "tray_color": "FFFFFFFF",
                },
            )
        )

        produccion = Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            estado="PENDIENTE",
            archivo_impresion=archivo,
            tiempo_impresion_minutos=150,
        )

        respuesta = self.client.post(
            reverse(
                "produccion:iniciar",
                args=[produccion.id],
            ),
            {
                "impresora": self.impresora.id,
                "filamento": "EXTERNO",
            },
        )

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        produccion.refresh_from_db()

        self.assertEqual(
            produccion.estado,
            "PENDIENTE",
        )
        self.assertEqual(
            produccion.impresora,
            self.impresora,
        )
        self.assertIsNone(
            produccion.inicio_impresion
        )
        self.assertEqual(
            produccion.bambu_fuente_filamento,
            "EXTERNO",
        )

        comando = ComandoBambu.objects.get(
            produccion=produccion,
            tipo="PRINT",
        )

        self.assertEqual(
            comando.estado,
            "PENDIENTE",
        )
        self.assertEqual(
            comando.impresora_estado,
            estado_bambu,
        )
        self.assertEqual(
            comando.trabajo_bambu_esperado,
            (
                f"DV_{produccion.codigo}_"
                f"{archivo.sha256[:8]}.gcode.3mf"
            ),
        )

    @patch("produccion.views.timezone.now")
    def test_planificacion_vencida_muestra_fin_si_inicia_ahora(
        self,
        ahora_mock,
    ):
        ahora = datetime(
            2026,
            9,
            15,
            10,
            41,
            tzinfo=ARGENTINA_TZ,
        )
        ahora_mock.return_value = ahora
        Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            estado="PENDIENTE",
            inicio_impresion=ahora - timedelta(hours=2),
            tiempo_impresion_minutos=150,
        )

        respuesta = self.client.get(
            reverse("produccion:lista")
        )

        self.assertContains(
            respuesta,
            "SI EMPIEZA AHORA",
        )
        self.assertContains(
            respuesta,
            "Termina aprox. 13:11",
        )

    def test_centro_produccion_muestra_miniatura_del_producto(self):
        ProductoImagen.objects.create(
            producto=self.producto,
            file_id="prod-thumb-centro",
            url="https://example.com/producto.jpg",
            thumbnail_url="https://example.com/producto-thumb.jpg",
            orden=1,
        )
        Produccion.objects.create(
            producto=self.producto,
            cantidad=2,
            impresora=self.impresora,
            estado="IMPRIMIENDO",
            tiempo_impresion_minutos=150,
        )

        respuesta = self.client.get(
            reverse("produccion:lista")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "https://example.com/producto-thumb.jpg",
        )
        self.assertContains(
            respuesta,
            'class="product-thumb"',
        )

    def test_historial_produccion_muestra_miniatura(self):
        ProductoImagen.objects.create(
            producto=self.producto,
            file_id="prod-thumb-historial",
            url="https://example.com/historial.jpg",
            thumbnail_url="https://example.com/historial-thumb.jpg",
            orden=1,
        )
        Produccion.objects.create(
            producto=self.producto,
            cantidad=3,
            impresora=self.impresora,
            estado="LISTO",
            tiempo_impresion_minutos=150,
        )

        respuesta = self.client.get(
            reverse("produccion:lista")
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "https://example.com/historial-thumb.jpg",
        )
        self.assertContains(
            respuesta,
            "VER ÚLTIMAS 1 FINALIZADAS",
        )



    @patch("produccion.views.timezone.now")
    def test_planificar_desde_detalle_producto_crea_trabajo_y_vuelve_al_producto(
        self,
        ahora_mock,
    ):
        ahora = datetime(
            2026,
            9,
            24,
            16,
            0,
            tzinfo=ARGENTINA_TZ,
        )
        ahora_mock.return_value = ahora

        respuesta = self.client.post(
            reverse(
                "produccion:planificar_desde_producto",
                args=[self.producto.id],
            ),
            {
                "cantidad": "3",
            },
        )

        self.assertRedirects(
            respuesta,
            reverse(
                "productos:detalle",
                args=[self.producto.id],
            ),
        )
        produccion = Produccion.objects.get()
        self.assertEqual(produccion.producto, self.producto)
        self.assertEqual(produccion.cantidad, 3)
        self.assertEqual(produccion.destino, "STOCK")
        self.assertEqual(produccion.estado, "PENDIENTE")
        self.assertIsNone(produccion.impresora)
        self.assertEqual(produccion.inicio_impresion, ahora)
        self.assertEqual(
            produccion.tiempo_impresion_minutos,
            450,
        )

    def test_detalle_producto_incluye_planificador_modal(self):
        respuesta = self.client.get(
            reverse(
                "productos:detalle",
                args=[self.producto.id],
            )
        )

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(
            respuesta,
            "PLANIFICAR IMPRESIÓN",
        )
        self.assertContains(
            respuesta,
            "AGREGAR A LA COLA",
        )
        self.assertContains(
            respuesta,
            "EDITAR PRODUCTO",
        )
