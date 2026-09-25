import io
import tempfile
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from productos.models import (
    ArchivoImpresion,
    Producto,
    TipoProducto,
)

from .models import Produccion


class GcodeDesdeProduccionTests(TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)

        override = self.override_settings(
            PRINT_FILES_ROOT=self.tempdir.name,
            PRINT_FILES_PERSISTENT=True,
            STORAGES={
                "default": {
                    "BACKEND": (
                        "django.core.files.storage.FileSystemStorage"
                    ),
                    "OPTIONS": {
                        "location": self.tempdir.name,
                        "base_url": "/_private_print_files/",
                    },
                },
                "staticfiles": {
                    "BACKEND": (
                        "django.contrib.staticfiles.storage.StaticFilesStorage"
                    ),
                },
            },
        )
        override.enable()
        self.addCleanup(override.disable)

        usuario = get_user_model().objects.create_user(
            username="gcode-produccion-test",
            password="test-pass",
        )
        self.client.force_login(usuario)

        tipo = TipoProducto.objects.create(
            nombre="Gcode producción",
        )

        self.producto = Producto.objects.create(
            nombre="Pepino sensorial",
            categoria="PRODUCTO",
            tipo=tipo,
            horas=1,
            minutos=0,
            requiere_impresion=True,
            activo=True,
            stock=0,
        )

        self.produccion = Produccion.objects.create(
            producto=self.producto,
            cantidad=6,
            destino="STOCK",
            estado="PENDIENTE",
            tiempo_impresion_minutos=60,
        )

        self.otra_pendiente = Produccion.objects.create(
            producto=self.producto,
            cantidad=6,
            destino="STOCK",
            estado="PENDIENTE",
            tiempo_impresion_minutos=60,
        )

    def _archivo(self, nombre, contenido):
        buffer = io.BytesIO()

        with zipfile.ZipFile(
            buffer,
            "w",
            zipfile.ZIP_DEFLATED,
        ) as paquete:
            paquete.writestr(
                "Metadata/plate_1.gcode",
                contenido,
            )

        return SimpleUploadedFile(
            nombre,
            buffer.getvalue(),
            content_type="application/octet-stream",
        )

    def test_carga_desde_produccion_asocia_a_pendientes_iguales(self):
        respuesta = self.client.post(
            reverse(
                "produccion:cargar_gcode",
                args=[self.produccion.id],
            ),
            {
                "archivo": self._archivo(
                    "pepino-x6.gcode.3mf",
                    "; v1\nG28\n",
                ),
                "version": "v1",
                "perfil_impresora": "A1 · 0.4 mm",
            },
        )

        self.assertEqual(
            respuesta.status_code,
            302,
        )

        archivo = ArchivoImpresion.objects.get()

        self.assertEqual(
            archivo.cantidad_unidades,
            6,
        )
        self.assertTrue(
            archivo.predeterminado,
        )

        self.produccion.refresh_from_db()
        self.otra_pendiente.refresh_from_db()

        self.assertEqual(
            self.produccion.archivo_impresion_id,
            archivo.id,
        )
        self.assertEqual(
            self.otra_pendiente.archivo_impresion_id,
            archivo.id,
        )

    def test_nueva_carga_sustituye_principal_y_conserva_anterior(self):
        url = reverse(
            "produccion:cargar_gcode",
            args=[self.produccion.id],
        )

        self.client.post(
            url,
            {
                "archivo": self._archivo(
                    "pepino-x6-v1.gcode.3mf",
                    "; v1\nG28\n",
                ),
                "version": "v1",
            },
        )

        anterior = ArchivoImpresion.objects.get()

        self.client.post(
            url,
            {
                "archivo": self._archivo(
                    "pepino-x6-v2.gcode.3mf",
                    "; v2\nG28\nG1 X10\n",
                ),
                "version": "v2",
            },
        )

        anterior.refresh_from_db()
        nuevo = ArchivoImpresion.objects.exclude(
            id=anterior.id
        ).get()

        self.assertFalse(
            anterior.activo,
        )
        self.assertFalse(
            anterior.predeterminado,
        )
        self.assertTrue(
            nuevo.activo,
        )
        self.assertTrue(
            nuevo.predeterminado,
        )
        self.assertEqual(
            nuevo.reemplaza_a_id,
            anterior.id,
        )

        self.produccion.refresh_from_db()
        self.assertEqual(
            self.produccion.archivo_impresion_id,
            nuevo.id,
        )

    def test_no_permite_cambiar_gcode_si_ya_imprime(self):
        self.produccion.estado = "IMPRIMIENDO"
        self.produccion.save(
            update_fields=["estado"]
        )

        respuesta = self.client.post(
            reverse(
                "produccion:cargar_gcode",
                args=[self.produccion.id],
            ),
            {
                "archivo": self._archivo(
                    "pepino-x6.gcode.3mf",
                    "; test\nG28\n",
                ),
            },
        )

        self.assertEqual(
            respuesta.status_code,
            404,
        )
        self.assertFalse(
            ArchivoImpresion.objects.exists()
        )
