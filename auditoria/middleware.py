from .context import contexto_auditoria


class AuditoriaRequestMiddleware:
    """Expone usuario y datos básicos del request a las señales de auditoría."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = request.user if getattr(request.user, "is_authenticated", False) else None

        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = forwarded_for.split(",")[0].strip() if forwarded_for else request.META.get("REMOTE_ADDR")

        with contexto_auditoria(
            usuario=usuario,
            ruta=request.path[:500],
            metodo=request.method[:10],
            ip=ip,
        ):
            return self.get_response(request)
