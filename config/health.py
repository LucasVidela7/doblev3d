from django.db import connection
from django.http import JsonResponse


def healthcheck(request):
    """Healthcheck liviano para Railway: app + conexión a PostgreSQL."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        return JsonResponse(
            {"ok": False, "database": "error"},
            status=503,
        )

    return JsonResponse(
        {"ok": True, "database": "ok"},
        status=200,
    )
