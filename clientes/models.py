from django.db import models


class Cliente(models.Model):

    nombre = models.CharField(
        max_length=150
    )

    telefono = models.CharField(
        max_length=30,
        blank=True
    )

    email = models.EmailField(
        blank=True
    )

    observaciones = models.TextField(
        blank=True
    )

    activo = models.BooleanField(
        default=True
    )

    @property
    def codigo(self):
        return f"C{self.id:04d}" if self.id else "NUEVO"

    def __str__(self):
        return self.nombre


class ContactoCliente(models.Model):
    MOTIVOS = [
        ("GENERICO", "Contacto general"),
        ("PEDIDO_LISTO", "Pedido listo"),
        ("SALDO", "Saldo pendiente"),
        ("PRESUPUESTO", "Presupuesto pendiente"),
        ("REACTIVACION", "Reactivar cliente"),
    ]

    cliente = models.ForeignKey(
        Cliente,
        on_delete=models.CASCADE,
        related_name="contactos",
    )

    canal = models.CharField(
        max_length=20,
        default="WHATSAPP",
    )

    motivo = models.CharField(
        max_length=30,
        choices=MOTIVOS,
        default="GENERICO",
    )

    referencia = models.CharField(
        max_length=40,
        blank=True,
    )

    mensaje = models.TextField(
        blank=True,
    )

    iniciado_en = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        ordering = ["-iniciado_en", "-id"]

    def __str__(self):
        return (
            f"{self.cliente.codigo} · "
            f"{self.get_motivo_display()}"
        )
