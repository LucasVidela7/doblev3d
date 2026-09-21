from django.test import TestCase
from django.urls import reverse


class HealthcheckTests(TestCase):
    def test_healthcheck_publico_responde_ok(self):
        response = self.client.get(reverse("healthcheck"))

        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(
            response.content,
            {"ok": True, "database": "ok"},
        )
