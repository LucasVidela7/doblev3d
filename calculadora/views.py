from decimal import Decimal, InvalidOperation

from django.shortcuts import render

from costos.models import ConfiguracionCostos
from productos.models import Producto

from calculadora.precios import (
    MARGEN_MINIMO as MARGEN_MINIMO_COMPARTIDO,
    desglose_productivo,
    fila_precio as fila_precio_compartido,
    margen_sugerido as margen_sugerido_compartido,
    margenes_escenario as margenes_escenario_compartido,
    precio_mayorista as precio_mayorista_compartido,
    redondear_arriba as redondear_arriba_compartido,
)


MARGEN_MINIMO_ADVERTENCIA = MARGEN_MINIMO_COMPARTIDO
CANTIDAD_PISO_MARGEN = Decimal("1500")
CANTIDADES_LISTA_DEFAULT = "10,20,50,100"

ESCALAS_MAYORISTAS = (
    (1, 4, Decimal("60")),
    (5, 9, Decimal("50")),
    (10, 24, Decimal("45")),
    (25, 49, Decimal("40")),
    (50, 99, Decimal("35")),
    (100, 199, Decimal("30")),
    (200, 499, Decimal("27.5")),
    (500, 999, Decimal("25")),
    (1000, None, Decimal("22.5")),
)


def _decimal(valor, default=Decimal("0")):
    try:
        if valor in (None, ""):
            return default
        return Decimal(str(valor).replace(",", "."))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _entero(valor, default=0):
    try:
        return int(valor)
    except (TypeError, ValueError):
        return default


def _redondear_arriba(valor, multiplo=Decimal("100")):
    return redondear_arriba_compartido(valor, multiplo)


def _margen_sugerido(cantidad, margen_tope):
    return margen_sugerido_compartido(cantidad, margen_tope)


def _precio_mayorista(costo_productivo, margen):
    return precio_mayorista_compartido(costo_productivo, margen)


def _margen_real(precio_unitario, costo_productivo):
    precio_unitario = Decimal(precio_unitario)
    costo_productivo = Decimal(costo_productivo)

    if precio_unitario <= 0:
        return Decimal("0")

    return (
        (precio_unitario - costo_productivo)
        / precio_unitario
        * Decimal("100")
    )


def _desglose_producto(producto, cantidad=1):
    """
    Usa el mismo desglose que la calculadora compartida.

    El precio del filamento se elige según los gramos totales de esta venta;
    el precio de lista del producto sigue usando el costo estándar normal.
    """
    return desglose_productivo(
        producto,
        cantidad=max(int(cantidad or 1), 1),
    )


def _parsear_cantidades(texto):
    texto = (texto or CANTIDADES_LISTA_DEFAULT).strip()
    cantidades = []

    for parte in texto.replace(";", ",").split(","):
        parte = parte.strip()
        if not parte:
            continue

        cantidad = _entero(parte, 0)
        if cantidad > 0 and cantidad not in cantidades:
            cantidades.append(cantidad)

    if not cantidades:
        cantidades = [10, 20, 50, 100]

    return sorted(cantidades)[:12]


def _fila_precio(
    costo_productivo,
    cantidad,
    margen=None,
    precio_forzado=None,
    margen_tope=Decimal("60"),
):
    if precio_forzado is not None:
        precio_unitario = Decimal(precio_forzado)
        costo_productivo = Decimal(costo_productivo)
        cantidad = max(int(cantidad or 1), 1)
        total_sin_redondear = precio_unitario * Decimal(cantidad)
        total = _redondear_arriba(total_sin_redondear, Decimal("100"))
        costo_total = costo_productivo * Decimal(cantidad)
        ganancia = total - costo_total
        margen_real = (
            ganancia / total * Decimal("100")
            if total > 0 else Decimal("0")
        )
        return {
            "cantidad": cantidad,
            "margen_objetivo": (
                Decimal(margen)
                if margen is not None
                else _margen_sugerido(cantidad, margen_tope)
            ),
            "precio_unitario": precio_unitario,
            "total_sin_redondear": total_sin_redondear,
            "total": total,
            "costo_total": costo_total,
            "ganancia": ganancia,
            "margen_real": margen_real,
        }

    fila = fila_precio_compartido(
        costo_productivo,
        cantidad,
        margen=margen,
        margen_tope=margen_tope,
    )

    total = fila["total_recomendado"]
    costo_total = fila["costo_total"]
    ganancia = total - costo_total

    return {
        "cantidad": fila["cantidad"],
        "margen_objetivo": fila["margen_objetivo"],
        "precio_unitario": fila["precio_unitario"],
        "total_sin_redondear": fila["total_sin_redondear"],
        "total": total,
        "costo_total": costo_total,
        "ganancia": ganancia,
        "margen_real": (
            ganancia / total * Decimal("100")
            if total > 0 else Decimal("0")
        ),
    }


