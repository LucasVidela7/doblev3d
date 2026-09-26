import hashlib
import logging
import math
import re
import zipfile
from decimal import Decimal
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_POST

from .models import ArchivoImpresion, Producto


logger = logging.getLogger(__name__)


PLATE_RE = re.compile(
    r"(?:^|/)plate_(\d+)\.gcode$",
    re.IGNORECASE,
)


WEIGHT_RE = re.compile(
    r"total\s+filament\s+weight\s*\[g\]\s*:\s*([0-9]+(?:\.[0-9]+)?)",
    re.IGNORECASE,
)

TOTAL_TIME_RE = re.compile(
    r"total\s+estimated\s+time\s*:\s*"
    r"(?:(\d+)h\s*)?"
    r"(?:(\d+)m\s*)?"
    r"(?:(\d+)s)?",
    re.IGNORECASE,
)


def _metadata_gcode_texto(texto):
    peso = None
    minutos = None

    peso_match = WEIGHT_RE.search(
        texto
    )
    if peso_match:
        try:
            peso = Decimal(
                peso_match.group(1)
            ).quantize(
                Decimal("0.01")
            )
        except Exception:
            peso = None

    tiempo_match = TOTAL_TIME_RE.search(
        texto
    )
    if tiempo_match:
        horas = int(
            tiempo_match.group(1)
            or 0
        )
        mins = int(
            tiempo_match.group(2)
            or 0
        )
        segundos = int(
            tiempo_match.group(3)
            or 0
        )
        total_segundos = (
            horas * 3600
            + mins * 60
            + segundos
        )
        if total_segundos > 0:
            minutos = max(
                1,
                math.ceil(
                    total_segundos / 60
                ),
            )

    return {
        "peso_estimado_gramos": peso,
        "tiempo_estimado_minutos": minutos,
    }


def _nombre_base(nombre):
    texto = str(nombre or "").strip()
    lower = texto.lower()
    sufijo = ".gcode.3mf"

    if lower.endswith(sufijo):
        texto = texto[: -len(sufijo)]

    return texto.strip()[:180]


def _cantidad(valor):
    try:
        cantidad = int(valor)
    except (TypeError, ValueError):
        return None

    return cantidad if cantidad > 0 else None


def _desmarcar_predeterminado(
    *,
    producto_id,
    cantidad_unidades,
    excluir_id=None,
):
    qs = ArchivoImpresion.objects.filter(
        producto_id=producto_id,
        cantidad_unidades=cantidad_unidades,
        predeterminado=True,
    )

    if excluir_id:
        qs = qs.exclude(id=excluir_id)

    qs.update(predeterminado=False)


def _sincronizar_pendientes_gcode(
    *,
    producto_id,
    cantidad_unidades,
    archivo=None,
):
    from produccion.models import Produccion

    return (
        Produccion.objects
        .filter(
            producto_id=producto_id,
            cantidad=cantidad_unidades,
            estado="PENDIENTE",
        )
        .update(
            archivo_impresion=archivo
        )
    )


def _archivo_fisico_disponible(
    registro,
):
    nombre = str(
        getattr(
            registro.archivo,
            "name",
            "",
        )
        or ""
    ).strip()

    if not nombre:
        return False

    try:
        return registro.archivo.storage.exists(
            nombre
        )
    except OSError:
        return False


