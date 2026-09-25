import re
from collections import defaultdict
from datetime import datetime

from django.contrib import messages
from django.db.models import Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from productos.models import Producto
from produccion.models import Produccion
from produccion.views import obtener_tiempo_recomendado

from .models import DetallePedido, Pedido


MARCA_PERSONALIZADO = "PERSONALIZADO:"


def _nuevo_item(producto, es_pieza=False):
    return {
        "producto": producto,
        "cantidad_pedida": 0,
        "cantidad_normal": 0,
        "cantidad_personalizada": 0,
        "necesidad_normal_impresion": 0,
        "stock": 0,
        "a_imprimir": 0,
        "planificadas": 0,
        "en_produccion": 0,
        "en_control": 0,
        "falta_iniciar": 0,
        "falta_normal_planificar": 0,
        "impresoras": [],
        "es_pieza": es_pieza,
        "origenes": set(),
        "personalizaciones": [],
    }


def _copiar_personalizaciones(personalizaciones, multiplicador=1):
    resultado = []

    for personalizacion in personalizaciones or []:
        copia = dict(personalizacion)
        copia["cantidad"] = (
            int(personalizacion.get("cantidad") or 0)
            * int(multiplicador or 1)
        )
        resultado.append(copia)

    return resultado


def _agregar_fabricacion(
    agrupados,
    producto,
    cantidad_normal,
    cantidad_personalizada,
    origen=None,
    personalizaciones=None,
):
    """
    Convierte demanda comercial en unidades físicas a imprimir.

    - SIMPLE: se imprime el mismo producto.
    - COMPUESTO: se expande a sus piezas x cantidad.

    El stock del producto terminado se descuenta antes de entrar acá.
    Las personalizaciones viajan con la unidad física para que nunca se
    mezclen silenciosamente con una planificación estándar.
    """
    cantidad_normal = max(int(cantidad_normal or 0), 0)
    cantidad_personalizada = max(int(cantidad_personalizada or 0), 0)

    if cantidad_normal <= 0 and cantidad_personalizada <= 0:
        return

    if producto.tipo_fabricacion == "COMPUESTO":
        for relacion in producto.componentes.select_related("componente").all():
            pieza = relacion.componente
            multiplicador = int(relacion.cantidad or 0)

            if multiplicador <= 0 or not pieza.requiere_impresion:
                continue

            item = agrupados.get(pieza.id)
            if item is None:
                item = _nuevo_item(pieza, es_pieza=True)
                agrupados[pieza.id] = item

            normal_piezas = cantidad_normal * multiplicador
            personalizadas_piezas = cantidad_personalizada * multiplicador

            item["cantidad_normal"] += normal_piezas
            item["necesidad_normal_impresion"] += normal_piezas
            item["cantidad_personalizada"] += personalizadas_piezas
            item["cantidad_pedida"] += normal_piezas + personalizadas_piezas
            item["a_imprimir"] += normal_piezas + personalizadas_piezas
            item["personalizaciones"].extend(
                _copiar_personalizaciones(
                    personalizaciones,
                    multiplicador=multiplicador,
                )
            )

            if origen:
                item["origenes"].add(origen)

        return

    item = agrupados.get(producto.id)
    if item is None:
        item = _nuevo_item(producto, es_pieza=False)
        agrupados[producto.id] = item

    item["cantidad_normal"] += cantidad_normal
    item["necesidad_normal_impresion"] += cantidad_normal
    item["cantidad_personalizada"] += cantidad_personalizada
    item["cantidad_pedida"] += cantidad_normal + cantidad_personalizada
    item["a_imprimir"] += cantidad_normal + cantidad_personalizada
    item["personalizaciones"].extend(
        _copiar_personalizaciones(personalizaciones)
    )

    if origen:
        item["origenes"].add(origen)


