from django.db import transaction
from django.http import JsonResponse

from .models import TipoProducto


@transaction.atomic
def crear_tipo_producto(request):
    if request.method != "POST":
        return JsonResponse(
            {
                "ok": False,
                "mensaje": "Método no permitido.",
            },
            status=405,
        )

    nombre = request.POST.get("nombre", "").strip()

    if not nombre:
        return JsonResponse(
            {
                "ok": False,
                "mensaje": "Ingresá un nombre para el nuevo tipo.",
            },
            status=400,
        )

    existente = (
        TipoProducto.objects
        .filter(nombre__iexact=nombre)
        .first()
    )

    creado = False

    if existente:
        tipo = existente
        if not tipo.activo:
            tipo.activo = True
            tipo.save(update_fields=["activo"])
    else:
        tipo = TipoProducto.objects.create(
            nombre=nombre,
            activo=True,
        )
        creado = True

    return JsonResponse(
        {
            "ok": True,
            "creado": creado,
            "tipo": {
                "id": tipo.id,
                "nombre": tipo.nombre,
            },
        }
    )
