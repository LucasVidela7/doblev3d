from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from .context import obtener_contexto
from .models import RegistroAuditoria


APPS_AUDITADAS = {
    "clientes",
    "pedidos",
    "productos",
    "produccion",
    "costos",
    "kits",
    "stock",
}

CAMPOS_IGNORADOS = {
    "creado_en",
    "actualizado_en",
    "updated_at",
    "created_at",
}


def _debe_auditar(sender):
    meta = getattr(sender, "_meta", None)
    return bool(meta and meta.app_label in APPS_AUDITADAS)


def _valor_serializable(valor):
    if hasattr(valor, "isoformat"):
        return valor.isoformat()
    return valor


def _snapshot(instancia):
    datos = {}
    for campo in instancia._meta.concrete_fields:
        if campo.name in CAMPOS_IGNORADOS:
            continue
        valor = getattr(instancia, campo.attname)
        datos[campo.name] = _valor_serializable(valor)
    return datos


def _cambios(antes, despues):
    resultado = {}
    for campo in sorted(set(antes) | set(despues)):
        valor_antes = antes.get(campo)
        valor_despues = despues.get(campo)
        if valor_antes != valor_despues:
            resultado[campo] = {
                "antes": valor_antes,
                "despues": valor_despues,
            }
    return resultado


def _accion_para(sender, created, cambios, eliminando=False):
    if eliminando:
        return "ELIMINAR"

    etiqueta = sender._meta.label_lower

    if created and etiqueta == "pedidos.pago":
        return "REGISTRAR_PAGO"

    if etiqueta == "pedidos.pedido" and "estado" in cambios:
        estado_nuevo = cambios["estado"]["despues"]
        if estado_nuevo == "ENTREGADO":
            return "ENTREGAR_PEDIDO"
        if estado_nuevo == "CANCELADO":
            return "CANCELAR_PEDIDO"
        return "CAMBIAR_ESTADO_PEDIDO"

    if etiqueta == "produccion.produccion" and "estado" in cambios:
        return "CAMBIAR_ESTADO_PRODUCCION"

    return "CREAR" if created else "MODIFICAR"


def _crear_registro(sender, instancia, accion, cambios):
    contexto = obtener_contexto()
    usuario = contexto["usuario"]

    try:
        representacion = str(instancia)
    except Exception:
        representacion = f"{sender._meta.verbose_name} #{instancia.pk}"

    RegistroAuditoria.objects.create(
        usuario=usuario,
        usuario_nombre=(
            usuario.get_username()
            if usuario is not None and getattr(usuario, "is_authenticated", False)
            else ""
        ),
        accion=accion,
        app_label=sender._meta.app_label,
        modelo=sender._meta.model_name,
        objeto_id=str(instancia.pk or ""),
        objeto_representacion=representacion[:255],
        cambios=cambios,
        ruta=contexto["ruta"],
        metodo=contexto["metodo"],
        ip=contexto["ip"],
    )


@receiver(pre_save)
def capturar_estado_anterior(sender, instance, **kwargs):
    if not _debe_auditar(sender) or instance.pk is None:
        return

    anterior = sender._default_manager.filter(pk=instance.pk).first()
    instance._auditoria_estado_anterior = _snapshot(anterior) if anterior else {}


@receiver(post_save)
def registrar_guardado(sender, instance, created, raw=False, **kwargs):
    if raw or not _debe_auditar(sender):
        return

    despues = _snapshot(instance)

    if created:
        antes = {campo: None for campo in despues}
    else:
        antes = getattr(instance, "_auditoria_estado_anterior", {})

    cambios = _cambios(antes, despues)

    # Un save() sin modificaciones reales no genera ruido en el historial.
    if not created and not cambios:
        return

    accion = _accion_para(sender, created, cambios)
    _crear_registro(sender, instance, accion, cambios)


@receiver(pre_delete)
def registrar_eliminacion(sender, instance, **kwargs):
    if not _debe_auditar(sender):
        return

    antes = _snapshot(instance)
    cambios = {
        campo: {"antes": valor, "despues": None}
        for campo, valor in antes.items()
    }
    _crear_registro(
        sender,
        instance,
        _accion_para(sender, False, cambios, eliminando=True),
        cambios,
    )