def _detalle_personalizacion(detalle):
    return {
        "detalle_id": detalle.id,
        "pedido_id": detalle.pedido_id,
        "pedido_codigo": detalle.pedido.codigo,
        "cantidad": int(detalle.cantidad or 0),
        "detalle": detalle.detalle_personalizacion or "",
        "color": detalle.color_personalizacion or "",
        "producto_origen": detalle.producto.nombre if detalle.producto else "",
    }


def _producciones_activas_por_producto():
    producciones = (
        Produccion.objects
        .filter(estado__in=["PENDIENTE", "IMPRIMIENDO", "CONTROL"])
        .select_related("producto", "impresora")
        .order_by("producto_id", "id")
    )

    por_producto = defaultdict(
        lambda: {
            "planificadas": 0,
            "imprimiendo": 0,
            "control": 0,
            "planificadas_estandar": 0,
            "imprimiendo_estandar": 0,
            "control_estandar": 0,
            "impresoras": [],
        }
    )
    personalizados = defaultdict(
        lambda: {
            "planificadas": 0,
            "imprimiendo": 0,
            "control": 0,
        }
    )

    for produccion in producciones:
        datos = por_producto[produccion.producto_id]
        cantidad = int(produccion.cantidad or 0)

        if produccion.estado == "PENDIENTE":
            datos["planificadas"] += cantidad
        elif produccion.estado == "CONTROL":
            datos["control"] += cantidad
        else:
            datos["imprimiendo"] += cantidad
            if produccion.impresora:
                datos["impresoras"].append(
                    f"{produccion.impresora.nombre} · {cantidad}"
                )

        coincidencia = re.search(
            r"PERSONALIZADO:(\d+)",
            produccion.observaciones or "",
        )

        if coincidencia:
            detalle_id = int(coincidencia.group(1))
            clave = (produccion.producto_id, detalle_id)
            if produccion.estado == "PENDIENTE":
                personalizados[clave]["planificadas"] += cantidad
            elif produccion.estado == "CONTROL":
                personalizados[clave]["control"] += cantidad
            else:
                personalizados[clave]["imprimiendo"] += cantidad
            continue

        if produccion.estado == "PENDIENTE":
            datos["planificadas_estandar"] += cantidad
        elif produccion.estado == "CONTROL":
            datos["control_estandar"] += cantidad
        else:
            datos["imprimiendo_estandar"] += cantidad

    return por_producto, personalizados


