from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from productos.models import (
    ArchivoImpresion,
    Producto,
    TipoProducto,
)

from .models import (
    Impresora,
    ImpresoraEstadoBambu,
    Produccion,
)
from .views import _archivo_impresion_coincidente


class ImpresionExternaBambuTests(TestCase):
    def setUp(self):
        self.usuario = (
            get_user_model()
            .objects.create_user(
                username="externa-test",
                password="test-pass",
            )
        )
        self.client.force_login(
            self.usuario
        )

        tipo = TipoProducto.objects.create(
            nombre="Externa Bambu",
        )

        self.producto = Producto.objects.create(
            nombre="Pepino sensorial",
            categoria="PRODUCTO",
            tipo=tipo,
            horas=1,
            minutos=30,
            requiere_impresion=True,
            activo=True,
            stock=0,
        )

        self.impresora = Impresora.objects.create(
            nombre="A1 COMBO test",
        )

        self.estado_bambu = (
            ImpresoraEstadoBambu.objects.create(
                impresora=self.impresora,
                serial="SERIAL-EXTERNA-1",
                nombre_bridge="A1-40",
                conectada=True,
                estado="RUNNING",
                progreso=15,
                minutos_restantes=80,
                trabajo="pepino_x6.gcode.3mf",
            )
        )

        self.archivo = ArchivoImpresion.objects.create(
            producto=self.producto,
            nombre="Pepino x6",
            version="v1",
            cantidad_unidades=6,
            archivo=(
                "productos/P0001/"
                "pepino_x6.gcode.3mf"
            ),
            nombre_original=(
                "pepino_x6.gcode.3mf"
            ),
            tamano_bytes=100,
            sha256="a" * 64,
            placas=[1],
            activo=True,
            predeterminado=True,
        )

        self.produccion = Produccion.objects.create(
            producto=self.producto,
            cantidad=6,
            destino="STOCK",
            estado="PENDIENTE",
            tiempo_impresion_minutos=90,
        )

    def test_reconoce_gcode_exacto_por_nombre(self):
        encontrado = (
            _archivo_impresion_coincidente(
                "PEPINO_X6.GCODE.3MF"
            )
        )

        self.assertIsNotNone(
            encontrado
        )
        self.assertEqual(
            encontrado.id,
            self.archivo.id,
        )

    def test_vincular_impresion_externa_a_pendiente(self):
        respuesta = self.client.post(
            reverse(
                "produccion:bambu_vincular_impresion",
                args=[self.estado_bambu.id],
            ),
            {
                "produccion": str(
                    self.produccion.id
                ),
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
        self.assertEqual(
            self.produccion.impresora_id,
            self.impresora.id,
        )
        self.assertEqual(
            self.produccion.origen,
            "BAMBU_STUDIO",
        )
        self.assertEqual(
            self.produccion.bambu_trabajo,
            "pepino_x6.gcode.3mf",
        )
        self.assertEqual(
            self.produccion.archivo_impresion_id,
            self.archivo.id,
        )

    def test_vinculo_manual_sin_coincidencia_exacta(self):
        self.estado_bambu.trabajo = (
            "proyecto_sin_nombre.3mf"
        )
        self.estado_bambu.save(
            update_fields=["trabajo"]
        )

        respuesta = self.client.post(
            reverse(
                "produccion:bambu_vincular_impresion",
                args=[self.estado_bambu.id],
            ),
            {
                "produccion": str(
                    self.produccion.id
                ),
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
        self.assertIsNone(
            self.produccion.archivo_impresion_id,
        )

    def test_no_permite_iniciar_otro_trabajo_si_bambu_ya_imprime(self):
        otra = Produccion.objects.create(
            producto=self.producto,
            cantidad=1,
            destino="STOCK",
            estado="PENDIENTE",
            tiempo_impresion_minutos=30,
        )

        respuesta = self.client.post(
            reverse(
                "produccion:iniciar",
                args=[otra.id],
            ),
            {
                "impresora": str(
                    self.impresora.id
                ),
            },
        )

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        otra.refresh_from_db()

        self.assertEqual(
            otra.estado,
            "PENDIENTE",
        )
        self.assertIsNone(
            otra.impresora_id,
        )

    def test_rechaza_vinculo_si_bambu_ya_no_imprime(self):
        self.estado_bambu.estado = "IDLE"
        self.estado_bambu.save(
            update_fields=["estado"]
        )

        respuesta = self.client.post(
            reverse(
                "produccion:bambu_vincular_impresion",
                args=[self.estado_bambu.id],
            ),
            {
                "produccion": str(
                    self.produccion.id
                ),
            },
        )

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        self.produccion.refresh_from_db()

        self.assertEqual(
            self.produccion.estado,
            "PENDIENTE",
        )
