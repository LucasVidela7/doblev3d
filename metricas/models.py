from django.db import models


class MetricasConfiguracion(models.Model):
    activas = models.BooleanField(
        default=True,
        verbose_name="Métricas del catálogo activas",
    )
    retencion_dias = models.PositiveSmallIntegerField(
        default=180,
        verbose_name="Retención de métricas en días",
    )

    class Meta:
        verbose_name = "Configuración de métricas"
        verbose_name_plural = "Configuración de métricas"

    def save(self, *args, **kwargs):
        self.pk = 1
        self.retencion_dias = max(
            30,
            min(int(self.retencion_dias or 180), 365),
        )
        super().save(*args, **kwargs)

    def __str__(self):
        return "Métricas del catálogo"


class EventoCatalogo(models.Model):
    PAGE_VIEW = "PAGE_VIEW"
    ADD_TO_CART = "ADD_TO_CART"
    CHECKOUT_START = "CHECKOUT_START"
    SOLICITUD = "SOLICITUD"
    WHATSAPP = "WHATSAPP"
    INSTAGRAM = "INSTAGRAM"

    EVENTOS = [
        (PAGE_VIEW, "Vista"),
        (ADD_TO_CART, "Agregar al carrito"),
        (CHECKOUT_START, "Inicio de checkout"),
        (SOLICITUD, "Solicitud enviada"),
        (WHATSAPP, "Click en WhatsApp"),
        (INSTAGRAM, "Click en Instagram"),
    ]

    DISPOSITIVOS = [
        ("MOBILE", "Móvil"),
        ("TABLET", "Tablet"),
        ("DESKTOP", "Escritorio"),
        ("OTHER", "Otro"),
    ]

    evento = models.CharField(
        max_length=30,
        choices=EVENTOS,
        db_index=True,
    )
    visitor_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )
    session_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
    )
    pagina = models.CharField(
        max_length=40,
        blank=True,
    )
    contenido_tipo = models.CharField(
        max_length=20,
        blank=True,
    )
    contenido_id = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )
    dispositivo = models.CharField(
        max_length=12,
        choices=DISPOSITIVOS,
        default="OTHER",
    )
    origen = models.CharField(
        max_length=120,
        blank=True,
        default="Directo",
    )
    ruta = models.CharField(
        max_length=255,
        blank=True,
    )
    creada_en = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
    )

    class Meta:
        ordering = ["-creada_en", "-id"]
        indexes = [
            models.Index(
                fields=["evento", "creada_en"],
                name="metr_evento_fecha_idx",
            ),
            models.Index(
                fields=["contenido_tipo", "contenido_id", "creada_en"],
                name="metr_contenido_fecha_idx",
            ),
            models.Index(
                fields=["session_hash", "creada_en"],
                name="metr_sesion_fecha_idx",
            ),
        ]

    def __str__(self):
        return f"{self.evento} · {self.creada_en:%d/%m/%Y %H:%M}"