def obtener_impresiones_por_producto():
    """Devuelve la necesidad física, planes pendientes y trabajos activos."""
    pedidos = (
        Pedido.objects
        .exclude(estado__in=["ENTREGADO", "CANCELADO"])
        .prefetch_related(
            "detalles__producto__componentes__componente",
            "detalles__kit",
            "detalles__productos_kit__producto__componentes__componente",
            "estados_impresion",
        )
        .order_by("fecha_entrega", "id")
    )

    demanda_comercial = defaultdict(
        lambda: {
            "producto": None,
            "cantidad_normal": 0,
            "cantidad_personalizada": 0,
            "personalizaciones": [],
        }
    )
    reservas_normales = defaultdict(int)

    for pedido in pedidos:
        estados_pedido = list(pedido.estados_impresion.all())
        productos_normales_listos = {
            estado.producto_id
            for estado in estados_pedido
            if estado.listo
        }

        # Al iniciar Preparación, el stock reservado ya se descuenta de
        # Producto.stock. Esa misma cantidad debe salir también de la demanda
        # pendiente; de lo contrario se compara demanda completa contra un
        # stock ya reducido y aparece un faltante ficticio.
        for estado in estados_pedido:
            if estado.listo or not estado.reservado_stock:
                continue
            reservas_normales[estado.producto_id] += max(
                int(estado.cantidad_stock_reservada or 0),
                0,
            )

        for detalle in pedido.detalles.all():
            if detalle.estado in ["CANCELADO", "ENTREGADO"]:
                continue

            if (
                detalle.tipo_item == "PERSONALIZADO"
                and detalle.producto
                and detalle.producto.requiere_impresion
            ):
                if detalle.estado == "LISTO":
                    continue

                item = demanda_comercial[detalle.producto_id]
                item["producto"] = detalle.producto
                item["cantidad_personalizada"] += detalle.cantidad
                item["personalizaciones"].append(
                    _detalle_personalizacion(detalle)
                )
                continue

            if (
                detalle.tipo_item == "PRODUCTO"
                and detalle.producto
                and detalle.producto.requiere_impresion
            ):
                if detalle.producto_id in productos_normales_listos:
                    continue

                item = demanda_comercial[detalle.producto_id]
                item["producto"] = detalle.producto
                item["cantidad_normal"] += detalle.cantidad
                continue

            if detalle.tipo_item == "KIT" and detalle.kit:
                for componente_kit in detalle.productos_kit.all():
                    producto = componente_kit.producto

                    if not producto.requiere_impresion:
                        continue

                    if producto.id in productos_normales_listos:
                        continue

                    item = demanda_comercial[producto.id]
                    item["producto"] = producto
                    item["cantidad_normal"] += componente_kit.cantidad

    productos_agrupados = {}

    for demanda in demanda_comercial.values():
        producto = demanda["producto"]
        if not producto:
            continue

        cantidad_normal_total = max(int(demanda["cantidad_normal"] or 0), 0)
        cantidad_personalizada = demanda["cantidad_personalizada"]
        cantidad_reservada = min(
            max(int(reservas_normales.get(producto.id, 0)), 0),
            cantidad_normal_total,
        )
        cantidad_normal = max(
            cantidad_normal_total - cantidad_reservada,
            0,
        )
        falta_normal = max(cantidad_normal - int(producto.stock or 0), 0)

        _agregar_fabricacion(
            productos_agrupados,
            producto,
            falta_normal,
            cantidad_personalizada,
            origen=producto.nombre,
            personalizaciones=demanda["personalizaciones"],
        )

        if producto.tipo_fabricacion == "SIMPLE":
            item = productos_agrupados.get(producto.id)
            if item:
                # cantidad_pedida conserva la demanda comercial visible;
                # cantidad_normal representa sólo lo que todavía no está
                # cubierto por una reserva de Preparación.
                item["cantidad_pedida"] = (
                    cantidad_normal_total + cantidad_personalizada
                )
                item["cantidad_normal"] = cantidad_normal
                item["necesidad_normal_impresion"] = falta_normal
                item["stock"] = int(producto.stock or 0)
                item["a_imprimir"] = falta_normal + cantidad_personalizada

    activas_por_producto, activas_personalizadas = (
        _producciones_activas_por_producto()
    )

    lista_productos = []

    for item in productos_agrupados.values():
        producto = item["producto"]
        activas = activas_por_producto.get(
            producto.id,
            {
                "planificadas": 0,
                "imprimiendo": 0,
                "control": 0,
                "planificadas_estandar": 0,
                "imprimiendo_estandar": 0,
                "control_estandar": 0,
                "impresoras": [],
            },
        )

        item["planificadas"] = activas["planificadas"]
        item["en_produccion"] = activas["imprimiendo"]
        item["en_control"] = activas["control"]
        item["impresoras"] = activas["impresoras"]
        item["falta_iniciar"] = max(
            item["a_imprimir"]
            - item["planificadas"]
            - item["en_produccion"]
            - item["en_control"],
            0,
        )
        item["falta_normal_planificar"] = max(
            item["necesidad_normal_impresion"]
            - activas["planificadas_estandar"]
            - activas["imprimiendo_estandar"]
            - activas["control_estandar"],
            0,
        )
        item["origenes"] = sorted(item["origenes"])

        for personalizacion in item["personalizaciones"]:
            estado = activas_personalizadas.get(
                (producto.id, personalizacion["detalle_id"]),
                {
                    "planificadas": 0,
                    "imprimiendo": 0,
                    "control": 0,
                },
            )
            personalizacion["planificadas"] = estado["planificadas"]
            personalizacion["imprimiendo"] = estado["imprimiendo"]
            personalizacion["control"] = estado["control"]
            personalizacion["falta_planificar"] = max(
                personalizacion["cantidad"]
                - estado["planificadas"]
                - estado["imprimiendo"]
                - estado["control"],
                0,
            )

        falta_iniciar = item["falta_iniciar"]
        en_produccion = item["en_produccion"]
        planificadas = item["planificadas"]
        a_imprimir = item["a_imprimir"]

        if falta_iniciar >= 6:
            item["prioridad"] = "ALTA"
            item["prioridad_clase"] = "prioridad-alta"
        elif falta_iniciar >= 3:
            item["prioridad"] = "MEDIA"
            item["prioridad_clase"] = "prioridad-media"
        elif falta_iniciar >= 1:
            item["prioridad"] = "BAJA"
            item["prioridad_clase"] = "prioridad-baja"
        elif (
            en_produccion > 0
            or planificadas > 0
            or item["en_control"] > 0
        ) and a_imprimir > 0:
            item["prioridad"] = "EN CURSO"
            item["prioridad_clase"] = "prioridad-curso"
        else:
            item["prioridad"] = "SIN NECESIDAD"
            item["prioridad_clase"] = "prioridad-cero"

        lista_productos.append(item)

    lista_productos.sort(
        key=lambda item: (
            -item["falta_iniciar"],
            -item["en_produccion"],
            -item["planificadas"],
            0 if item["es_pieza"] else 1,
            item["producto"].nombre.lower(),
        )
    )

    return lista_productos


