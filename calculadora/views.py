from decimal import Decimal, InvalidOperation

from django.shortcuts import render

from costos.models import ConfiguracionCostos
from productos.models import Producto

from calculadora.precios import (
    CANTIDAD_MINIMA_DESCUENTO_PRODUCTOS,
    DESCUENTO_MAXIMO_PRODUCTOS,
    MAX_CANTIDAD_CATALOGO,
    calcular_precio_catalogo_producto,
)


CANTIDADES_LISTA_DEFAULT = "1,2,4,5,6,10,15,20"


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


def _parsear_cantidades(texto):
    texto = (texto or CANTIDADES_LISTA_DEFAULT).strip()
    cantidades = []

    for parte in texto.replace(";", ",").split(","):
        parte = parte.strip()
        if not parte:
            continue

        cantidad = _entero(parte, 0)
        if (
            1 <= cantidad <= MAX_CANTIDAD_CATALOGO
            and cantidad not in cantidades
        ):
            cantidades.append(cantidad)

    if not cantidades:
        cantidades = [1, 2, 4, 5, 6, 10, 15, 20]

    return sorted(cantidades)[:12]


def _lista_catalogo(producto, cantidades):
    return [
        calcular_precio_catalogo_producto(producto, cantidad)
        for cantidad in cantidades
    ]


def _moneda(valor):
    valor = Decimal(str(valor or 0)).quantize(Decimal("0.01"))
    entero = int(valor)
    centavos = int((valor - Decimal(entero)) * 100)
    entero_txt = f"{entero:,}".replace(",", ".")
    if not centavos:
        return entero_txt
    return f"{entero_txt},{centavos:02d}".rstrip("0")


def _mensaje_cliente(nombre, filas):
    nombre = (nombre or "Producto").strip()
    lineas = [
        f"*{nombre}*",
        "Precios por cantidad:",
        "",
    ]

    for fila in filas:
        descuento = fila["descuento_porcentaje"]
        extra = (
            f" · {descuento}% desc."
            if descuento > 0
            else ""
        )
        lineas.append(
            f"• x{fila['cantidad']}: "
            + "$"
            + _moneda(fila["precio_unitario"])
            + " c/u"
            + extra
            + " — Total $"
            + _moneda(fila["precio_final_total"])
        )

    lineas.extend(
        [
            "",
            "Precios calculados con la misma lógica vigente del catálogo web.",
        ]
    )
    return "\n".join(lineas)


def _validar_cantidad(cantidad, errores):
    if cantidad < 1:
        errores.append("La cantidad debe ser mayor a 0.")
        return 1
    if cantidad > MAX_CANTIDAD_CATALOGO:
        errores.append(
            f"El catálogo admite hasta {MAX_CANTIDAD_CATALOGO} unidades "
            "por línea."
        )
        return MAX_CANTIDAD_CATALOGO
    return cantidad


def calculadora_precios(request):
    productos = (
        Producto.objects
        .filter(
            activo=True,
            solo_produccion=False,
        )
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
        request.GET.get("modo", "existente"),
    )
    if modo not in {"nuevo", "existente"}:
        modo = "existente"

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
        if modo == "nuevo":
            nombre_cotizacion = (
                request.POST.get("nombre_cotizacion", "").strip()
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
            cantidad = _validar_cantidad(
                _entero(request.POST.get("cantidad"), 5),
                errores,
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
                    solo_produccion=False,
                )

                catalogo = calcular_precio_catalogo_producto(
                    producto_temporal,
                    cantidad,
                )
                lista = _lista_catalogo(
                    producto_temporal,
                    cantidades_lista,
                )

                resultado_nuevo = {
                    "nombre": nombre_cotizacion,
                    "horas": horas,
                    "minutos": minutos,
                    "peso": peso,
                    "margen_minorista": margen_minorista,
                    "cantidad": cantidad,
                    "catalogo": catalogo,
                    "lista_precios": lista,
                    "mensaje_cliente": _mensaje_cliente(
                        nombre_cotizacion,
                        lista,
                    ),
                }

        elif modo == "existente":
            producto_id = _entero(
                request.POST.get("producto_id")
            )
            cantidad = _validar_cantidad(
                _entero(request.POST.get("cantidad"), 5),
                errores,
            )

            producto = (
                Producto.objects
                .filter(
                    id=producto_id,
                    activo=True,
                    solo_produccion=False,
                )
                .select_related("tipo")
                .first()
            )

            if not producto:
                errores.append("Seleccioná un producto válido.")

            if not config:
                errores.append(
                    "No hay una ConfiguracionCostos activa."
                )

            if not errores:
                catalogo = calcular_precio_catalogo_producto(
                    producto,
                    cantidad,
                )
                lista = _lista_catalogo(
                    producto,
                    cantidades_lista,
                )

                resultado_existente = {
                    "producto": producto,
                    "cantidad": cantidad,
                    "catalogo": catalogo,
                    "lista_precios": lista,
                    "mensaje_cliente": _mensaje_cliente(
                        producto.nombre,
                        lista,
                    ),
                }

    context = {
        "modo": modo,
        "productos": productos,
        "config": config,
        "errores": errores,
        "resultado_nuevo": resultado_nuevo,
        "resultado_existente": resultado_existente,
        "producto_inicial_id": producto_inicial_id,
        "cantidades_texto": cantidades_texto,
        "cantidad_minima_descuento": CANTIDAD_MINIMA_DESCUENTO_PRODUCTOS,
        "descuento_maximo": DESCUENTO_MAXIMO_PRODUCTOS,
        "max_cantidad_catalogo": MAX_CANTIDAD_CATALOGO,
    }

    return render(
        request,
        "calculadora/precios.html",
        context,
    )
