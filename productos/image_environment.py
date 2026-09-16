import os
import re


QA_ALIASES = {"qa", "test", "testing", "staging"}
PRODUCTION_ALIASES = {"prod", "production"}


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
