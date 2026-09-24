from calendar import monthrange
from datetime import date, datetime, time
from decimal import Decimal, ROUND_HALF_UP

from django.utils import timezone

from .models import CuotaGasto


def fecha_mas_meses(fecha, meses):
    indice = fecha.year * 12 + fecha.month - 1 + meses
    anio = indice // 12
    mes = indice % 12 + 1
    ultimo_dia = monthrange(anio, mes)[1]
    return date(
        anio,
        mes,
        min(fecha.day, ultimo_dia),
    )


def crear_cuotas_gasto(gasto):
    gasto.cuotas.all().delete()

    cantidad = max(int(gasto.cantidad_cuotas or 1), 1)
    total = Decimal(str(gasto.monto_total)).quantize(
        Decimal("0.01")
    )
    monto_base = (
        total / Decimal(cantidad)
    ).quantize(
        Decimal("0.01"),
        rounding=ROUND_HALF_UP,
    )

    if gasto.medio_pago == "TARJETA_CREDITO":
        fecha_base = (
            gasto.fecha_primera_cuota
            or gasto.fecha_compra
        )
        acumulado = Decimal("0")

        for numero in range(1, cantidad + 1):
            if numero < cantidad:
                monto = monto_base
                acumulado += monto
            else:
                monto = (
                    total - acumulado
                ).quantize(Decimal("0.01"))

            CuotaGasto.objects.create(
                gasto=gasto,
                numero=numero,
                fecha_vencimiento=fecha_mas_meses(
                    fecha_base,
                    numero - 1,
                ),
                monto=monto,
                pagada=False,
                fecha_pago=None,
                pagada_en=None,
            )
        return

    if gasto.fecha_compra == timezone.localdate():
        pagada_en = timezone.now()
    else:
        pagada_en = timezone.make_aware(
            datetime.combine(
                gasto.fecha_compra,
                time.min,
            )
        )

    CuotaGasto.objects.create(
        gasto=gasto,
        numero=1,
        fecha_vencimiento=gasto.fecha_compra,
        monto=total,
        pagada=True,
        fecha_pago=gasto.fecha_compra,
        pagada_en=pagada_en,
    )
