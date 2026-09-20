import re


def normalizar_telefono(valor):
    """
    Devuelve una clave comparable para teléfonos argentinos.

    Acepta formatos habituales como:
    - 11 6476-0709
    - +54 11 6476-0709
    - +54 9 11 6476-0709
    """
    digitos = re.sub(r"\D+", "", str(valor or ""))
    if not digitos:
        return ""

    if digitos.startswith("00"):
        digitos = digitos[2:]

    if digitos.startswith("54"):
        digitos = digitos[2:]
        if digitos.startswith("9") and len(digitos) >= 11:
            digitos = digitos[1:]

    if digitos.startswith("0") and len(digitos) > 10:
        digitos = digitos[1:]

    return digitos


def buscar_cliente_por_telefono(telefono, excluir_id=None):
    from .models import Cliente

    clave = normalizar_telefono(telefono)
    if not clave:
        return None

    queryset = Cliente.objects.filter(
        activo=True,
    ).exclude(telefono="")
    if excluir_id:
        queryset = queryset.exclude(id=excluir_id)

    for cliente in queryset.only("id", "nombre", "telefono", "activo"):
        if normalizar_telefono(cliente.telefono) == clave:
            return cliente

    return None