def _guardar_archivo_impresion(
    registro,
    archivo,
):
    raiz = Path(
        getattr(
            settings,
            "PRINT_FILES_ROOT",
            settings.MEDIA_ROOT,
        )
    )

    nombre_guardado = ""

    try:
        raiz.mkdir(
            parents=True,
            exist_ok=True,
        )

        registro.archivo.save(
            str(archivo.name),
            archivo,
            save=False,
        )

        nombre_guardado = (
            registro.archivo.name
            or ""
        )

        registro.save()

    except Exception as error:
        logger.exception(
            "Error guardando G-code. producto_id=%s nombre=%s root=%s",
            getattr(
                registro,
                "producto_id",
                None,
            ),
            getattr(
                archivo,
                "name",
                "",
            ),
            raiz,
        )

        if nombre_guardado:
            try:
                registro.archivo.storage.delete(
                    nombre_guardado
                )
            except Exception:
                logger.exception(
                    "No se pudo limpiar archivo parcial %s",
                    nombre_guardado,
                )

        raise ValueError(
            "No se pudo guardar el archivo de impresión. "
            "Reintentá en unos segundos."
        ) from error


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

            metadata_gcode = {
                "peso_estimado_gramos": None,
                "tiempo_estimado_minutos": None,
            }

            if len(gcodes) == 1:
                try:
                    texto_gcode = paquete.read(
                        gcodes[0]
                    ).decode(
                        "utf-8",
                        errors="ignore",
                    )
                    metadata_gcode = (
                        _metadata_gcode_texto(
                            texto_gcode
                        )
                    )
                except Exception:
                    metadata_gcode = {
                        "peso_estimado_gramos": None,
                        "tiempo_estimado_minutos": None,
                    }

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
        "peso_estimado_gramos": (
            metadata_gcode.get(
                "peso_estimado_gramos"
            )
        ),
        "tiempo_estimado_minutos": (
            metadata_gcode.get(
                "tiempo_estimado_minutos"
            )
        ),
    }


