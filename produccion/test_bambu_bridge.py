import json

from django.test import TestCase, override_settings
from django.urls import reverse

from productos.models import ArchivoImpresion, Producto, TipoProducto

from .models import (
    ComandoBambu,
    Impresora,
    ImpresoraEstadoBambu,
    Produccion,
)


@override_settings(
    BAMBU_BRIDGE_TOKEN="test-bridge-token",
)
class BambuBridgeSyncTests(TestCase):
    def setUp(self):
        tipo = TipoProducto.objects.create(
            nombre="Tipo Bambu test",
        )
        self.producto = Producto.objects.create(
            nombre="Producto Bambu test",
            categoria="PRODUCTO",
            tipo=tipo,
            requiere_impresion=True,
            activo=True,
        )
        self.impresora = Impresora.objects.create(
            nombre="A1 Gestión test",
        )

    def _payload(self):
        return {
            "bridge_id": "doblev3d-bambu",
            "printers": [
                {
                    "name": "A1-40",
                    "connected": True,
                    "ip": "192.168.1.40",
                    "serial": "03919D483100208",
                    "status": "RUNNING",
                    "progress": 33,
                    "remaining_minutes": 256,
                    "job_name": "pieza.3mf",
                    "nozzle_temp": 219.8,
                    "bed_temp": 65.1,
                    "wifi": "-54dBm",
                    "last_update": 1790344318.45,
                }
            ],
        }

    def test_rechaza_sin_token(self):
        respuesta = self.client.post(
            reverse("bambu_bridge_sync"),
            data=json.dumps(self._payload()),
            content_type="application/json",
        )

        self.assertEqual(
            respuesta.status_code,
            401,
        )

    def test_sincroniza_estado_impresora(self):
        respuesta = self.client.post(
            reverse("bambu_bridge_sync"),
            data=json.dumps(self._payload()),
            content_type="application/json",
            HTTP_AUTHORIZATION=(
                "Bearer test-bridge-token"
            ),
        )

        self.assertEqual(
            respuesta.status_code,
            200,
        )

        estado = (
            ImpresoraEstadoBambu.objects.get(
                serial="03919D483100208"
            )
        )

        self.assertTrue(estado.conectada)
        self.assertEqual(
            estado.estado,
            "RUNNING",
        )
        self.assertEqual(
            estado.progreso,
            33,
        )
        self.assertEqual(
            estado.minutos_restantes,
            256,
        )
        self.assertEqual(
            estado.trabajo,
            "pieza.3mf",
        )

    def test_actualiza_mismo_serial_sin_duplicar(self):
        payload = self._payload()

        for progreso in (33, 34):
            payload["printers"][0]["progress"] = progreso

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

        self.assertEqual(
            ImpresoraEstadoBambu.objects.count(),
            1,
        )

        self.assertEqual(
            ImpresoraEstadoBambu.objects.get().progreso,
            34,
        )


    def test_sync_entrega_payload_print_con_archivo_y_filamento(self):
        estado = ImpresoraEstadoBambu.objects.create(
            impresora=self.impresora,
            serial="03919D483100208",
            nombre_bridge="A1-40",
            conectada=True,
            estado="FINISH",
        )
        archivo = ArchivoImpresion.objects.create(
            producto=self.producto,
            nombre="Archivo test",
            cantidad_unidades=1,
            archivo="productos/P0001/test.gcode.3mf",
            nombre_original="test.gcode.3mf",
            tamano_bytes=98765,
            sha256="b" * 64,
            placas=[1],
            activo=True,
            predeterminado=True,
        )
        produccion = Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            impresora=self.impresora,
            estado="PENDIENTE",
            archivo_impresion=archivo,
            bambu_fuente_filamento="AMS",
            bambu_ams_id=0,
            bambu_tray_id=2,
        )
        comando = ComandoBambu.objects.create(
            tipo="PRINT",
            impresora_estado=estado,
            produccion=produccion,
            trabajo_bambu_esperado=(
                f"DV_{produccion.codigo}_"
                f"{archivo.sha256[:8]}.gcode.3mf"
            ),
        )

        payload = self._payload()
        payload["printers"][0]["status"] = "FINISH"
        payload["printers"][0]["job_name"] = ""

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

        data = respuesta.json()
        self.assertEqual(
            len(data["commands"]),
            1,
        )

        item = data["commands"][0]

        self.assertEqual(
            item["command_id"],
            str(comando.id_comando),
        )
        self.assertEqual(
            item["type"],
            "PRINT",
        )
        self.assertEqual(
            item["file_sha256"],
            archivo.sha256,
        )
        self.assertEqual(
            item["file_size_bytes"],
            archivo.tamano_bytes,
        )
        self.assertEqual(
            item["plate"],
            1,
        )
        self.assertTrue(
            item["use_ams"],
        )
        self.assertEqual(
            item["ams_mapping"],
            [2, -1, -1, -1, -1],
        )

    def test_confirma_resultado_comando_con_produccion_nullable(self):
        estado = ImpresoraEstadoBambu.objects.create(
            impresora=self.impresora,
            serial="TEST-COMMAND-RESULT",
            nombre_bridge="A1-test",
            conectada=True,
            estado="FINISH",
        )
        produccion = Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            impresora=self.impresora,
            estado="PENDIENTE",
        )
        comando = ComandoBambu.objects.create(
            tipo="PRINT",
            impresora_estado=estado,
            produccion=produccion,
            trabajo_bambu_esperado="test.gcode.3mf",
        )

        payload = {
            "printers": [
                {
                    "name": "A1-test",
                    "connected": True,
                    "serial": "TEST-COMMAND-RESULT",
                    "status": "FINISH",
                }
            ],
            "command_results": [
                {
                    "command_id": str(comando.id_comando),
                    "ok": False,
                    "error": "timeout de prueba",
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
        self.assertEqual(
            comando.estado,
            "ERROR",
        )
        self.assertEqual(
            comando.error,
            "timeout de prueba",
        )

    def test_telemetria_promueve_print_confirmado_a_imprimiendo(self):
        estado = ImpresoraEstadoBambu.objects.create(
            impresora=self.impresora,
            serial="03919D483100208",
            nombre_bridge="A1-40",
            conectada=True,
            estado="FINISH",
        )
        produccion = Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            impresora=self.impresora,
            estado="PENDIENTE",
            bambu_trabajo="DV_PRD0001_test.gcode.3mf",
        )
        ComandoBambu.objects.create(
            tipo="PRINT",
            estado="EJECUTADO",
            impresora_estado=estado,
            produccion=produccion,
            trabajo_bambu_esperado=(
                "DV_PRD0001_test.gcode.3mf"
            ),
        )

        payload = self._payload()
        payload["printers"][0]["status"] = "RUNNING"
        payload["printers"][0]["job_name"] = (
            "DV_PRD0001_test.gcode.3mf"
        )

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

        produccion.refresh_from_db()

        self.assertEqual(
            produccion.estado,
            "IMPRIMIENDO",
        )
        self.assertIsNotNone(
            produccion.inicio_impresion,
        )
        self.assertEqual(
            produccion.bambu_trabajo,
            "DV_PRD0001_test.gcode.3mf",
        )
