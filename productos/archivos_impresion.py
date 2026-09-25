import hashlib
import re
import zipfile
from pathlib import PurePosixPath

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .models import ArchivoImpresion, Producto


PLATE_RE = re.compile(
    r"(?:^|/)plate_(\d+)\.gcode$",
    re.IGNORECASE,
)


def _nombre_base(nombre):
    texto = str(nombre or "").strip()
    lower = texto.lower()
    sufijo = ".gcode.3mf"

    if lower.endswith(sufijo):
        texto = texto[: -len(sufijo)]

    return texto.strip()[:180]


def _analizar_gcode_3mf(archivo):
    nombre = str(
        getattr(archivo, "name", "")
        or ""
    ).strip()

    if not nombre.lower().endswith(".gcode.3mf"):
        raise ValueError(
            "El archivo debe terminar en .gcode.3mf."
        )

    tamano = int(
        getattr(archivo, "size", 0)
        or 0
    )

    if tamano <= 0:
        raise ValueError(
            "El archivo está vacío."
        )

    maximo = int(
        getattr(
            settings,
            "PRINT_FILE_MAX_BYTES",
            250 * 1024 * 1024,
        )
    )

    if tamano > maximo:
        limite_mb = maximo // (1024 * 1024)
        raise ValueError(
            f"El archivo supera el límite de {limite_mb} MB."
        )

    sha = hashlib.sha256()

    archivo.seek(0)
    for bloque in iter(
        lambda: archivo.read(1024 * 1024),
        b"",
    ):
        sha.update(bloque)

    archivo.seek(0)

    try:
        with zipfile.ZipFile(archivo) as paquete:
            nombres = [
                str(item)
                for item in paquete.namelist()
            ]

            gcodes = [
                item
                for item in nombres
                if item.lower().endswith(".gcode")
            ]

            if not gcodes:
                raise ValueError(
                    "El .gcode.3mf no contiene ningún archivo G-code."
                )

            placas = []
            for ruta in gcodes:
                match = PLATE_RE.search(ruta)
                if not match:
                    continue
                numero = int(match.group(1))
                if numero not in placas:
                    placas.append(numero)

            placas.sort()

            # No extraemos contenido. Validamos además que las rutas del ZIP
            # sean relativas para evitar aceptar paquetes malformados.
            for ruta in nombres:
                pure = PurePosixPath(ruta)
                if pure.is_absolute() or ".." in pure.parts:
                    raise ValueError(
                        "El paquete contiene rutas internas no válidas."
                    )

    except zipfile.BadZipFile as error:
        raise ValueError(
            "El archivo no es un 3MF válido."
        ) from error
    finally:
        archivo.seek(0)

    return {
        "sha256": sha.hexdigest(),
        "tamano_bytes": tamano,
        "placas": placas,
    }


@require_POST
@transaction.atomic
def subir(request, producto_id):
    producto = get_object_or_404(
        Producto,
        id=producto_id,
    )

    archivo = request.FILES.get("archivo")

    if archivo is None:
        messages.error(
            request,
            "Seleccioná un archivo .gcode.3mf.",
        )
        return redirect(
            "productos:detalle",
            producto_id=producto.id,
        )

    try:
        analisis = _analizar_gcode_3mf(
            archivo
        )
    except ValueError as error:
        messages.error(
            request,
            str(error),
        )
        return redirect(
            "productos:detalle",
            producto_id=producto.id,
        )

    duplicado = (
        ArchivoImpresion.objects
        .filter(
            producto=producto,
            sha256=analisis["sha256"],
        )
        .first()
    )

    if duplicado:
        messages.error(
            request,
            (
                "Ese mismo archivo ya está cargado como "
                f"“{duplicado.nombre}”."
            ),
        )
        return redirect(
            "productos:detalle",
            producto_id=producto.id,
        )

    nombre = (
        request.POST.get("nombre", "")
        .strip()[:180]
        or _nombre_base(archivo.name)
        or "Archivo de impresión"
    )

    version = (
        request.POST.get("version", "")
        .strip()[:60]
    )

    perfil_impresora = (
        request.POST.get(
            "perfil_impresora",
            "",
        )
        .strip()[:120]
    )

    notas = (
        request.POST.get("notas", "")
        .strip()
    )

    predeterminado = (
        request.POST.get(
            "predeterminado"
        )
        == "1"
    )

    if (
        not producto.archivos_impresion
        .filter(activo=True)
        .exists()
    ):
        predeterminado = True

    if predeterminado:
        ArchivoImpresion.objects.filter(
            producto=producto,
            predeterminado=True,
        ).update(
            predeterminado=False
        )

    registro = ArchivoImpresion(
        producto=producto,
        nombre=nombre,
        version=version,
        nombre_original=str(
            archivo.name
        )[:255],
        tamano_bytes=analisis[
            "tamano_bytes"
        ],
        sha256=analisis["sha256"],
        placas=analisis["placas"],
        perfil_impresora=perfil_impresora,
        notas=notas,
        activo=True,
        predeterminado=predeterminado,
    )

    registro.archivo.save(
        str(archivo.name),
        archivo,
        save=False,
    )
    registro.save()

    placas = (
        ", ".join(
            str(item)
            for item in registro.placas
        )
        or "sin número de placa detectado"
    )

    messages.success(
        request,
        (
            f"Archivo “{registro.nombre}” cargado. "
            f"{registro.tamano_formateado} · "
            f"placas: {placas}."
        ),
    )

    if not getattr(
        settings,
        "PRINT_FILES_PERSISTENT",
        False,
    ):
        messages.warning(
            request,
            (
                "El almacenamiento de archivos de impresión "
                "todavía no está marcado como persistente en este entorno."
            ),
        )

    return redirect(
        "productos:detalle",
        producto_id=producto.id,
    )


