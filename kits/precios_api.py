from decimal import Decimal

from django.http import JsonResponse
from django.views.decorators.http import require_POST

from calculadora.precios import calcular_escenarios_kit_libre
from productos.models import Producto, TipoProducto

from .precio_fijo_combinado import calcular_escenarios_kit_fijo


def _decimal_texto(valor, decimales="0.01"):
    return str(
        Decimal(str(valor or 0)).quantize(
            Decimal(decimales)
        )
    )


def _filamento_json(calculo):
    return {
        "tipo": calculo.get("tipo_filamento", "estandar"),
        "economico": bool(
            calculo.get("filamento_economico", False)
        ),
        "precio_kg": _decimal_texto(
            calculo.get("precio_filamento_kg", 0)
        ),
    }


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
            "referencia_separada": _decimal_texto(
                escenario.get("referencia_separada", 0)
            ),
            "ahorro_combo": _decimal_texto(
                escenario.get("ahorro_combo", 0)
            ),
        }

    return JsonResponse(
        {
            "ok": True,
            "tipo": "FIJO",
            "cantidad_total": calculo.get("cantidad_total", 0),
            "costo_total": _decimal_texto(
                calculo["costo_total"]
            ),
            "margen_tope_ponderado": _decimal_texto(
                calculo.get("margen_tope_ponderado", 0),
                "0.1",
            ),
            "margen_piso": _decimal_texto(
                calculo["margen_piso"],
                "0.1",
            ),
            "filamento": _filamento_json(calculo),
            "escenarios": escenarios,
        }
    )


@require_POST
def recomendar_precio_libre(request):
    tipo_id = str(
        request.POST.get("tipo_producto") or ""
    ).strip()
    cantidad_raw = str(
        request.POST.get("cantidad") or ""
    ).strip()

    try:
        tipo_id_int = int(tipo_id)
        cantidad = int(cantidad_raw)
    except (TypeError, ValueError):
        return JsonResponse(
            {
                "ok": False,
                "mensaje": "Elegí una categoría y una cantidad válida.",
            },
            status=400,
        )

    if cantidad <= 0:
        return JsonResponse(
            {
                "ok": False,
                "mensaje": "La cantidad del kit debe ser mayor a cero.",
            },
            status=400,
        )

    try:
        tipo = TipoProducto.objects.get(
            id=tipo_id_int,
            activo=True,
        )
    except TipoProducto.DoesNotExist:
        return JsonResponse(
            {
                "ok": False,
                "mensaje": "La categoría seleccionada no está disponible.",
            },
            status=404,
        )

    productos = list(
        Producto.objects.filter(
            tipo=tipo,
            activo=True,
            solo_produccion=False,
        ).order_by("id")
    )

    if not productos:
        return JsonResponse(
            {
                "ok": False,
                "mensaje": (
                    "No hay productos comerciales activos en esta categoría "
                    "para calcular los escenarios."
                ),
            },
            status=422,
        )

    calculo = calcular_escenarios_kit_libre(
        productos,
        cantidad,
    )

    if calculo["costo_peor_caso"] <= 0:
        return JsonResponse(
            {
                "ok": False,
                "mensaje": (
                    "Los productos de la categoría no tienen un costo "
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
            "margen_promedio": _decimal_texto(
                escenario["margen_promedio"],
                "0.1",
            ),
            "margen_peor_caso": _decimal_texto(
                escenario["margen_peor_caso"],
                "0.1",
            ),
            "ganancia_promedio": _decimal_texto(
                escenario["ganancia_promedio"]
            ),
            "ganancia_peor_caso": _decimal_texto(
                escenario["ganancia_peor_caso"]
            ),
        }

    return JsonResponse(
        {
            "ok": True,
            "tipo": "LIBRE_CATEGORIA",
            "categoria": tipo.nombre,
            "cantidad": calculo["cantidad"],
            "productos_categoria": calculo[
                "cantidad_productos_categoria"
            ],
            "costo_promedio": _decimal_texto(
                calculo["costo_promedio"]
            ),
            "costo_peor_caso": _decimal_texto(
                calculo["costo_peor_caso"]
            ),
            "margen_piso": _decimal_texto(
                calculo["margen_piso"],
                "0.1",
            ),
            "filamento": _filamento_json(calculo),
            "escenarios": escenarios,
        }
    )