def impresiones_por_producto(request):
    return render(
        request,
        "pedidos/impresiones_por_producto.html",
        {"productos": obtener_impresiones_por_producto()},
    )


def _parsear_inicio(texto):
    if not texto:
        return None

    try:
        inicio = datetime.strptime(texto, "%Y-%m-%dT%H:%M")
    except ValueError:
        return None

    if timezone.is_naive(inicio):
        inicio = timezone.make_aware(
            inicio,
            timezone.get_current_timezone(),
        )

    return inicio


def _tiempo_manual(request):
    horas_texto = request.POST.get("horas", "").strip()
    minutos_texto = request.POST.get("minutos", "").strip()

    if horas_texto == "" and minutos_texto == "":
        return None

    try:
        horas = int(horas_texto or 0)
        minutos = int(minutos_texto or 0)
    except (TypeError, ValueError):
        return -1

    if horas < 0 or minutos < 0 or minutos > 59:
        return -1

    return horas * 60 + minutos


def _cantidad_personalizada_fisica(detalle, producto):
    if detalle.producto_id == producto.id:
        return int(detalle.cantidad or 0)

    relacion = (
        detalle.producto.componentes
        .filter(componente=producto)
        .first()
    )

    if not relacion:
        return 0

    return int(detalle.cantidad or 0) * int(relacion.cantidad or 0)


def _cantidad_personalizada_ya_planificada(detalle, producto):
    marca = f"{MARCA_PERSONALIZADO}{detalle.id}"
    return (
        Produccion.objects
        .filter(
            producto=producto,
            estado__in=["PENDIENTE", "IMPRIMIENDO", "CONTROL"],
            observaciones__contains=marca,
        )
        .aggregate(total=Sum("cantidad"))
        .get("total")
        or 0
    )