def _margenes_escenario(cantidad, margen_tope):
    return margenes_escenario_compartido(cantidad, margen_tope)


def _lista_precios_escenarios(producto, cantidades, margen_tope):
    """Cada cantidad recalcula su costo porque puede caer en otro tramo."""
    filas = []

    for cantidad in cantidades:
        desglose = _desglose_producto(producto, cantidad)
        costo_productivo = desglose["costo_productivo"]
        margenes = _margenes_escenario(cantidad, margen_tope)

        filas.append(
            {
                "cantidad": cantidad,
                "desglose": desglose,
                "conservador": _fila_precio(
                    costo_productivo,
                    cantidad,
                    margenes["conservador"],
                ),
                "recomendado": _fila_precio(
                    costo_productivo,
                    cantidad,
                    margenes["recomendado"],
                ),
                "agresivo": _fila_precio(
                    costo_productivo,
                    cantidad,
                    margenes["agresivo"],
                ),
            }
        )

    return filas


def _filas_de_estrategia(lista_escenarios, estrategia):
    return [
        fila[estrategia]
        for fila in lista_escenarios
    ]


def _moneda_entera(valor):
    numero = int(Decimal(valor).quantize(Decimal("1")))
    return f"{numero:,}".replace(",", ".")


def _moneda_unitaria(valor):
    valor = Decimal(valor).quantize(Decimal("0.01"))
    entero = int(valor)
    decimales = int((valor - Decimal(entero)) * 100)

    entero_txt = f"{entero:,}".replace(",", ".")

    if decimales == 0:
        return entero_txt

    return f"{entero_txt},{decimales:02d}".rstrip("0")


def _mensaje_cliente(nombre, filas, estrategia=None):
    nombre = (nombre or "Producto").strip()

    lineas = [
        f"*{nombre}*",
        "Precios por cantidad:",
        "",
    ]

    for fila in filas:
        lineas.append(
            f"• x{fila['cantidad']}: "
            f"${_moneda_unitaria(fila['precio_unitario'])} c/u "
            f"— Total ${_moneda_entera(fila['total'])}"
        )

    lineas.extend(
        [
            "",
            "Precios sujetos a confirmación al momento de realizar el pedido.",
        ]
    )

    return "\n".join(lineas)


def _escenarios(costo_productivo, cantidad, margen_recomendado, margen_tope):
    margen_conservador = min(
        margen_recomendado + Decimal("4"),
        Decimal(margen_tope),
    )
    margen_agresivo = max(
        margen_recomendado - Decimal("4"),
        MARGEN_MINIMO_ADVERTENCIA,
    )

    return [
        {
            "nombre": nombre,
            **_fila_precio(
                costo_productivo,
                cantidad,
                margen,
            ),
        }
        for nombre, margen in (
            ("Conservador", margen_conservador),
            ("Recomendado", margen_recomendado),
            ("Agresivo", margen_agresivo),
        )
    ]


