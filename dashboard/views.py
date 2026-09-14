from decimal import Decimal
from collections import defaultdict
from datetime import timedelta

from django.db.models import Sum
from django.shortcuts import render
from django.utils import timezone

from pedidos.models import Pedido, Pago
from produccion.models import Produccion
from productos.models import Producto


def inicio(request):
    hoy = timezone.localdate()
    fin_semana = hoy + timedelta(days=7)

    pedidos_activos_qs = (
        Pedido.objects
        .exclude(
            estado__in=[
                "ENTREGADO",
                "CANCELADO",
            ]
        )
    )

    pedidos_activos = pedidos_activos_qs.count()

    pedidos_pendientes = (
        pedidos_activos_qs
        .filter(estado="PENDIENTE")
        .count()
    )

    pedidos_preparando = (
        pedidos_activos_qs
        .filter(estado="PREPARANDO")
        .count()
    )

    pedidos_listos = (
        pedidos_activos_qs
        .filter(estado="LISTO")
        .count()
    )

    pedidos_hoy = (
        pedidos_activos_qs
        .filter(fecha_entrega=hoy)
        .count()
    )

    pedidos_atrasados = (
        pedidos_activos_qs
        .filter(fecha_entrega__lt=hoy)
        .count()
    )

    producciones_pendientes = (
        Produccion.objects
        .filter(estado="PENDIENTE")
        .count()
    )

    producciones_imprimiendo = (
        Produccion.objects
        .filter(estado="IMPRIMIENDO")
        .count()
    )

    unidades_en_produccion = (
        Produccion.objects
        .filter(
            estado__in=[
                "PENDIENTE",
                "IMPRIMIENDO",
            ]
        )
        .aggregate(total=Sum("cantidad"))
        .get("total")
        or 0
    )

    # Próximas entregas: primero atrasadas y luego las más cercanas.
    proximas_entregas = (
        pedidos_activos_qs
        .filter(
            fecha_entrega__isnull=False,
            fecha_entrega__lte=fin_semana,
        )
        .select_related("cliente")
        .order_by(
            "fecha_entrega",
            "id",
        )[:8]
    )

    # ==========================================================
    # NECESIDAD DE IMPRESIÓN
    # ==========================================================
    #
    # Se calcula con la misma idea operativa de
    # "Impresiones por producto":
    #
    # - Producto / Kit: el stock puede cubrir demanda.
    # - Personalizado: siempre debe fabricarse para ese pedido.
    # - Si un producto normal ya fue marcado LISTO para un pedido,
    #   no vuelve a contarse.
    # - Si un personalizado está LISTO, tampoco vuelve a contarse.
    # ==========================================================

    pedidos_para_impresion = (
        pedidos_activos_qs
        .prefetch_related(
            "detalles__producto",
            "detalles__kit",
            "detalles__productos_kit__producto",
            "estados_impresion",
        )
        .order_by(
            "fecha_entrega",
            "id",
        )
    )

    demanda = defaultdict(
        lambda: {
            "producto": None,
            "normal": 0,
            "personalizada": 0,
        }
    )

    for pedido in pedidos_para_impresion:
        productos_normales_listos = {
            estado.producto_id
            for estado in pedido.estados_impresion.all()
            if estado.listo
        }

        for detalle in pedido.detalles.all():
            if detalle.estado in [
                "CANCELADO",
                "ENTREGADO",
            ]:
                continue

            if (
                detalle.tipo_item == "PERSONALIZADO"
                and detalle.producto
                and detalle.producto.requiere_impresion
            ):
                if detalle.estado == "LISTO":
                    continue

                item = demanda[detalle.producto_id]
                item["producto"] = detalle.producto
                item["personalizada"] += detalle.cantidad
                continue

            if (
                detalle.tipo_item == "PRODUCTO"
                and detalle.producto
                and detalle.producto.requiere_impresion
            ):
                if detalle.producto_id in productos_normales_listos:
                    continue

                item = demanda[detalle.producto_id]
                item["producto"] = detalle.producto
                item["normal"] += detalle.cantidad

            elif (
                detalle.tipo_item == "KIT"
                and detalle.kit
            ):
                for componente in detalle.productos_kit.all():
                    producto = componente.producto

                    if not producto.requiere_impresion:
                        continue

                    if producto.id in productos_normales_listos:
                        continue

                    item = demanda[producto.id]
                    item["producto"] = producto
                    item["normal"] += componente.cantidad

    necesidad_impresion = []

    for item in demanda.values():
        producto = item["producto"]

        falta_normal = max(
            item["normal"] - producto.stock,
            0,
        )

        a_imprimir = (
            falta_normal
            + item["personalizada"]
        )

        if a_imprimir <= 0:
            continue

        necesidad_impresion.append(
            {
                "producto": producto,
                "cantidad": a_imprimir,
                "personalizada": item["personalizada"],
            }
        )

    necesidad_impresion.sort(
        key=lambda item: (
            -item["cantidad"],
            item["producto"].nombre.lower(),
        )
    )

    total_a_imprimir = sum(
        item["cantidad"]
        for item in necesidad_impresion
    )

    top_impresion = necesidad_impresion[:6]

    max_impresion = max(
        (
            item["cantidad"]
            for item in top_impresion
        ),
        default=1,
    )

    for item in top_impresion:
        item["porcentaje"] = round(
            item["cantidad"]
            * 100
            / max_impresion
        )

    # Productos activos sin stock. Es una alerta simple y útil;
    # no supone un "stock mínimo" porque ese campo aún no existe.
    productos_sin_stock = (
        Producto.objects
        .filter(
            activo=True,
            stock__lte=0,
        )
        .count()
    )


    # ==========================================================
    # PAGOS
    # ==========================================================

    inicio_mes = hoy.replace(day=1)

    saldo_a_cobrar = Decimal("0")

    pedidos_con_saldo_qs = (
        Pedido.objects
        .exclude(estado="CANCELADO")
        .prefetch_related(
            "detalles",
            "pagos",
        )
    )

    pedidos_con_saldo = 0

    for pedido in pedidos_con_saldo_qs:
        saldo = pedido.saldo_pendiente

        if saldo > 0:
            saldo_a_cobrar += saldo
            pedidos_con_saldo += 1

    cobrado_mes = (
        Pago.objects
        .filter(
            fecha__date__gte=inicio_mes,
        )
        .aggregate(total=Sum("monto"))
        .get("total")
        or Decimal("0")
    )

    return render(
        request,
        "dashboard/inicio.html",
        {
            "hoy": hoy,
            "pedidos_activos": pedidos_activos,
            "pedidos_pendientes": pedidos_pendientes,
            "pedidos_preparando": pedidos_preparando,
            "pedidos_listos": pedidos_listos,
            "pedidos_hoy": pedidos_hoy,
            "pedidos_atrasados": pedidos_atrasados,
            "producciones_pendientes": producciones_pendientes,
            "producciones_imprimiendo": producciones_imprimiendo,
            "unidades_en_produccion": unidades_en_produccion,
            "total_a_imprimir": total_a_imprimir,
            "productos_sin_stock": productos_sin_stock,
            "proximas_entregas": proximas_entregas,
            "top_impresion": top_impresion,
            "saldo_a_cobrar": saldo_a_cobrar,
            "pedidos_con_saldo": pedidos_con_saldo,
            "cobrado_mes": cobrado_mes,
        },
    )
