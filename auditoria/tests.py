from django.contrib.auth import get_user_model
from django.test import TestCase

from clientes.models import Cliente
from pedidos.models import Pago, Pedido

from .context import contexto_auditoria
from .models import RegistroAuditoria


class AuditoriaTests(TestCase):
    def setUp(self):
        self.usuario = get_user_model().objects.create_user(
            username="lucas",
            password="ClaveSegura-12345",
        )

    def test_registra_usuario_ruta_y_alta(self):
        with contexto_auditoria(
            usuario=self.usuario,
            ruta="/clientes/",
            metodo="POST",
            ip="127.0.0.1",
        ):
            cliente = Cliente.objects.create(
                nombre="Cliente auditado",
                telefono="1111",
            )

        registro = RegistroAuditoria.objects.get(
            app_label="clientes",
            modelo="cliente",
            objeto_id=str(cliente.id),
        )

        self.assertEqual(registro.usuario, self.usuario)
        self.assertEqual(registro.usuario_nombre, "lucas")
        self.assertEqual(registro.accion, "CREAR")
        self.assertEqual(registro.ruta, "/clientes/")
        self.assertEqual(registro.metodo, "POST")
        self.assertEqual(registro.ip, "127.0.0.1")

    def test_registra_solo_campos_modificados(self):
        cliente = Cliente.objects.create(nombre="Cliente")
        RegistroAuditoria.objects.all().delete()

        with contexto_auditoria(usuario=self.usuario, ruta="/clientes/1/"):
            cliente.telefono = "15-1234"
            cliente.save(update_fields=["telefono"])

        registro = RegistroAuditoria.objects.get()

        self.assertEqual(registro.accion, "MODIFICAR")
        self.assertEqual(
            registro.cambios["telefono"],
            {"antes": "", "despues": "15-1234"},
        )
        self.assertEqual(set(registro.cambios), {"telefono"})

    def test_entrega_de_pedido_tiene_accion_especifica(self):
        cliente = Cliente.objects.create(nombre="Cliente")
        pedido = Pedido.objects.create(cliente=cliente, estado="LISTO")
        RegistroAuditoria.objects.all().delete()

        with contexto_auditoria(usuario=self.usuario, ruta=f"/pedidos/{pedido.id}/entregar/"):
            pedido.estado = "ENTREGADO"
            pedido.save(update_fields=["estado"])

        registro = RegistroAuditoria.objects.get()
        self.assertEqual(registro.accion, "ENTREGAR_PEDIDO")
        self.assertEqual(
            registro.cambios["estado"],
            {"antes": "LISTO", "despues": "ENTREGADO"},
        )

    def test_registrar_pago_tiene_accion_especifica(self):
        cliente = Cliente.objects.create(nombre="Cliente")
        pedido = Pedido.objects.create(cliente=cliente)
        RegistroAuditoria.objects.all().delete()

        with contexto_auditoria(usuario=self.usuario, ruta=f"/pedidos/{pedido.id}/pago/"):
            pago = Pago.objects.create(
                pedido=pedido,
                monto="15000.00",
                medio="EFECTIVO",
            )

        registro = RegistroAuditoria.objects.get(
            modelo="pago",
            objeto_id=str(pago.id),
        )
        self.assertEqual(registro.accion, "REGISTRAR_PAGO")
        self.assertEqual(registro.usuario_nombre, "lucas")

    def test_registra_eliminacion(self):
        cliente = Cliente.objects.create(nombre="Temporal")
        RegistroAuditoria.objects.all().delete()
        cliente_id = cliente.id

        with contexto_auditoria(usuario=self.usuario, ruta=f"/clientes/{cliente_id}/"):
            cliente.delete()

        registro = RegistroAuditoria.objects.get(
            app_label="clientes",
            modelo="cliente",
            objeto_id=str(cliente_id),
        )
        self.assertEqual(registro.accion, "ELIMINAR")
        self.assertEqual(registro.cambios["nombre"]["antes"], "Temporal")
        self.assertIsNone(registro.cambios["nombre"]["despues"])
