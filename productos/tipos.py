from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from .models import TipoProducto


@transaction.atomic
def categorias_seo(request):
    tipos = TipoProducto.objects.all().order_by("-activo", "nombre")

    if request.method == "POST":
        tipo = get_object_or_404(
            TipoProducto,
            id=request.POST.get("tipo_id"),
        )
        tipo.descripcion_catalogo = (
            request.POST.get("descripcion_catalogo", "").strip()
        )
        tipo.seo_titulo = (
            request.POST.get("seo_titulo", "").strip()[:160]
        )
        tipo.seo_descripcion = (
            request.POST.get("seo_descripcion", "").strip()[:320]
        )
        tipo.save(
            update_fields=[
                "descripcion_catalogo",
                "seo_titulo",
                "seo_descripcion",
            ]
        )
        messages.success(
            request,
            f"SEO de {tipo.nombre} actualizado.",
        )
        return redirect("productos:categorias_seo")

    return render(
        request,
        "productos/categorias_seo.html",
        {
            "tipos": tipos,
        },
    )


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