def descargar(
    request,
    producto_id,
    archivo_id,
):
    registro = get_object_or_404(
        ArchivoImpresion.objects
        .select_related("producto"),
        id=archivo_id,
        producto_id=producto_id,
    )

    try:
        handle = registro.archivo.open(
            "rb"
        )
    except (FileNotFoundError, OSError):
        raise Http404(
            "El archivo físico no está disponible."
        )

    return FileResponse(
        handle,
        as_attachment=True,
        filename=registro.nombre_original,
        content_type="application/octet-stream",
    )


@require_POST
@transaction.atomic
def predeterminar(
    request,
    producto_id,
    archivo_id,
):
    registro = get_object_or_404(
        ArchivoImpresion.objects
        .select_for_update()
        .select_related("producto"),
        id=archivo_id,
        producto_id=producto_id,
        activo=True,
    )

    ArchivoImpresion.objects.filter(
        producto_id=producto_id,
        predeterminado=True,
    ).exclude(
        id=registro.id,
    ).update(
        predeterminado=False
    )

    if not registro.predeterminado:
        registro.predeterminado = True
        registro.save(
            update_fields=[
                "predeterminado",
                "actualizado_en",
            ]
        )

    messages.success(
        request,
        (
            f"“{registro.nombre}” quedó como "
            "archivo predeterminado."
        ),
    )

    return redirect(
        "productos:detalle",
        producto_id=producto_id,
    )


@require_POST
@transaction.atomic
def cambiar_activo(
    request,
    producto_id,
    archivo_id,
):
    registro = get_object_or_404(
        ArchivoImpresion.objects
        .select_for_update(),
        id=archivo_id,
        producto_id=producto_id,
    )

    registro.activo = not registro.activo

    if not registro.activo:
        registro.predeterminado = False

    registro.save(
        update_fields=[
            "activo",
            "predeterminado",
            "actualizado_en",
        ]
    )

    if registro.activo:
        existe_predeterminado = (
            ArchivoImpresion.objects
            .filter(
                producto_id=producto_id,
                activo=True,
                predeterminado=True,
            )
            .exists()
        )

        if not existe_predeterminado:
            registro.predeterminado = True
            registro.save(
                update_fields=[
                    "predeterminado",
                    "actualizado_en",
                ]
            )

    messages.success(
        request,
        (
            f"Archivo {'activado' if registro.activo else 'desactivado'}."
        ),
    )

    return redirect(
        "productos:detalle",
        producto_id=producto_id,
    )


@require_POST
@transaction.atomic
def eliminar(
    request,
    producto_id,
    archivo_id,
):
    registro = get_object_or_404(
        ArchivoImpresion.objects
        .select_for_update(),
        id=archivo_id,
        producto_id=producto_id,
    )

    era_predeterminado = (
        registro.predeterminado
    )
    nombre = registro.nombre
    storage = registro.archivo.storage
    path = registro.archivo.name

    registro.delete()

    if path:
        try:
            storage.delete(path)
        except OSError:
            pass

    if era_predeterminado:
        siguiente = (
            ArchivoImpresion.objects
            .filter(
                producto_id=producto_id,
                activo=True,
            )
            .order_by(
                "-actualizado_en",
                "-id",
            )
            .first()
        )

        if siguiente:
            siguiente.predeterminado = True
            siguiente.save(
                update_fields=[
                    "predeterminado",
                    "actualizado_en",
                ]
            )

    messages.success(
        request,
        f"Archivo “{nombre}” eliminado.",
    )

    return redirect(
        "productos:detalle",
        producto_id=producto_id,
    )