@require_POST
@transaction.atomic
def subir(request, producto_id):
    producto = get_object_or_404(
        Producto,
        id=producto_id,
    )

    cantidad_unidades = _cantidad(
        request.POST.get(
            "cantidad_unidades"
        )
    )

    if not cantidad_unidades:
        messages.error(
            request,
            "Ingresá una cantidad de unidades válida.",
        )
        return redirect(
            "productos:detalle",
            producto_id=producto.id,
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
        .select_for_update()
        .filter(
            producto=producto,
            sha256=analisis["sha256"],
        )
        .first()
    )

    principal_existente = (
        ArchivoImpresion.objects
        .select_for_update()
        .filter(
            producto=producto,
            cantidad_unidades=cantidad_unidades,
            activo=True,
            predeterminado=True,
        )
        .first()
    )

    reemplazo_confirmado = (
        request.POST.get(
            "confirmar_reemplazo_principal",
            ""
        )
        == "1"
    )

    if duplicado:
        if (
            duplicado.cantidad_unidades
            != cantidad_unidades
        ):
            messages.error(
                request,
                (
                    "Ese mismo archivo ya está asociado a "
                    f"{duplicado.cantidad_unidades} unidad(es). "
                    "No se puede reutilizar para una cantidad distinta."
                ),
            )
            return redirect(
                "productos:detalle",
                producto_id=producto.id,
            )

        if (
            principal_existente
            and principal_existente.id != duplicado.id
            and not reemplazo_confirmado
        ):
            messages.warning(
                request,
                (
                    f"Ya existe un G-code principal para "
                    f"{cantidad_unidades} unidad(es): "
                    f"“{principal_existente.nombre}”. "
                    "Confirmá el reemplazo antes de continuar."
                ),
            )
            return redirect(
                "productos:detalle",
                producto_id=producto.id,
            )

        _desmarcar_predeterminado(
            producto_id=producto.id,
            cantidad_unidades=cantidad_unidades,
            excluir_id=duplicado.id,
        )

        if not _archivo_fisico_disponible(
            duplicado
        ):
            try:
                _guardar_archivo_impresion(
                    duplicado,
                    archivo,
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

            duplicado.activo = True
            duplicado.predeterminado = True
            duplicado.save(
                update_fields=[
                    "activo",
                    "predeterminado",
                    "actualizado_en",
                ]
            )

            _sincronizar_pendientes_gcode(
                producto_id=producto.id,
                cantidad_unidades=cantidad_unidades,
                archivo=duplicado,
            )

            messages.success(
                request,
                (
                    f"Se reparó “{duplicado.nombre_original}”. "
                    "El registro existía, pero faltaba el archivo físico."
                ),
            )
            return redirect(
                "productos:detalle",
                producto_id=producto.id,
            )

        if (
            not duplicado.activo
            or not duplicado.predeterminado
        ):
            duplicado.activo = True
            duplicado.predeterminado = True
            duplicado.save(
                update_fields=[
                    "activo",
                    "predeterminado",
                    "actualizado_en",
                ]
            )

        _sincronizar_pendientes_gcode(
            producto_id=producto.id,
            cantidad_unidades=cantidad_unidades,
            archivo=duplicado,
        )

        messages.info(
            request,
            (
                f"“{duplicado.nombre_original}” ya está cargado "
                "y disponible. No fue necesario subirlo otra vez."
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

    if (
        principal_existente
        and not reemplazo_confirmado
    ):
        messages.warning(
            request,
            (
                f"Ya existe un G-code principal para "
                f"{cantidad_unidades} unidad(es): "
                f"“{principal_existente.nombre}”. "
                "Confirmá el reemplazo antes de continuar."
            ),
        )
        return redirect(
            "productos:detalle",
            producto_id=producto.id,
        )

    _desmarcar_predeterminado(
        producto_id=producto.id,
        cantidad_unidades=cantidad_unidades,
    )

    predeterminado = True

    registro = ArchivoImpresion(
        producto=producto,
        nombre=nombre,
        version=version,
        cantidad_unidades=cantidad_unidades,
        nombre_original=str(
            archivo.name
        )[:255],
        tamano_bytes=analisis[
            "tamano_bytes"
        ],
        sha256=analisis["sha256"],
        placas=analisis["placas"],
        perfil_impresora=perfil_impresora,
        peso_estimado_gramos=analisis[
            "peso_estimado_gramos"
        ],
        tiempo_estimado_minutos=analisis[
            "tiempo_estimado_minutos"
        ],
        notas=notas,
        activo=True,
        predeterminado=predeterminado,
    )

    try:
        _guardar_archivo_impresion(
            registro,
            archivo,
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

    from produccion.models import Produccion

    _sincronizar_pendientes_gcode(
        producto_id=producto.id,
        cantidad_unidades=cantidad_unidades,
        archivo=registro,
    )

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
            f"Archivo “{registro.nombre}” cargado para "
            f"{registro.cantidad_unidades} unidad(es). "
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


def completar_metadata_gcode(
    registro,
):
    if (
        registro is None
        or (
            registro.peso_estimado_gramos
            is not None
            and registro.tiempo_estimado_minutos
            is not None
        )
    ):
        return False

    try:
        registro.archivo.open(
            "rb"
        )
        analisis = _analizar_gcode_3mf(
            registro.archivo
        )
    except Exception:
        logger.exception(
            "No se pudo completar metadata G-code. archivo_id=%s",
            getattr(
                registro,
                "id",
                None,
            ),
        )
        return False
    finally:
        try:
            registro.archivo.close()
        except Exception:
            pass

    campos = []

    if (
        registro.peso_estimado_gramos
        is None
        and analisis.get(
            "peso_estimado_gramos"
        )
        is not None
    ):
        registro.peso_estimado_gramos = (
            analisis[
                "peso_estimado_gramos"
            ]
        )
        campos.append(
            "peso_estimado_gramos"
        )

    if (
        registro.tiempo_estimado_minutos
        is None
        and analisis.get(
            "tiempo_estimado_minutos"
        )
        is not None
    ):
        registro.tiempo_estimado_minutos = (
            analisis[
                "tiempo_estimado_minutos"
            ]
        )
        campos.append(
            "tiempo_estimado_minutos"
        )

    if campos:
        campos.append(
            "actualizado_en"
        )
        registro.save(
            update_fields=campos
        )
        return True

    return False


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

    _desmarcar_predeterminado(
        producto_id=producto_id,
        cantidad_unidades=registro.cantidad_unidades,
        excluir_id=registro.id,
    )

    if not registro.predeterminado:
        registro.predeterminado = True
        registro.save(
            update_fields=[
                "predeterminado",
                "actualizado_en",
            ]
        )

    _sincronizar_pendientes_gcode(
        producto_id=producto_id,
        cantidad_unidades=registro.cantidad_unidades,
        archivo=registro,
    )

    messages.success(
        request,
        (
            f"“{registro.nombre}” quedó asignado como "
            f"archivo principal para {registro.cantidad_unidades} unidad(es)."
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
                cantidad_unidades=registro.cantidad_unidades,
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

    principal = (
        ArchivoImpresion.objects
        .filter(
            producto_id=producto_id,
            cantidad_unidades=registro.cantidad_unidades,
            activo=True,
            predeterminado=True,
        )
        .first()
    )

    _sincronizar_pendientes_gcode(
        producto_id=producto_id,
        cantidad_unidades=registro.cantidad_unidades,
        archivo=principal,
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
def reemplazar(
    request,
    producto_id,
    archivo_id,
):
    anterior = get_object_or_404(
        ArchivoImpresion.objects
        .select_for_update()
        .select_related("producto"),
        id=archivo_id,
        producto_id=producto_id,
    )

    archivo = request.FILES.get("archivo")

    if archivo is None:
        messages.error(
            request,
            "Seleccioná el nuevo archivo .gcode.3mf.",
        )
        return redirect(
            "productos:detalle",
            producto_id=producto_id,
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
            producto_id=producto_id,
        )

    if analisis["sha256"] == anterior.sha256:
        messages.error(
            request,
            "El archivo nuevo es idéntico al actual.",
        )
        return redirect(
            "productos:detalle",
            producto_id=producto_id,
        )

    duplicado = (
        ArchivoImpresion.objects
        .filter(
            producto_id=producto_id,
            sha256=analisis["sha256"],
        )
        .exclude(id=anterior.id)
        .first()
    )

    if duplicado:
        messages.error(
            request,
            (
                "Ese archivo ya existe en la biblioteca como "
                f"“{duplicado.nombre}”."
            ),
        )
        return redirect(
            "productos:detalle",
            producto_id=producto_id,
        )

    version = (
        request.POST.get("version", "")
        .strip()[:60]
        or anterior.version
    )

    notas = (
        request.POST.get("notas", "")
        .strip()
        or anterior.notas
    )

    _desmarcar_predeterminado(
        producto_id=producto_id,
        cantidad_unidades=anterior.cantidad_unidades,
    )

    nuevo = ArchivoImpresion(
        producto=anterior.producto,
        nombre=anterior.nombre,
        version=version,
        cantidad_unidades=anterior.cantidad_unidades,
        reemplaza_a=anterior,
        nombre_original=str(
            archivo.name
        )[:255],
        tamano_bytes=analisis[
            "tamano_bytes"
        ],
        sha256=analisis["sha256"],
        placas=analisis["placas"],
        perfil_impresora=anterior.perfil_impresora,
        peso_estimado_gramos=analisis[
            "peso_estimado_gramos"
        ],
        tiempo_estimado_minutos=analisis[
            "tiempo_estimado_minutos"
        ],
        notas=notas,
        activo=True,
        predeterminado=True,
    )

    try:
        _guardar_archivo_impresion(
            nuevo,
            archivo,
        )
    except ValueError as error:
        messages.error(
            request,
            str(error),
        )
        return redirect(
            "productos:detalle",
            producto_id=producto_id,
        )

    # Las planificaciones que todavía no empezaron deben usar la versión
    # nueva. Las impresiones en curso y el historial conservan el archivo
    # exacto con el que fueron ejecutadas.
    from produccion.models import Produccion

    _sincronizar_pendientes_gcode(
        producto_id=producto_id,
        cantidad_unidades=nuevo.cantidad_unidades,
        archivo=nuevo,
    )

    anterior.activo = False
    anterior.predeterminado = False
    anterior.save(
        update_fields=[
            "activo",
            "predeterminado",
            "actualizado_en",
        ]
    )

    messages.success(
        request,
        (
            f"Archivo para {nuevo.cantidad_unidades} unidad(es) "
            f"sustituido por “{nuevo.nombre_original}”. "
            "La versión anterior quedó guardada en el historial."
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
    cantidad_unidades = registro.cantidad_unidades
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
                cantidad_unidades=cantidad_unidades,
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
    else:
        siguiente = (
            ArchivoImpresion.objects
            .filter(
                producto_id=producto_id,
                cantidad_unidades=cantidad_unidades,
                activo=True,
                predeterminado=True,
            )
            .first()
        )

    _sincronizar_pendientes_gcode(
        producto_id=producto_id,
        cantidad_unidades=cantidad_unidades,
        archivo=siguiente,
    )

    messages.success(
        request,
        f"Archivo “{nombre}” eliminado.",
    )

    return redirect(
        "productos:detalle",
        producto_id=producto_id,
    )
