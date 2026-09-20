from django.db.models import Q
from django.shortcuts import render

from .gestion import preparar_kits_gestion
from .models import Kit


def lista_kits(request):
    consulta = (
        Kit.objects
        .select_related("tipo_producto")
        .prefetch_related("componentes__producto__tipo")
        .order_by("nombre")
    )

    q = request.GET.get("q", "").strip()
    modalidad = request.GET.get("modalidad", "").strip().upper()
    estado = request.GET.get("estado", "").strip().upper()

    if q:
        consulta = consulta.filter(
            Q(nombre__icontains=q)
            | Q(tipo_producto__nombre__icontains=q)
        )

    if modalidad in {"FIJO", "LIBRE_CATEGORIA"}:
        consulta = consulta.filter(modalidad=modalidad)

    kits = preparar_kits_gestion(list(consulta))

    if estado == "ATENCION":
        kits = [
            kit
            for kit in kits
            if kit.salud_gestion["codigo"] != "SALUDABLE"
        ]
    elif estado == "INACTIVOS":
        kits = [kit for kit in kits if not kit.activo]
    elif estado == "ACTIVOS":
        kits = [kit for kit in kits if kit.activo]

    metricas = {
        "total": len(kits),
        "saludables": sum(
            1
            for kit in kits
            if kit.salud_gestion["codigo"] == "SALUDABLE"
        ),
        "atencion": sum(
            1
            for kit in kits
            if kit.salud_gestion["codigo"] != "SALUDABLE"
        ),
        "fijos": sum(
            1
            for kit in kits
            if kit.modalidad == "FIJO"
        ),
        "libres": sum(
            1
            for kit in kits
            if kit.modalidad == "LIBRE_CATEGORIA"
        ),
    }

    return render(
        request,
        "kits/lista.html",
        {
            "kits": kits,
            "metricas": metricas,
            "q": q,
            "modalidad_seleccionada": (
                modalidad
                if modalidad in {"FIJO", "LIBRE_CATEGORIA"}
                else ""
            ),
            "estado_seleccionado": (
                estado
                if estado in {"ATENCION", "INACTIVOS", "ACTIVOS"}
                else ""
            ),
        },
    )
