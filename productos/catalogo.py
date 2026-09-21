from collections import defaultdict

from django.shortcuts import get_object_or_404, render

from kits.engine import KitEngine
from kits.imagenes import adjuntar_imagenes_reutilizadas
from kits.models import Kit

from .image_environment import entorno_imagenes
from .image_models import ProductoImagen
from .models import ConfiguracionCatalogo, Producto


def _catalogo_publico(request, vista_catalogo):
    """Construye el contexto público compartido de la tienda."""

    ambiente = entorno_imagenes()
    config_catalogo = (
        ConfiguracionCatalogo.objects.first()
        or ConfiguracionCatalogo()
    )

    productos = list(
        Producto.objects
        .filter(
            activo=True,
            solo_produccion=False,
        )
        .select_related("tipo")
        .order_by("tipo__nombre", "nombre")
    )

    imagenes_por_producto = defaultdict(list)
    for imagen in (
        ProductoImagen.objects
        .filter(
            producto_id__in=[producto.id for producto in productos],
            ambiente=ambiente,
        )
        .order_by("producto_id", "orden", "id")
    ):
        if len(imagenes_por_producto[imagen.producto_id]) < 2:
            imagenes_por_producto[imagen.producto_id].append(imagen)

    for producto in productos:
        producto.catalogo_imagenes_preview = (
            imagenes_por_producto.get(producto.id, [])
        )
        producto.catalogo_imagen = (
            producto.catalogo_imagenes_preview[0]
            if producto.catalogo_imagenes_preview
            else None
        )
        producto.catalogo_precio = producto.subtotal

    # En el catálogo priorizamos los productos que ya tienen foto principal.
    # Dentro de cada grupo mantenemos un orden estable por categoría y nombre.
    productos.sort(
        key=lambda producto: (
            0 if producto.catalogo_imagen else 1,
            (producto.tipo.nombre if producto.tipo else "").casefold(),
            producto.nombre.casefold(),
        )
    )

    productos_por_tipo = defaultdict(list)
    for producto in productos:
        productos_por_tipo[producto.tipo_id].append(producto)

    kits = list(
        Kit.objects
        .filter(activo=True)
        .select_related("tipo_producto")
        .prefetch_related("componentes__producto__tipo")
        .order_by("nombre")
    )

    # Los kits libres ya tienen una categoría explícita. Para un kit fijo,
    # si todos sus componentes pertenecen al mismo tipo de producto, usamos
    # ese tipo como categoría de catálogo sin persistirlo en la base. De esta
    # forma un enlace ?categoria=... también incluye esos kits fijos.
    for kit in kits:
        if kit.modalidad != "FIJO" or kit.tipo_producto_id:
            continue

        componentes = list(kit.componentes.all())
        tipos = {
            componente.producto.tipo_id
            for componente in componentes
            if componente.producto_id and componente.producto.tipo_id
        }
        if len(tipos) == 1 and componentes:
            kit.tipo_producto = componentes[0].producto.tipo

    for kit in kits:
        if kit.modalidad == "LIBRE_CATEGORIA":
            analisis = KitEngine.opciones(
                kit,
                productos_categoria=productos_por_tipo.get(
                    kit.tipo_producto_id,
                    [],
                ),
            )
            kit.opciones_libres_analisis = analisis
            kit.catalogo_opciones_incluidas = analisis["incluidos"]
            kit.catalogo_opciones_premium = analisis["premium"]
            kit.catalogo_productos_visuales = [
                item["producto"]
                for item in (
                    analisis["incluidos"]
                    + analisis["premium"]
                )
            ]
            kit.catalogo_busqueda_productos = " ".join(
                item["nombre"]
                for item in analisis["opciones"]
            )

    adjuntar_imagenes_reutilizadas(
        kits,
        productos_por_tipo=productos_por_tipo,
    )

    for kit in kits:
        kit.catalogo_imagen_url = next(
            (
                visual["imagen_url"]
                for visual in kit.productos_visuales
                if visual["imagen_url"]
            ),
            "",
        )

    # La portada funciona como vidriera: sólo mostramos destacados que
    # tengan una imagen disponible. Las páginas completas de Productos y
    # Kits mantienen todos los ítems activos, tengan foto o no.
    productos_inicio = [
        producto
        for producto in productos
        if producto.catalogo_imagen
    ]
    kits_inicio = [
        kit
        for kit in kits
        if kit.catalogo_imagen_url
    ]

    categorias = sorted(
        {
            producto.tipo.nombre
            for producto in productos
            if producto.tipo_id and producto.tipo
        }
    )

    template = (
        "productos/tienda_inicio.html"
        if vista_catalogo == "inicio"
        else "productos/catalogo_publico.html"
    )

    return render(
        request,
        template,
        {
            "productos": productos,
            "kits": kits,
            "productos_inicio": productos_inicio,
            "kits_inicio": kits_inicio,
            "categorias": categorias,
            "vista_catalogo": vista_catalogo,
            "ambiente_catalogo": ambiente,
            "es_ambiente_no_productivo": ambiente != "production",
            "mensaje_plazo_entrega": (
                config_catalogo.mensaje_plazo_entrega
            ),
        },
    )



