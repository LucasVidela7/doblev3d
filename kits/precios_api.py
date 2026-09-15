from decimal import Decimal

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from calculadora.precios import calcular_escenarios_kit_fijo
from productos.models import Producto


def _decimal_texto(valor, decimales="0.01"):
    return str(
        Decimal(str(valor or 0)).quantize(
            Decimal(decimales)
        )
    )


@require_POST
def recomendar_precio_fijo(request):
    producto_ids = request.POST.getlist("producto_id")
    cantidades = request.POST.getlist("cantidad")

    agrupados = {}

    for producto_id, cantidad_raw in zip(
        producto_ids,
        cantidades,
    ):
        producto_id = str(producto_id or "").strip()
        cantidad_raw = str(cantidad_raw or "").strip()

        if not producto_id:
            continue

        try:
            producto_id_int = int(producto_id)
            cantidad = int(cantidad_raw)
        except (TypeError, ValueError):
            return JsonResponse(
                {
                    "ok": False,
                    "mensaje": "La composición contiene valores inválidos.",
                },
                status=400,
            )

        if cantidad <= 0:
            return JsonResponse(
                {
                    "ok": False,
                    "mensaje": "Las cantidades deben ser mayores a cero.",
                },
                status=400,
            )

        agrupados[producto_id_int] = (
            agrupados.get(producto_id_int, 0)
            + cantidad
        )

    if not agrupados:
        return JsonResponse(
            {
                "ok": False,
                "mensaje": "Agregá al menos un producto a la composición fija.",
            },
            status=400,
        )

    productos = Producto.objects.filter(
        id__in=agrupados.keys(),
        activo=True,
    ).in_bulk()

    if len(productos) != len(agrupados):
        return JsonResponse(
            {
                "ok": False,
                "mensaje": "Alguno de los productos ya no está disponible.",
            },
            status=400,
        )

    componentes = [
        {
            "producto": productos[producto_id],
            "cantidad": cantidad,
        }
        for producto_id, cantidad in agrupados.items()
    ]

    calculo = calcular_escenarios_kit_fijo(componentes)

    if calculo["costo_total"] <= 0:
        return JsonResponse(
            {
                "ok": False,
                "mensaje": (
                    "Los productos seleccionados no tienen un costo "
                    "productivo calculable actualmente."
                ),
            },
            status=422,
        )

    escenarios = {}

    for clave in (
        "agresivo",
        "recomendado",
        "conservador",
    ):
        escenario = calculo["escenarios"][clave]
        escenarios[clave] = {
            "precio": _decimal_texto(
                escenario["total_recomendado"]
            ),
            "margen_real": _decimal_texto(
                escenario["margen_real"],
                "0.1",
            ),
            "ganancia": _decimal_texto(
                escenario["ganancia"]
            ),
        }

    return JsonResponse(
        {
            "ok": True,
            "costo_total": _decimal_texto(
                calculo["costo_total"]
            ),
            "margen_piso": _decimal_texto(
                calculo["margen_piso"],
                "0.1",
            ),
            "escenarios": escenarios,
        }
    )
