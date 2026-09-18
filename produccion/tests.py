from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from productos.models import Producto, TipoProducto

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

    def test_formulario_precarga_fecha_y_hora_actual(self):
        respuesta = self.client.get(
            reverse("produccion:lista")
        )

        self.assertContains(
            respuesta,
            "inicio.value = fechaHoraLocalActual();",
        )
        self.assertContains(
            respuesta,
            "REPROGRAMAR IMPRESIÓN",
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
            "Si inicia ahora · termina 13:11",
        )
        self.assertContains(
            respuesta,
            "Programada originalmente · 15/09 08:41",
        )