def calculadora_precios(request):
    productos = (
        Producto.objects
        .filter(activo=True, requiere_impresion=True)
        .select_related("tipo")
        .order_by("nombre")
    )

    config = (
        ConfiguracionCostos.objects
        .filter(activa=True)
        .order_by("-fecha_desde")
        .first()
    )

    modo = request.POST.get(
        "modo",
        request.GET.get("modo", "nuevo"),
    )

    producto_inicial_id = request.GET.get(
        "producto_id",
        "",
    ).strip()

    resultado_nuevo = None
    resultado_existente = None
    errores = []

    cantidades_texto = request.POST.get(
        "cantidades_lista",
        CANTIDADES_LISTA_DEFAULT,
    )
    cantidades_lista = _parsear_cantidades(cantidades_texto)

    if request.method == "POST":
        # ==========================================================
        # PRODUCTO NUEVO
        # ==========================================================
        if modo == "nuevo":
            nombre_cotizacion = (
                request.POST.get("nombre_cotizacion", "")
                .strip()
                or "Producto cotizado"
            )
            horas = max(_entero(request.POST.get("horas"), 0), 0)
            minutos = max(_entero(request.POST.get("minutos"), 0), 0)
            peso = max(
                _decimal(request.POST.get("peso_gramos")),
                Decimal("0"),
            )
            margen_minorista = _decimal(
                request.POST.get("margen"),
                Decimal("60"),
            )
            cantidad = max(
                _entero(request.POST.get("cantidad"), 1),
                1,
            )

            if minutos >= 60:
                horas += minutos // 60
                minutos %= 60

            if peso <= 0:
                errores.append("Ingresá un peso mayor a 0 gramos.")

            if horas == 0 and minutos == 0:
                errores.append(
                    "Ingresá un tiempo de impresión mayor a 0."
                )

            if margen_minorista < 0 or margen_minorista >= 100:
                errores.append(
                    "El margen debe ser mayor o igual a 0 y menor a 100%."
                )

            if not config:
                errores.append(
                    "No hay una ConfiguracionCostos activa."
                )

            if not errores:
                producto_temporal = Producto(
                    nombre=nombre_cotizacion,
                    categoria="PRODUCTO",
                    horas=horas,
                    minutos=minutos,
                    peso_gramos=peso,
                    margen_ganancia=margen_minorista,
                    requiere_impresion=True,
                    personalizable=False,
                    stock=0,
                    activo=True,
                )

                desglose = _desglose_producto(
                    producto_temporal,
                    cantidad,
                )
                costo_productivo = desglose["costo_productivo"]
                precio_lista = producto_temporal.subtotal
                margen_cantidad = _margen_sugerido(
                    cantidad,
                    margen_minorista,
                )
                fila_cantidad = _fila_precio(
                    costo_productivo,
                    cantidad,
                    margen_cantidad,
                    precio_forzado=(
                        precio_lista if cantidad <= 4 else None
                    ),
                )
                lista_escenarios = _lista_precios_escenarios(
                    producto_temporal,
                    cantidades_lista,
                    margen_minorista,
                )
                lista = _filas_de_estrategia(
                    lista_escenarios,
                    "recomendado",
                )

                resultado_nuevo = {
                    "nombre": nombre_cotizacion,
                    "horas": horas,
                    "minutos": minutos,
                    "peso": peso,
                    "margen_minorista": margen_minorista,
                    "margen_tope": margen_minorista,
                    "margen_piso": MARGEN_MINIMO_ADVERTENCIA,
                    "cantidad": cantidad,
                    "desglose": desglose,
                    "precio_lista": precio_lista,
                    "margen_lista_real": _margen_real(
                        precio_lista,
                        costo_productivo,
                    ),
                    "fila_cantidad": fila_cantidad,
                    "lista_precios": lista,
                    "lista_escenarios": lista_escenarios,
                    "mensajes": {
                        "conservador": _mensaje_cliente(
                            nombre_cotizacion,
                            _filas_de_estrategia(
                                lista_escenarios,
                                "conservador",
                            ),
                        ),
                        "recomendado": _mensaje_cliente(
                            nombre_cotizacion,
                            _filas_de_estrategia(
                                lista_escenarios,
                                "recomendado",
                            ),
                        ),
                        "agresivo": _mensaje_cliente(
                            nombre_cotizacion,
                            _filas_de_estrategia(
                                lista_escenarios,
                                "agresivo",
                            ),
                        ),
                    },
                    "mensaje_cliente": _mensaje_cliente(
                        nombre_cotizacion,
                        lista,
                    ),
                }

        # ==========================================================
        # PRODUCTO EXISTENTE / MAYORISTA
        # ==========================================================
        elif modo == "existente":
            producto_id = _entero(
                request.POST.get("producto_id")
            )
            cantidad = max(
                _entero(request.POST.get("cantidad"), 1),
                1,
            )

            producto = (
                Producto.objects
                .filter(
                    id=producto_id,
                    activo=True,
                    requiere_impresion=True,
                )
                .first()
            )

            if not producto:
                errores.append("Seleccioná un producto válido.")

            if not config:
                errores.append(
                    "No hay una ConfiguracionCostos activa."
                )

            if not errores:
                desglose = _desglose_producto(
                    producto,
                    cantidad,
                )
                costo_productivo = desglose["costo_productivo"]
                margen_tope = max(
                    Decimal(producto.margen_ganancia),
                    MARGEN_MINIMO_ADVERTENCIA,
                )
                recomendado = _margen_sugerido(
                    cantidad,
                    margen_tope,
                )

                margen_ingresado = (
                    request.POST.get("margen_mayorista", "")
                    .strip()
                )

                margen_usado = (
                    _decimal(margen_ingresado, recomendado)
                    if margen_ingresado
                    else recomendado
                )

                if margen_usado > margen_tope:
                    margen_usado = margen_tope

                if margen_usado < 0 or margen_usado >= 100:
                    errores.append(
                        "El margen mayorista debe ser mayor o igual a 0 y menor a 100%."
                    )

                if not errores:
                    fila_cantidad = _fila_precio(
                        costo_productivo,
                        cantidad,
                        margen_usado,
                        precio_forzado=(
                            producto.subtotal
                            if cantidad <= 4 and not margen_ingresado
                            else None
                        ),
                    )
                    lista_escenarios = _lista_precios_escenarios(
                        producto,
                        cantidades_lista,
                        margen_tope,
                    )
                    lista = _filas_de_estrategia(
                        lista_escenarios,
                        "recomendado",
                    )

                    resultado_existente = {
                        "producto": producto,
                        "cantidad": cantidad,
                        "desglose": desglose,
                        "precio_lista": producto.subtotal,
                        "margen_recomendado": recomendado,
                        "margen_tope": margen_tope,
                        "margen_piso": MARGEN_MINIMO_ADVERTENCIA,
                        "margen_usado": margen_usado,
                        "fila_cantidad": fila_cantidad,
                        "advertencia_margen": (
                            margen_usado
                            < MARGEN_MINIMO_ADVERTENCIA
                        ),
                        "escenarios": _escenarios(
                            costo_productivo,
                            cantidad,
                            recomendado,
                            margen_tope,
                        ),
                        "lista_precios": lista,
                        "lista_escenarios": lista_escenarios,
                        "mensajes": {
                            "conservador": _mensaje_cliente(
                                producto.nombre,
                                _filas_de_estrategia(
                                    lista_escenarios,
                                    "conservador",
                                ),
                            ),
                            "recomendado": _mensaje_cliente(
                                producto.nombre,
                                _filas_de_estrategia(
                                    lista_escenarios,
                                    "recomendado",
                                ),
                            ),
                            "agresivo": _mensaje_cliente(
                                producto.nombre,
                                _filas_de_estrategia(
                                    lista_escenarios,
                                    "agresivo",
                                ),
                            ),
                        },
                        "mensaje_cliente": _mensaje_cliente(
                            producto.nombre,
                            lista,
                        ),
                    }

    tramos_filamento = (
        list(
            config.tramos_filamento
            .filter(activo=True)
            .order_by("desde_gramos")
        )
        if config
        else []
    )

    context = {
        "modo": modo,
        "productos": productos,
        "config": config,
        "tramos_filamento": tramos_filamento,
        "errores": errores,
        "resultado_nuevo": resultado_nuevo,
        "resultado_existente": resultado_existente,
        "escalas": ESCALAS_MAYORISTAS,
        "margen_minimo": MARGEN_MINIMO_ADVERTENCIA,
        "cantidades_texto": cantidades_texto,
        "producto_inicial_id": producto_inicial_id,
    }

    return render(
        request,
        "calculadora/precios.html",
        context,
    )
