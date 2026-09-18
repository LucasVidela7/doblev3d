from django.shortcuts import redirect


def impresiones_por_producto(request):
    """
    Ruta histórica conservada por compatibilidad.
    La necesidad de impresión y la producción ahora viven en Planificación.
    """
    return redirect("produccion:lista")
