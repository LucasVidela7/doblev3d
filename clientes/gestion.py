from datetime import timedelta
from decimal import Decimal

from django.db.models import (
    Case,
    Count,
    DateField,
    DecimalField,
    ExpressionWrapper,
    F,
    IntegerField,
    Max,
    OuterRef,
    Q,
    Subquery,
    Sum,
    Value,
    When,
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from pedidos.models import (
    DetallePedido,
    DetallePresupuesto,
    Pago,
    Pedido,
    Presupuesto,
)

from .models import Cliente


DINERO = DecimalField(
    max_digits=16,
    decimal_places=2,
)


def _subtotal_pedido_expr():
    return Case(
        When(
            tipo_item="PERSONALIZADO",
            precio_total_personalizado__isnull=False,
            then=F("precio_total_personalizado"),
        ),
        default=ExpressionWrapper(
            F("precio_unitario") * F("cantidad"),
            output_field=DINERO,
        ),
        output_field=DINERO,
    )


def clientes_con_resumen():
    """Clientes con métricas comerciales sin precargar todo su historial."""
    total_comprado = (
        DetallePedido.objects
        .filter(
            pedido__cliente_id=OuterRef("pk"),
        )
        .exclude(pedido__estado="CANCELADO")
        .values("pedido__cliente_id")
        .annotate(
            valor=Sum(_subtotal_pedido_expr()),
        )
        .values("valor")[:1]
    )

    total_pagado = (
        Pago.objects
        .filter(
            pedido__cliente_id=OuterRef("pk"),
        )
        .exclude(pedido__estado="CANCELADO")
        .values("pedido__cliente_id")
        .annotate(valor=Sum("monto"))
        .values("valor")[:1]
    )

    ultimo_pedido = (
        Pedido.objects
        .filter(cliente_id=OuterRef("pk"))
        .order_by("-fecha", "-id")
    )
    ultimo_presupuesto = (
        Presupuesto.objects
        .filter(cliente_id=OuterRef("pk"))
        .order_by("-fecha", "-id")
    )

    return (
        Cliente.objects
        .filter(activo=True)
        .annotate(
            cantidad_pedidos_db=Count(
                "pedidos",
                distinct=True,
            ),
            cantidad_cancelados_db=Count(
                "pedidos",
                filter=Q(pedidos__estado="CANCELADO"),
                distinct=True,
            ),
            cantidad_presupuestos_db=Count(
                "presupuestos",
                distinct=True,
            ),
            pedidos_activos_count_db=Count(
                "pedidos",
                filter=Q(
                    pedidos__estado__in=[
                        "PENDIENTE",
                        "PREPARANDO",
                        "LISTO",
                    ]
                ),
                distinct=True,
            ),
            pedidos_listos_count_db=Count(
                "pedidos",
                filter=Q(pedidos__estado="LISTO"),
                distinct=True,
            ),
            presupuestos_pendientes_count_db=Count(
                "presupuestos",
                filter=Q(
                    presupuestos__estado="PENDIENTE",
                ),
                distinct=True,
            ),
            ultima_fecha_pedido_db=Max(
                "pedidos__fecha",
                output_field=DateField(),
            ),
            ultima_fecha_presupuesto_db=Max(
                "presupuestos__fecha",
                output_field=DateField(),
            ),
            total_comprado_db=Coalesce(
                Subquery(
                    total_comprado,
                    output_field=DINERO,
                ),
                Value(Decimal("0")),
                output_field=DINERO,
            ),
            total_pagado_db=Coalesce(
                Subquery(
                    total_pagado,
                    output_field=DINERO,
                ),
                Value(Decimal("0")),
                output_field=DINERO,
            ),
            ultimo_pedido_id_db=Subquery(
                ultimo_pedido.values("id")[:1],
                output_field=IntegerField(),
            ),
            ultimo_presupuesto_id_db=Subquery(
                ultimo_presupuesto.values("id")[:1],
                output_field=IntegerField(),
            ),
        )
        .order_by("nombre")
    )


def resumen_desde_anotaciones(cliente):
    hoy = timezone.localdate()
    total_comprado = Decimal(
        cliente.total_comprado_db or 0
    )
    total_pagado = Decimal(
        cliente.total_pagado_db or 0
    )
    saldo = max(
        total_comprado - total_pagado,
        Decimal("0"),
    )

    fechas = [
        fecha
        for fecha in (
            cliente.ultima_fecha_pedido_db,
            cliente.ultima_fecha_presupuesto_db,
        )
        if fecha
    ]
    ultima_actividad = max(fechas) if fechas else None
    dias_sin_actividad = (
        (hoy - ultima_actividad).days
        if ultima_actividad
        else None
    )

    pedidos_activos = int(
        cliente.pedidos_activos_count_db or 0
    )
    pedidos_listos = int(
        cliente.pedidos_listos_count_db or 0
    )
    presupuestos_pendientes = int(
        cliente.presupuestos_pendientes_count_db or 0
    )

    atenciones = []
    if pedidos_listos:
        atenciones.append(
            f"{pedidos_listos} pedido(s) listo(s)"
        )
    if saldo > 0:
        atenciones.append(
            f"Saldo $ {saldo:,.0f}"
        )
    if presupuestos_pendientes:
        atenciones.append(
            f"{presupuestos_pendientes} presupuesto(s) pendiente(s)"
        )

    sin_actividad = (
        dias_sin_actividad is None
        or dias_sin_actividad >= 60
    )
    para_contactar = (
        presupuestos_pendientes > 0
        or (
            sin_actividad
            and pedidos_activos == 0
        )
    )

    return {
        "cliente": cliente,
        "cantidad_pedidos": int(
            cliente.cantidad_pedidos_db or 0
        ),
        "cantidad_cancelados": int(
            cliente.cantidad_cancelados_db or 0
        ),
        "cantidad_presupuestos": int(
            cliente.cantidad_presupuestos_db or 0
        ),
        "pedidos_activos_count": pedidos_activos,
        "pedidos_listos_count": pedidos_listos,
        "presupuestos_pendientes_count": presupuestos_pendientes,
        "total_comprado": total_comprado,
        "total_pagado": total_pagado,
        "saldo_pendiente": saldo,
        "ultima_actividad": ultima_actividad,
        "dias_sin_actividad": dias_sin_actividad,
        "sin_actividad_reciente": sin_actividad,
        "atenciones": atenciones,
        "necesita_atencion": bool(atenciones),
        "para_contactar": para_contactar,
        "ultimo_pedido_codigo": (
            f"PED{cliente.ultimo_pedido_id_db:04d}"
            if cliente.ultimo_pedido_id_db
            else ""
        ),
        "ultimo_presupuesto_codigo": (
            f"PRE{cliente.ultimo_presupuesto_id_db:04d}"
            if cliente.ultimo_presupuesto_id_db
            else ""
        ),
    }


def preferencias_cliente(cliente, limite=5):
    """Productos y kits más comprados, sin cargar pedidos completos."""
    productos = list(
        DetallePedido.objects
        .filter(
            pedido__cliente=cliente,
            producto__isnull=False,
        )
        .exclude(pedido__estado="CANCELADO")
        .values(
            "producto_id",
            "producto__nombre",
        )
        .annotate(
            unidades=Sum("cantidad"),
            compras=Count(
                "pedido_id",
                distinct=True,
            ),
            ultima=Max("pedido__fecha"),
        )
        .order_by("-unidades", "-compras")[:limite]
    )

    kits = list(
        DetallePedido.objects
        .filter(
            pedido__cliente=cliente,
            kit__isnull=False,
            tipo_item="KIT",
        )
        .exclude(pedido__estado="CANCELADO")
        .values(
            "kit_id",
            "kit__nombre",
        )
        .annotate(
            unidades=Sum("cantidad"),
            compras=Count(
                "pedido_id",
                distinct=True,
            ),
            ultima=Max("pedido__fecha"),
        )
        .order_by("-unidades", "-compras")[:limite]
    )

    resultado = [
        {
            "tipo": "PRODUCTO",
            "nombre": item["producto__nombre"],
            "unidades": item["unidades"] or 0,
            "compras": item["compras"] or 0,
            "ultima": item["ultima"],
        }
        for item in productos
    ] + [
        {
            "tipo": "KIT",
            "nombre": item["kit__nombre"],
            "unidades": item["unidades"] or 0,
            "compras": item["compras"] or 0,
            "ultima": item["ultima"],
        }
        for item in kits
    ]

    resultado.sort(
        key=lambda item: (
            int(item["unidades"] or 0),
            int(item["compras"] or 0),
        ),
        reverse=True,
    )
    return resultado[:limite]


def candidatos_fusion(cliente, limite=10):
    """Sugiere duplicados por teléfono, email o nombre."""
    telefono = "".join(
        caracter
        for caracter in (cliente.telefono or "")
        if caracter.isdigit()
    )
    email = (cliente.email or "").strip().lower()
    nombre = (cliente.nombre or "").strip().lower()

    candidatos = []
    for otro in (
        Cliente.objects
        .filter(activo=True)
        .exclude(id=cliente.id)
        .order_by("nombre")
    ):
        otro_telefono = "".join(
            caracter
            for caracter in (otro.telefono or "")
            if caracter.isdigit()
        )
        coincide = bool(
            (telefono and otro_telefono == telefono)
            or (
                email
                and (otro.email or "").strip().lower() == email
            )
            or (
                nombre
                and (otro.nombre or "").strip().lower() == nombre
            )
        )
        if coincide:
            candidatos.append(otro)
        if len(candidatos) >= limite:
            break

    return candidatos
