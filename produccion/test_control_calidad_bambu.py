import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from productos.models import Producto, TipoProducto

from .models import (
    ConfiguracionProduccion,
    Impresora,
    ImpresoraEstadoBambu,
    Produccion,
)


@override_settings(
    BAMBU_BRIDGE_TOKEN="test-bridge-token",
)
class ControlCalidadBambuTests(TestCase):
    def setUp(self):
        tipo = TipoProducto.objects.create(
            nombre="Control calidad",
        )
        self.producto = Producto.objects.create(
            nombre="Pieza control",
            categoria="PRODUCTO",
            tipo=tipo,
            horas=1,
            minutos=0,
            requiere_impresion=True,
            activo=True,
            stock=0,
        )
        self.impresora = Impresora.objects.create(
            nombre="A1 control",
        )
        self.estado_bambu = (
            ImpresoraEstadoBambu.objects.create(
                impresora=self.impresora,
                serial="SERIAL-CONTROL-1",
                nombre_bridge="A1-TEST",
                conectada=True,
                estado="RUNNING",
            )
        )
        self.produccion = Produccion.objects.create(
            producto=self.producto,
            cantidad=2,
            destino="STOCK",
            estado="IMPRIMIENDO",
            impresora=self.impresora,
            tiempo_impresion_minutos=60,
        )
        ConfiguracionProduccion.objects.create(
            pk=1,
        )

    def _sync(self, status, remaining=0, progress=100):
        payload = {
            "printers": [
                {
                    "name": "A1-TEST",
                    "connected": True,
                    "ip": "192.168.1.36",
                    "serial": "SERIAL-CONTROL-1",
                    "status": status,
                    "progress": progress,
                    "remaining_minutes": remaining,
                    "job_name": "pieza.3mf",
                    "nozzle_temp": 220,
                    "bed_temp": 65,
                    "wifi": "-55dBm",
                    "last_update": 1790344318.45,
                }
            ],
        }

        return self.client.post(
            reverse("bambu_bridge_sync"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=(
                "Bearer test-bridge-token"
            ),
        )

    @patch(
        "produccion.bambu_bridge_api.enviar_push_operativo"
    )
    def test_finalizada_pasa_a_control_sin_sumar_stock(
        self,
        push_mock,
    ):
        respuesta = self._sync("FINISH")

        self.assertEqual(
            respuesta.status_code,
            200,
        )

        self.produccion.refresh_from_db()
        self.producto.refresh_from_db()

        self.assertEqual(
            self.produccion.estado,
            "CONTROL",
        )
        self.assertEqual(
            self.producto.stock,
            0,
        )
        self.assertFalse(
            self.produccion.ingresado_stock,
        )
        self.assertEqual(
            self.produccion.evento_fin_bambu,
            "FINALIZADA",
        )
        push_mock.assert_called_once()

    @patch(
        "produccion.bambu_bridge_api.enviar_push_operativo"
    )
    def test_aviso_previo_se_emite_una_sola_vez(
        self,
        push_mock,
    ):
        config = ConfiguracionProduccion.objects.get(
            pk=1
        )
        config.minutos_aviso_finalizacion = 15
        config.save(
            update_fields=[
                "minutos_aviso_finalizacion"
            ]
        )

        self._sync(
            "RUNNING",
            remaining=14,
            progress=90,
        )
        self._sync(
            "RUNNING",
            remaining=13,
            progress=91,
        )

        self.assertEqual(
            push_mock.call_count,
            1,
        )

    def test_control_correcto_recien_ahi_suma_stock(self):
        self.produccion.estado = "CONTROL"
        self.produccion.save(
            update_fields=["estado"]
        )

        usuario = get_user_model().objects.create_user(
            username="control-test",
            password="test-pass",
        )
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse(
                "produccion:control",
                args=[self.produccion.id],
            ),
            {
                "resultado": "OK",
            },
        )

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        self.produccion.refresh_from_db()
        self.producto.refresh_from_db()

        self.assertEqual(
            self.produccion.estado,
            "LISTO",
        )
        self.assertEqual(
            self.producto.stock,
            2,
        )
        self.assertTrue(
            self.produccion.ingresado_stock,
        )

    def test_control_fallido_no_suma_stock(self):
        self.produccion.estado = "CONTROL"
        self.produccion.save(
            update_fields=["estado"]
        )

        usuario = get_user_model().objects.create_user(
            username="fallo-test",
            password="test-pass",
        )
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse(
                "produccion:control",
                args=[self.produccion.id],
            ),
            {
                "resultado": "FALLA",
            },
        )

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        self.produccion.refresh_from_db()
        self.producto.refresh_from_db()

        self.assertEqual(
            self.produccion.estado,
            "FALLIDA",
        )
        self.assertEqual(
            self.producto.stock,
            0,
        )
        self.assertFalse(
            self.produccion.ingresado_stock,
        )

    def test_reimprimir_fallida_crea_nueva_planificacion(self):
        self.produccion.estado = "FALLIDA"
        self.produccion.resultado_control = "FALLA"
        self.produccion.save(
            update_fields=[
                "estado",
                "resultado_control",
            ]
        )

        usuario = get_user_model().objects.create_user(
            username="reprint-test",
            password="test-pass",
        )
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse(
                "produccion:repetir",
                args=[self.produccion.id],
            )
        )

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        nueva = (
            Produccion.objects
            .exclude(id=self.produccion.id)
            .get()
        )

        self.assertEqual(
            nueva.estado,
            "PENDIENTE",
        )
        self.assertEqual(
            nueva.reimpresion_de_id,
            self.produccion.id,
        )
        self.assertEqual(
            nueva.cantidad,
            2,
        )
