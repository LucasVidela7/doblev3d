from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Gasto


class CentroFinancieroTests(TestCase):
    def setUp(self):
        usuario = get_user_model().objects.create_user(
            username="centro-financiero",
            password="test12345",
        )
        self.client.force_login(usuario)

    def test_resumen_abre_mes_actual_por_defecto(self):
        respuesta = self.client.get(
            reverse("pedidos:finanzas"),
        )

        hoy = timezone.localdate()

        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.context["vista"], "resumen")
        self.assertEqual(
            respuesta.context["rango"]["rango"],
            "mes_actual",
        )
        self.assertEqual(
            respuesta.context["inicio_periodo"],
            hoy.replace(day=1),
        )
        self.assertContains(respuesta, "NECESITAN ATENCIÓN")
        self.assertContains(respuesta, "COBROS RECIENTES")
        self.assertContains(respuesta, "GASTOS RECIENTES")

    def test_metricas_superiores_navegan_a_cada_seccion(self):
        respuesta = self.client.get(
            reverse("pedidos:finanzas"),
        )

        self.assertEqual(respuesta.status_code, 200)
        contenido = respuesta.content.decode()

        self.assertIn("vista=caja", contenido)
        self.assertIn("vista=cobros", contenido)
        self.assertIn("vista=gastos", contenido)
        self.assertIn("vista=cuotas", contenido)
        self.assertIn("vista=rentabilidad", contenido)

    def test_gastos_se_paginan_de_a_20(self):
        hoy = timezone.localdate()

        for indice in range(25):
            Gasto.objects.create(
                fecha_compra=hoy - timedelta(
                    days=indice % 10
                ),
                tipo="OPERATIVO",
                categoria="INSUMOS",
                descripcion=f"Gasto {indice + 1}",
                monto_total=Decimal("1000"),
                medio_pago="TRANSFERENCIA",
                cantidad_cuotas=1,
            )

        respuesta = self.client.get(
            reverse("pedidos:finanzas"),
            {
                "vista": "gastos",
                "rango": "mes_actual",
            },
        )

        self.assertEqual(respuesta.status_code, 200)
        pagina = respuesta.context["gastos_pagina"]
        self.assertEqual(len(pagina.object_list), 20)
        self.assertEqual(pagina.paginator.num_pages, 2)

    def test_segunda_pagina_de_gastos_no_duplica_la_primera(self):
        hoy = timezone.localdate()

        for indice in range(25):
            Gasto.objects.create(
                fecha_compra=hoy,
                tipo="OPERATIVO",
                categoria="INSUMOS",
                descripcion=f"Gasto paginado {indice + 1}",
                monto_total=Decimal("1000"),
                medio_pago="TRANSFERENCIA",
                cantidad_cuotas=1,
            )

        primera = self.client.get(
            reverse("pedidos:finanzas"),
            {
                "vista": "gastos",
                "page": 1,
            },
        )
        segunda = self.client.get(
            reverse("pedidos:finanzas"),
            {
                "vista": "gastos",
                "page": 2,
            },
        )

        ids_primera = {
            item.id
            for item in primera.context[
                "gastos_pagina"
            ].object_list
        }
        ids_segunda = {
            item.id
            for item in segunda.context[
                "gastos_pagina"
            ].object_list
        }

        self.assertEqual(len(ids_primera), 20)
        self.assertEqual(len(ids_segunda), 5)
        self.assertFalse(
            ids_primera.intersection(ids_segunda)
        )
