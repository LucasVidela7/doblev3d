from collections import Counter
from decimal import Decimal, InvalidOperation

from django.shortcuts import render

from costos.models import ConfiguracionCostos
from kits.economia import precio_automatico_kit_libre
from kits.models import Kit
from pedidos.kits_volumen import (
    CANTIDAD_MINIMA_KITS_VOLUMEN,
    DESCUENTO_MAXIMO_KITS,
    calcular_precio_volumen_kits,
)
from productos.models import Producto

from calculadora.precios import (
    CANTIDAD_MINIMA_DESCUENTO_PRODUCTOS,
    DESCUENTO_MAXIMO_PRODUCTOS,
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
        if cantidad >= 1 and cantidad not in cantidades:
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
    return cantidad


def _calcular_kit(kit, cantidad, ids_seleccion, errores):
    cantidad = _validar_cantidad(cantidad, errores)
    componentes = []
    seleccion_productos = []
    precio_lista_unitario = Decimal(str(kit.precio or 0))

    if kit.modalidad == "FIJO":
        componentes_fijos = list(kit.componentes.all())
        if not componentes_fijos:
            errores.append(
                f"{kit.nombre} no tiene componentes configurados."
            )
            return None

        componentes = [
            {
                "producto": componente.producto,
                "cantidad": int(componente.cantidad or 0) * cantidad,
            }
            for componente in componentes_fijos
            if int(componente.cantidad or 0) > 0
        ]
    else:
        esperados = int(kit.cantidad_productos or 0)
        if len(ids_seleccion) != esperados:
            errores.append(
                f"{kit.nombre} necesita exactamente {esperados} productos."
            )
            return None

        if not kit.tipo_producto_id:
            errores.append(
                f"{kit.nombre} no tiene categoría configurada."
            )
            return None

        productos = {
            producto.id: producto
            for producto in Producto.objects.filter(
                id__in=set(ids_seleccion),
                activo=True,
                solo_produccion=False,
                tipo_id=kit.tipo_producto_id,
            )
        }
        if any(producto_id not in productos for producto_id in ids_seleccion):
            errores.append(
                "Una de las opciones seleccionadas ya no está disponible."
            )
            return None

        seleccion_productos = [
            productos[producto_id]
            for producto_id in ids_seleccion
        ]
        precio_lista_unitario = Decimal(
            str(precio_automatico_kit_libre(kit, seleccion_productos))
        )

        conteo = Counter(ids_seleccion)
        componentes = [
            {
                "producto": productos[producto_id],
                "cantidad": veces * cantidad,
            }
            for producto_id, veces in conteo.items()
        ]

    if precio_lista_unitario <= 0:
        errores.append(
            f"{kit.nombre} no tiene un precio válido."
        )
        return None

    resumen = calcular_precio_volumen_kits(
        [
            {
                "key": "calculadora",
                "kit": kit,
                "cantidad": cantidad,
                "precio_unitario_lista": precio_lista_unitario,
                "componentes": componentes,
            }
        ]
    )
    linea = resumen["lineas"][0]

    return {
        "kit": kit,
        "cantidad": cantidad,
        "seleccion_productos": seleccion_productos,
        "precio_lista_unitario": linea["precio_unitario_lista"],
        "precio_final_unitario": linea["precio_unitario_final"],
        "precio_lista_total": linea["precio_lista_total"],
        "precio_final_total": linea["precio_final_total"],
        "ahorro": linea["ahorro"],
        "descuento_porcentaje": linea["descuento_porcentaje"],
        "margen_real": resumen["margen_real"],
        "margen_minimo": resumen["margen_minimo"],
        "total_piezas": resumen["total_piezas"],
        "elegible": resumen["elegible"],
        "limitado_por_margen": resumen["limitado_por_margen"],
        "precio_base_configurado": Decimal(str(kit.precio or 0)),
    }


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
    kits = (
        Kit.objects
        .filter(activo=True)
        .select_related("tipo_producto")
        .prefetch_related("componentes__producto")
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
    if modo not in {"nuevo", "existente", "kit", "personalizado"}:
        modo = "existente"

    producto_inicial_id = request.GET.get(
        "producto_id",
        "",
    ).strip()

    resultado_nuevo = None
    resultado_existente = None
    resultado_kit = None
    resultado_personalizado = None
    errores = []
    kit_seleccion_ids = []

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

        elif modo == "kit":
            kit_id = _entero(request.POST.get("kit_id"))
            cantidad = _validar_cantidad(
                _entero(request.POST.get("cantidad"), 2),
                errores,
            )
            try:
                kit_seleccion_ids = [
                    int(valor)
                    for valor in request.POST.getlist("kit_producto")
                    if str(valor).strip()
                ]
            except (TypeError, ValueError):
                kit_seleccion_ids = []
                errores.append(
                    "La selección de productos del kit no es válida."
                )

            kit = (
                Kit.objects
                .filter(id=kit_id, activo=True)
                .select_related("tipo_producto")
                .prefetch_related("componentes__producto")
                .first()
            )
            if not kit:
                errores.append("Seleccioná un kit válido.")

            if kit and not errores:
                resultado_kit = _calcular_kit(
                    kit,
                    cantidad,
                    kit_seleccion_ids,
                    errores,
                )

        elif modo == "personalizado":
            producto_id = _entero(
                request.POST.get("producto_personalizado_id")
            )
            cantidad = _validar_cantidad(
                _entero(request.POST.get("cantidad"), 1),
                errores,
            )
            total_acordado = max(
                _decimal(request.POST.get("precio_total_personalizado")),
                Decimal("0"),
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
                errores.append(
                    "Seleccioná un producto base válido."
                )

            if producto and not errores:
                base = calcular_precio_catalogo_producto(
                    producto,
                    cantidad,
                )
                adicional = (
                    total_acordado - base["precio_final_total"]
                    if total_acordado > 0
                    else Decimal("0")
                )

                resultado_personalizado = {
                    "producto": producto,
                    "cantidad": cantidad,
                    "base": base,
                    "total_acordado": total_acordado,
                    "precio_unitario_acordado": (
                        total_acordado / Decimal(cantidad)
                        if total_acordado > 0
                        else Decimal("0")
                    ),
                    "diferencia_total": adicional,
                    "por_debajo_base": (
                        total_acordado > 0
                        and total_acordado < base["precio_final_total"]
                    ),
                }

    context = {
        "modo": modo,
        "productos": productos,
        "kits": kits,
        "config": config,
        "errores": errores,
        "resultado_nuevo": resultado_nuevo,
        "resultado_existente": resultado_existente,
        "resultado_kit": resultado_kit,
        "resultado_personalizado": resultado_personalizado,
        "producto_inicial_id": producto_inicial_id,
        "cantidades_texto": cantidades_texto,
        "kit_seleccion_ids": kit_seleccion_ids,
        "cantidad_minima_descuento": CANTIDAD_MINIMA_DESCUENTO_PRODUCTOS,
        "descuento_maximo": DESCUENTO_MAXIMO_PRODUCTOS,
        "cantidad_minima_kits": CANTIDAD_MINIMA_KITS_VOLUMEN,
        "descuento_maximo_kits": DESCUENTO_MAXIMO_KITS,
    }

    return render(
        request,
        "calculadora/precios.html",
        context,
    )