def planificar_impresion_producto(request):
    if request.method != "POST":
        return redirect("pedidos:impresiones_productos")

    producto = get_object_or_404(
        Producto,
        id=request.POST.get("producto"),
        activo=True,
        requiere_impresion=True,
    )

    try:
        cantidad = int(request.POST.get("cantidad", "0"))
    except (TypeError, ValueError):
        cantidad = 0

    if cantidad <= 0:
        messages.error(request, "Ingresá una cantidad mayor a cero para la placa.")
        return redirect("pedidos:impresiones_productos")

    inicio = _parsear_inicio(
        request.POST.get("inicio_impresion", "").strip()
    )
    if inicio is None:
        messages.error(request, "Ingresá un día y horario válido para la planificación.")
        return redirect("pedidos:impresiones_productos")

    if inicio < timezone.now():
        inicio = timezone.now()

    personalizado_id = request.POST.get("personalizado_id", "").strip()
    destino = "STOCK"
    pedido = None
    observaciones = "Planificada desde Impresiones por producto."

    if personalizado_id:
        detalle = get_object_or_404(
            DetallePedido.objects
            .select_related("pedido", "producto")
            .prefetch_related("producto__componentes"),
            id=personalizado_id,
            tipo_item="PERSONALIZADO",
            estado="PENDIENTE",
        )

        total_fisico = _cantidad_personalizada_fisica(detalle, producto)
        ya_planificado = _cantidad_personalizada_ya_planificada(
            detalle,
            producto,
        )
        restante = max(total_fisico - int(ya_planificado), 0)

        if total_fisico <= 0:
            messages.error(
                request,
                "Ese producto no corresponde a la personalización seleccionada.",
            )
            return redirect("pedidos:impresiones_productos")

        if cantidad > restante:
            messages.error(
                request,
                (
                    f"Para {detalle.pedido.codigo} quedan {restante} unidad(es) "
                    "personalizadas por planificar."
                ),
            )
            return redirect("pedidos:impresiones_productos")

        destino = "PEDIDO"
        pedido = detalle.pedido
        detalle_texto = detalle.detalle_personalizacion or "Sin detalle"
        color_texto = detalle.color_personalizacion or "Sin color especificado"
        observaciones = (
            f"{MARCA_PERSONALIZADO}{detalle.id}\n"
            f"{detalle.pedido.codigo} · {detalle.producto.nombre}\n"
            f"Detalle: {detalle_texto}\n"
            f"Color: {color_texto}"
        )

    else:
        item = next(
            (
                actual
                for actual in obtener_impresiones_por_producto()
                if actual["producto"].id == producto.id
            ),
            None,
        )
        restante = int(item["falta_normal_planificar"] if item else 0)

        if restante <= 0:
            messages.error(
                request,
                "No quedan unidades estándar de este producto por planificar.",
            )
            return redirect("pedidos:impresiones_productos")

        if cantidad > restante:
            messages.error(
                request,
                (
                    f"Quedan {restante} unidad(es) estándar por planificar. "
                    "Dividí la necesidad en las placas que realmente entren."
                ),
            )
            return redirect("pedidos:impresiones_productos")

    tiempo_total = _tiempo_manual(request)

    if tiempo_total == -1:
        messages.error(
            request,
            "La duración debe tener horas válidas y minutos entre 0 y 59.",
        )
        return redirect("pedidos:impresiones_productos")

    if not tiempo_total:
        tiempo_total = obtener_tiempo_recomendado(
            producto,
            cantidad,
        )

    if not tiempo_total:
        messages.error(
            request,
            (
                f"No hay un tiempo registrado para {producto.nombre} x{cantidad}. "
                "Ingresá la duración estimada de esa placa."
            ),
        )
        return redirect("pedidos:impresiones_productos")

    produccion = Produccion.objects.create(
        producto=producto,
        cantidad=cantidad,
        destino=destino,
        pedido=pedido,
        estado="PENDIENTE",
        impresora=None,
        inicio_impresion=inicio,
        tiempo_impresion_minutos=tiempo_total,
        observaciones=observaciones,
    )

    messages.success(
        request,
        (
            f"{produccion.codigo} planificada: {producto.nombre} x{cantidad}. "
            "La impresora se elige al momento de iniciar."
        ),
    )
    return redirect("pedidos:impresiones_productos")
