from .impresiones_compuestas import impresiones_por_producto as _impresiones_por_producto
from .personalizados_produccion import sincronizar_personalizados_pendientes


def impresiones_por_producto(request):
    """
    Antes de armar la necesidad productiva sincroniza personalizados antiguos
    que ya tienen todas sus producciones finalizadas.

    Así una producción LISTO no vuelve a aparecer como necesidad a planificar.
    """
    sincronizar_personalizados_pendientes()
    return _impresiones_por_producto(request)