def catalogo(request):
    """Página principal de la tienda pública."""
    return _catalogo_publico(request, "inicio")


def catalogo_productos(request):
    """Página pública exclusiva de productos."""
    return _catalogo_publico(request, "productos")


def catalogo_kits(request):
    """Página pública exclusiva de kits."""
    return _catalogo_publico(request, "kits")


def catalogo_producto_detalle(request, producto_id):
    """Detalle público de un producto activo del catálogo."""

    ambiente = entorno_imagenes()
    config_catalogo = (
        ConfiguracionCatalogo.objects.first()
        or ConfiguracionCatalogo()
    )

    producto = get_object_or_404(
        Producto.objects
        .filter(
            activo=True,
            solo_produccion=False,
        )
        .select_related("tipo"),
        id=producto_id,
    )
    producto.catalogo_precio = producto.subtotal

    imagenes = list(
        ProductoImagen.objects
        .filter(
            producto=producto,
            ambiente=ambiente,
        )
        .order_by("orden", "id")[:2]
    )
    producto.catalogo_imagen_url = (
        imagenes[0].url
        if imagenes
        else ""
    )

    return render(
        request,
        "productos/catalogo_producto_detalle.html",
        {
            "producto": producto,
            "imagenes": imagenes,
            "ambiente_catalogo": ambiente,
            "es_ambiente_no_productivo": ambiente != "production",
            "mensaje_plazo_entrega": (
                config_catalogo.mensaje_plazo_entrega
            ),
        },
    )


def catalogo_kit_detalle(request, kit_id):
    """Detalle público de un kit activo, sin exponer la gestión interna."""

    ambiente = entorno_imagenes()
    config_catalogo = (
        ConfiguracionCatalogo.objects.first()
        or ConfiguracionCatalogo()
    )

    kit = get_object_or_404(
        Kit.objects
        .filter(activo=True)
        .select_related("tipo_producto")
        .prefetch_related("componentes__producto__tipo"),
        id=kit_id,
    )

    seleccionables = []
    adicionales = []
    componentes_fijos = []
    analisis = None

    if kit.modalidad == "LIBRE_CATEGORIA":
        productos = list(
            Producto.objects
            .filter(
                tipo_id=kit.tipo_producto_id,
                activo=True,
                solo_produccion=False,
            )
            .select_related("tipo")
            .order_by("nombre", "id")
        )

        analisis = KitEngine.opciones(
            kit,
            productos_categoria=productos,
        )

        adjuntar_imagenes_reutilizadas(
            [kit],
            productos_por_tipo={
                kit.tipo_producto_id: productos,
            },
        )

        imagenes = {
            visual["producto"].id: visual["imagen_url"]
            for visual in getattr(kit, "productos_visuales", [])
        }

        def opcion_publica(item):
            opcion = dict(item)
            opcion["imagen_url"] = imagenes.get(
                item["producto_id"],
                "",
            )
            return opcion

        seleccionables = [
            opcion_publica(item)
            for item in analisis["incluidos"]
        ]
        adicionales = [
            opcion_publica(item)
            for item in analisis["premium"]
        ]

        seleccionables.sort(
            key=lambda item: (
                item["nombre"].casefold(),
                item["producto_id"],
            )
        )
        adicionales.sort(
            key=lambda item: (
                item["extra"],
                item["nombre"].casefold(),
                item["producto_id"],
            )
        )

    else:
        adjuntar_imagenes_reutilizadas([kit])

        imagenes = {
            visual["producto"].id: visual["imagen_url"]
            for visual in getattr(kit, "productos_visuales", [])
        }

        componentes_fijos = [
            {
                "producto": componente.producto,
                "cantidad": componente.cantidad,
                "imagen_url": imagenes.get(
                    componente.producto_id,
                    "",
                ),
            }
            for componente in kit.componentes.all()
        ]
        componentes_fijos.sort(
            key=lambda item: (
                item["producto"].nombre.casefold(),
                item["producto"].id,
            )
        )

    kit.catalogo_imagen_url = next(
        (
            visual["imagen_url"]
            for visual in getattr(kit, "productos_visuales", [])
            if visual["imagen_url"]
        ),
        "",
    )

    return render(
        request,
        "productos/catalogo_kit_detalle.html",
        {
            "kit": kit,
            "seleccionables": seleccionables,
            "adicionales": adicionales,
            "componentes_fijos": componentes_fijos,
            "analisis_opciones": analisis,
            "ambiente_catalogo": ambiente,
            "es_ambiente_no_productivo": ambiente != "production",
            "mensaje_plazo_entrega": (
                config_catalogo.mensaje_plazo_entrega
            ),
        },
    )
