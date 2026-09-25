import json

from django.test import TestCase, override_settings
from django.urls import reverse

from .models import ImpresoraEstadoBambu


@override_settings(
    BAMBU_BRIDGE_TOKEN="test-bridge-token",
)
class BambuBridgeSyncTests(TestCase):
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
