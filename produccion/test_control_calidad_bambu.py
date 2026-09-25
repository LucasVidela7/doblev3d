import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from productos.models import Producto, TipoProducto

from .models import (
    ComandoBambu,
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


    def test_cancelar_desde_gestion_encola_stop_sin_cancelar_stock(self):
        usuario = get_user_model().objects.create_user(
            username="cancel-test",
            password="test-pass",
        )
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse(
                "produccion:cancelar_bambu",
                args=[self.produccion.id],
            )
        )

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        self.produccion.refresh_from_db()

        self.assertEqual(
            self.produccion.estado,
            "IMPRIMIENDO",
        )
        self.assertEqual(
            self.produccion.evento_fin_bambu,
            "CANCELACION_SOLICITADA",
        )

        comando = ComandoBambu.objects.get(
            produccion=self.produccion
        )
        self.assertEqual(
            comando.tipo,
            "STOP",
        )
        self.assertEqual(
            comando.estado,
            "PENDIENTE",
        )

    def test_sync_entrega_stop_y_confirma_resultado(self):
        comando = ComandoBambu.objects.create(
            tipo="STOP",
            impresora_estado=self.estado_bambu,
            produccion=self.produccion,
        )
        self.produccion.evento_fin_bambu = (
            "CANCELACION_SOLICITADA"
        )
        self.produccion.save(
            update_fields=["evento_fin_bambu"]
        )

        respuesta = self._sync(
            "RUNNING",
            remaining=30,
            progress=50,
        )
        data = respuesta.json()

        self.assertEqual(
            len(data["commands"]),
            1,
        )
        self.assertEqual(
            data["commands"][0]["type"],
            "STOP",
        )
        self.assertEqual(
            data["commands"][0]["command_id"],
            str(comando.id_comando),
        )

        payload = {
            "printers": [
                {
                    "name": "A1-TEST",
                    "connected": True,
                    "ip": "192.168.1.36",
                    "serial": "SERIAL-CONTROL-1",
                    "status": "RUNNING",
                    "progress": 50,
                    "remaining_minutes": 30,
                    "job_name": "pieza.3mf",
                    "nozzle_temp": 220,
                    "bed_temp": 65,
                    "wifi": "-55dBm",
                    "last_update": 1790344318.45,
                }
            ],
            "command_results": [
                {
                    "command_id": str(
                        comando.id_comando
                    ),
                    "ok": True,
                }
            ],
        }

        respuesta = self.client.post(
            reverse("bambu_bridge_sync"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=(
                "Bearer test-bridge-token"
            ),
        )

        self.assertEqual(
            respuesta.status_code,
            200,
        )

        comando.refresh_from_db()
        self.produccion.refresh_from_db()

        self.assertEqual(
            comando.estado,
            "EJECUTADO",
        )
        self.assertEqual(
            self.produccion.evento_fin_bambu,
            "CANCELACION_ENVIADA",
        )

    @patch(
        "produccion.bambu_bridge_api.enviar_push_operativo"
    )
    def test_impresora_detenida_confirma_cancelacion(
        self,
        push_mock,
    ):
        self.produccion.evento_fin_bambu = (
            "CANCELACION_ENVIADA"
        )
        self.produccion.save(
            update_fields=["evento_fin_bambu"]
        )

        self._sync(
            "FAILED",
            remaining=0,
            progress=50,
        )

        self.produccion.refresh_from_db()
        self.producto.refresh_from_db()

        self.assertEqual(
            self.produccion.estado,
            "CANCELADO",
        )
        self.assertEqual(
            self.producto.stock,
            0,
        )
        self.assertFalse(
            self.produccion.ingresado_stock,
        )
        push_mock.assert_called_once()

    def test_no_permite_finalizar_si_a1_sigue_imprimiendo(self):
        usuario = get_user_model().objects.create_user(
            username="finalizar-activo-test",
            password="test-pass",
        )
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse(
                "produccion:cambiar_estado",
                args=[self.produccion.id],
            ),
            {
                "estado": "CONTROL",
            },
        )

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        self.produccion.refresh_from_db()

        self.assertEqual(
            self.produccion.estado,
            "IMPRIMIENDO",
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

    def test_reimprimir_fallida_con_slot_ams_guarda_filamento(self):
        self.estado_bambu.ams = {
            "ams": [
                {
                    "id": 0,
                    "tray": [
                        {
                            "id": 3,
                            "tray_type": "PLA",
                            "tray_color": "0085D5FF",
                        }
                    ],
                }
            ],
            "tray_now": "3",
        }
        self.estado_bambu.save(
            update_fields=["ams"]
        )

        self.produccion.estado = "FALLIDA"
        self.produccion.resultado_control = "FALLA"
        self.produccion.save(
            update_fields=[
                "estado",
                "resultado_control",
            ]
        )

        usuario = get_user_model().objects.create_user(
            username="ams-reprint-test",
            password="test-pass",
        )
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse(
                "produccion:repetir",
                args=[self.produccion.id],
            ),
            {
                "impresora": str(self.impresora.id),
                "filamento": "AMS:0:3",
            },
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
            nueva.impresora_id,
            self.impresora.id,
        )
        self.assertEqual(
            nueva.bambu_fuente_filamento,
            "AMS",
        )
        self.assertEqual(
            nueva.bambu_ams_id,
            0,
        )
        self.assertEqual(
            nueva.bambu_tray_id,
            3,
        )
        self.assertEqual(
            nueva.bambu_material,
            "PLA",
        )
        self.assertEqual(
            nueva.bambu_color_hex,
            "#0085D5",
        )
        self.assertFalse(
            nueva.bambu_requiere_cambio_manual,
        )

    def test_reimprimir_fallida_con_cambio_manual(self):
        self.produccion.estado = "FALLIDA"
        self.produccion.resultado_control = "FALLA"
        self.produccion.save(
            update_fields=[
                "estado",
                "resultado_control",
            ]
        )

        usuario = get_user_model().objects.create_user(
            username="manual-reprint-test",
            password="test-pass",
        )
        self.client.force_login(usuario)

        respuesta = self.client.post(
            reverse(
                "produccion:repetir",
                args=[self.produccion.id],
            ),
            {
                "impresora": str(self.impresora.id),
                "filamento": "MANUAL",
                "material_manual": "PLA",
                "color_manual": "Azul",
            },
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
            nueva.bambu_fuente_filamento,
            "MANUAL",
        )
        self.assertEqual(
            nueva.bambu_material,
            "PLA",
        )
        self.assertEqual(
            nueva.bambu_color_nombre,
            "Azul",
        )
        self.assertTrue(
            nueva.bambu_requiere_cambio_manual,
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
