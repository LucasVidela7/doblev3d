from contextlib import contextmanager
from contextvars import ContextVar


_usuario_actual = ContextVar("auditoria_usuario", default=None)
_ruta_actual = ContextVar("auditoria_ruta", default="")
_metodo_actual = ContextVar("auditoria_metodo", default="")
_ip_actual = ContextVar("auditoria_ip", default=None)


def obtener_contexto():
    return {
        "usuario": _usuario_actual.get(),
        "ruta": _ruta_actual.get(),
        "metodo": _metodo_actual.get(),
        "ip": _ip_actual.get(),
    }


@contextmanager
def contexto_auditoria(usuario=None, ruta="", metodo="", ip=None):
    tokens = (
        _usuario_actual.set(usuario),
        _ruta_actual.set(ruta or ""),
        _metodo_actual.set(metodo or ""),
        _ip_actual.set(ip),
    )

    try:
        yield
    finally:
        _usuario_actual.reset(tokens[0])
        _ruta_actual.reset(tokens[1])
        _metodo_actual.reset(tokens[2])
        _ip_actual.reset(tokens[3])
