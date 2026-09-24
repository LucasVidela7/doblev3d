import os
import re


QA_ALIASES = {"qa", "test", "testing", "staging"}
PRODUCTION_ALIASES = {"prod", "production"}


def _env_bool(nombre, default=False):
    valor = os.getenv(nombre, "true" if default else "false").strip().lower()
    return valor in {"1", "true", "yes", "on"}


def entorno_imagenes():
    """Nombre estable del ambiente usado para aislar imágenes externas."""
    valor = (
        os.getenv("APP_ENV", "").strip().lower()
        or os.getenv("RAILWAY_ENVIRONMENT_NAME", "").strip().lower()
        or "local"
    )

    if valor in QA_ALIASES:
        return "qa"
    if valor in PRODUCTION_ALIASES:
        return "production"

    valor = re.sub(r"[^a-z0-9_-]+", "-", valor).strip("-_")
    return valor or "local"


def ambientes_imagenes_lectura():
    """Ambientes permitidos para mostrar imágenes sin cambiar el destino de escritura."""
    actual = entorno_imagenes()
    if (
        actual == "qa"
        and _env_bool("IMAGEKIT_PRODUCTION_FALLBACK", False)
    ):
        return ("qa", "production")
    return (actual,)


def clave_imagen_lectura(imagen):
    """Prioriza la imagen propia del ambiente y usa producción sólo como fallback."""
    ambientes = ambientes_imagenes_lectura()
    try:
        prioridad = ambientes.index(getattr(imagen, "ambiente", ""))
    except ValueError:
        prioridad = len(ambientes)
    return (
        prioridad,
        int(getattr(imagen, "orden", 99) or 99),
        int(getattr(imagen, "id", 0) or 0),
    )
