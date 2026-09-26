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

from .views import (
    _color_bambu_bandeja,
    _nombre_remoto_print_bambu,
    _slots_ams_bambu,
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

    def test_normaliza_color_ams_rgba_real(self):
        self.assertEqual(
            _color_bambu_bandeja(
                {
                    "tray_color": "FF6910FF",
                    "cols": ["FF6910FF"],
                }
            ),
            "#FF6910",
        )

    def test_color_ams_usa_cols_si_tray_color_no_llega(self):
        self.assertEqual(
            _color_bambu_bandeja(
                {
                    "tray_color": "",
                    "cols": ["0085D5FF"],
                }
            ),
            "#0085D5",
        )

    def test_normaliza_ams_real_a1_combo(self):
        estado = ImpresoraEstadoBambu(
            ams={
                "ams": [
                    {
                        "id": "0",
                        "tray": [
                            {
                                "id": "0",
                                "tray_type": "PLA",
                                "tray_color": "FF6910FF",
                            },
                            {"id": "1"},
                            {
                                "id": "2",
                                "tray_type": "PLA",
                                "tray_color": "F6DA5AFF",
                            },
                            {
                                "id": "3",
                                "tray_type": "PLA",
                                "tray_color": "0085D5FF",
                            },
                        ],
                    }
                ],
                "tray_now": "3",
            },
            payload={},
        )

        slots, tray_now = _slots_ams_bambu(
            estado
        )

        self.assertEqual(tray_now, "3")
        self.assertEqual(
            [
                (
                    slot["ams_id"],
                    slot["tray_id"],
                    _color_bambu_bandeja(
                        slot["bandeja"]
                    ),
                )
                for slot in slots
                if slot["bandeja"].get(
                    "tray_type"
                )
            ],
            [
                (0, 0, "#FF6910"),
                (0, 2, "#F6DA5A"),
                (0, 3, "#0085D5"),
            ],
        )

    def test_normaliza_ams_lista_y_fallback_payload(self):
        estado_lista = ImpresoraEstadoBambu(
            ams=[
                {
                    "id": "0",
                    "tray": [
                        {
                            "id": "2",
                            "tray_type": "PLA",
                            "tray_color": "0085D5FF",
                        }
                    ],
                }
            ],
            payload={},
        )
        slots_lista, _ = _slots_ams_bambu(
            estado_lista
        )
        self.assertEqual(
            slots_lista[0]["tray_id"],
            2,
        )

        estado_payload = ImpresoraEstadoBambu(
            ams={},
            payload={
                "ams": {
                    "ams": [
                        {
                            "id": "0",
                            "tray": [
                                {
                                    "id": "3",
                                    "tray_type": "PLA",
                                    "cols": [
                                        "0085D5FF"
                                    ],
                                }
                            ],
                        }
                    ],
                    "tray_now": "3",
                }
            },
        )
        slots_payload, tray_now = (
            _slots_ams_bambu(
                estado_payload
            )
        )
        self.assertEqual(tray_now, "3")
        self.assertEqual(
            slots_payload[0]["tray_id"],
            3,
        )

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

    def test_sync_no_borra_ams_completo_con_paquete_parcial(self):
        ImpresoraEstadoBambu.objects.create(
            serial="03919D483100208",
            nombre_bridge="A1-40",
            conectada=True,
            estado="RUNNING",
            ams={
                "ams": [
                    {
                        "id": "0",
                        "tray": [
                            {
                                "id": "0",
                                "tray_type": "PLA",
                                "tray_color": "FF6910FF",
                            },
                            {
                                "id": "2",
                                "tray_type": "PLA",
                                "tray_color": "F6DA5AFF",
                            },
                            {
                                "id": "3",
                                "tray_type": "PLA",
                                "tray_color": "0085D5FF",
                            },
                        ],
                    }
                ],
                "tray_now": "3",
                "tray_pre": "255",
            },
        )

        payload = self._payload()
        payload["printers"][0]["ams"] = {
            "tray_pre": "3",
        }

        respuesta = self.client.post(
            reverse("bambu_bridge_sync"),
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_AUTHORIZATION=(
                "Bearer test-bridge-token"
            ),
        )

        self.assertEqual(respuesta.status_code, 200)

        estado = ImpresoraEstadoBambu.objects.get(
            serial="03919D483100208"
        )

        self.assertEqual(
            estado.ams["tray_pre"],
            "3",
        )
        self.assertEqual(
            len(estado.ams["ams"][0]["tray"]),
            3,
        )
        self.assertEqual(
            estado.ams["ams"][0]["tray"][0][
                "tray_color"
            ],
            "FF6910FF",
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
                f"DV_{archivo.sha256[:16]}"
                ".gcode.3mf"
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
            item["remote_name"],
            (
                f"DV_{archivo.sha256[:16]}"
                ".gcode.3mf"
            ),
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
            [2],
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

    def test_dos_producciones_mismo_gcode_comparten_nombre_remoto(self):
        archivo = ArchivoImpresion.objects.create(
            producto=self.producto,
            nombre="Archivo reutilizable",
            cantidad_unidades=2,
            archivo=(
                "productos/P0001/"
                "reutilizable.gcode.3mf"
            ),
            nombre_original=(
                "reutilizable.gcode.3mf"
            ),
            tamano_bytes=12345,
            sha256="a" * 64,
            placas=[1],
            activo=True,
            predeterminado=True,
        )
        primera = Produccion.objects.create(
            producto=self.producto,
            cantidad=2,
            estado="PENDIENTE",
            archivo_impresion=archivo,
        )
        segunda = Produccion.objects.create(
            producto=self.producto,
            cantidad=2,
            estado="PENDIENTE",
            archivo_impresion=archivo,
        )

        nombre_primera = _nombre_remoto_print_bambu(
            primera,
            archivo,
        )
        nombre_segunda = _nombre_remoto_print_bambu(
            segunda,
            archivo,
        )

        self.assertNotEqual(
            primera.codigo,
            segunda.codigo,
        )
        self.assertEqual(
            nombre_primera,
            nombre_segunda,
        )
        self.assertEqual(
            nombre_primera,
            "DV_aaaaaaaaaaaaaaaa.gcode.3mf",
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
            bambu_trabajo="DV_bbbbbbbbbbbbbbbb.gcode.3mf",
        )
        ComandoBambu.objects.create(
            tipo="PRINT",
            estado="EJECUTADO",
            impresora_estado=estado,
            produccion=produccion,
            trabajo_bambu_esperado=(
                "DV_bbbbbbbbbbbbbbbb.gcode.3mf"
            ),
        )

        payload = self._payload()
        payload["printers"][0]["status"] = "RUNNING"
        payload["printers"][0]["job_name"] = (
            "DV_PRD0001_bbbbbbbb.gcode.3mf"
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
            "DV_PRD0001_bbbbbbbb.gcode.3mf",
        )
