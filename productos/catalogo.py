from collections import defaultdict

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.templatetags.static import static
from django.urls import reverse
from django.utils.text import slugify
from django.views.defaults import page_not_found

from kits.engine import KitEngine
from kits.imagenes import adjuntar_imagenes_reutilizadas
from kits.models import Kit

from .image_environment import (
    ambientes_imagenes_lectura,
    clave_imagen_lectura,
    entorno_imagenes,
    seleccionar_imagenes_lectura,
)
from .image_models import ProductoImagen
from .models import ConfiguracionCatalogo, Producto, TipoProducto
from .seo import (
    seo_catalogo,
    seo_categoria,
    seo_kit,
    seo_producto,
)


def _url_absoluta(request, url):
    if not url:
        return ""
    if url.startswith(("http://", "https://")):
        return url
    return request.build_absolute_uri(url)


def _social_defaults(request):
    return {
        "social_url": request.build_absolute_uri(request.path),
        "social_fallback_image": request.build_absolute_uri(
            static("brand/logo.png")
        ),
    }


def catalogo_404(request, exception):
    """404 amigable para la tienda pública sin alterar la gestión interna."""

    if request.path_info.startswith("/gestion/"):
        return page_not_found(request, exception)

    config_catalogo = (
        ConfiguracionCatalogo.objects.first()
        or ConfiguracionCatalogo()
    )
    mostrar_whatsapp = bool(
        config_catalogo.mostrar_whatsapp
        and (config_catalogo.whatsapp_numero or "").strip()
    )

    return render(
        request,
        "productos/catalogo_404.html",
        {
            "mostrar_whatsapp": mostrar_whatsapp,
        },
        status=404,
    )


def _catalogo_publico(request, vista_catalogo, categoria_actual=None):
    """Construye el contexto público compartido de la tienda."""

    ambiente = entorno_imagenes()
    config_catalogo = (
        ConfiguracionCatalogo.objects.first()
        or ConfiguracionCatalogo()
    )

    # Compatibilidad con filtros compartidos antes de las URLs SEO.
    # /productos/?categoria=sensoriales pasa a /categorias/sensoriales/
    # conservando una búsqueda textual si existiera.
    categoria_query = (
        request.GET.get("categoria") or ""
    ).strip()
    if (
        categoria_actual is None
        and vista_catalogo in {"productos", "kits"}
        and categoria_query
    ):
        categoria_query_slug = slugify(
            categoria_query
        )
        categoria_destino = (
            TipoProducto.objects
            .filter(
                activo=True,
                slug=categoria_query_slug,
            )
            .first()
        )
        if categoria_destino is not None:
            parametros = request.GET.copy()
            parametros.pop("categoria", None)
            parametros.pop("tipo", None)
            destino = reverse(
                (
                    "catalogo_categoria_kits"
                    if vista_catalogo == "kits"
                    else "catalogo_categoria_productos"
                ),
                args=[categoria_destino.slug],
            )
            query = parametros.urlencode()
            if query:
                destino += f"?{query}"
            return redirect(
                destino,
                permanent=True,
            )

    productos = list(
        Producto.objects
        .filter(
            activo=True,
            solo_produccion=False,
        )
        .select_related("tipo")
        .prefetch_related(
            "componentes__componente",
            "insumos_asignados__insumo",
            "componentes__componente__insumos_asignados__insumo",
        )
        .order_by("tipo__nombre", "nombre")
    )

    candidatas_por_producto = defaultdict(list)
    for imagen in (
        ProductoImagen.objects
        .filter(
            producto_id__in=[producto.id for producto in productos],
            ambiente__in=ambientes_imagenes_lectura(),
        )
        .order_by("producto_id", "orden", "id")
    ):
        candidatas_por_producto[imagen.producto_id].append(imagen)

    imagenes_por_producto = {
        producto_id: seleccionar_imagenes_lectura(imagenes, limite=2)
        for producto_id, imagenes in candidatas_por_producto.items()
    }

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

    productos_visibles = [
        producto
        for producto in productos
        if (
            config_catalogo.mostrar_productos_sin_foto
            or producto.catalogo_imagen
        )
    ]

    productos_por_tipo = defaultdict(list)
    for producto in productos:
        productos_por_tipo[producto.tipo_id].append(producto)

    kits = list(
        Kit.objects
        .filter(activo=True)
        .select_related("tipo_producto")
        .prefetch_related(
            "componentes__producto__tipo",
            "componentes__producto__insumos_asignados__insumo",
            "componentes__producto__componentes__componente__insumos_asignados__insumo",
        )
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

    kits = [
        kit
        for kit in kits
        if KitEngine.validar_configuracion(
            kit,
            productos_categoria=(
                productos_por_tipo.get(kit.tipo_producto_id, [])
                if kit.modalidad == "LIBRE_CATEGORIA"
                else None
            ),
        )["valido"]
    ]

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
        for producto in productos_visibles
        if producto.catalogo_imagen
    ]
    kits_inicio = [
        kit
        for kit in kits
        if kit.catalogo_imagen_url
    ]

    categorias_productos_ids = {
        producto.tipo_id
        for producto in productos_visibles
        if producto.tipo_id
    }
    categorias_kits_ids = {
        kit.tipo_producto_id
        for kit in kits
        if kit.tipo_producto_id
    }

    if categoria_actual is not None:
        productos_visibles = [
            producto
            for producto in productos_visibles
            if producto.tipo_id == categoria_actual.id
        ]
        kits = [
            kit
            for kit in kits
            if kit.tipo_producto_id == categoria_actual.id
        ]

    if vista_catalogo == "kits":
        categorias_ids = categorias_kits_ids
    elif vista_catalogo == "productos":
        categorias_ids = categorias_productos_ids
    else:
        categorias_ids = (
            categorias_productos_ids
            | categorias_kits_ids
        )

    categorias = list(
        TipoProducto.objects
        .filter(
            activo=True,
            id__in=categorias_ids,
        )
        .order_by("nombre")
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
            "productos": productos_visibles,
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
            "categoria_actual": categoria_actual,
            **(
                seo_categoria(
                    request,
                    categoria_actual,
                    vista_catalogo,
                    config_catalogo,
                )
                if categoria_actual is not None
                else seo_catalogo(
                    request,
                    vista_catalogo,
                    config_catalogo,
                )
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


def _categoria_publica(slug):
    return get_object_or_404(
        TipoProducto,
        slug=slug,
        activo=True,
    )


def catalogo_categoria_productos(request, slug):
    """Landing SEO de una categoría dentro de Productos."""
    return _catalogo_publico(
        request,
        "productos",
        categoria_actual=_categoria_publica(slug),
    )


def catalogo_categoria_kits(request, slug):
    """Landing SEO de una categoría dentro de Kits."""
    return _catalogo_publico(
        request,
        "kits",
        categoria_actual=_categoria_publica(slug),
    )


def catalogo_categoria(request, slug):
    """Compatibilidad del enlace general creado durante QA."""
    categoria = _categoria_publica(slug)
    return redirect(
        "catalogo_categoria_productos",
        slug=categoria.slug,
        permanent=True,
    )


def catalogo_producto_detalle(request, slug):
    """Detalle público canónico de un producto por slug."""

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
        .select_related("tipo")
        .prefetch_related(
            "componentes__componente",
            "insumos_asignados__insumo",
            "componentes__componente__insumos_asignados__insumo",
        ),
        slug=slug,
    )
    producto.catalogo_precio = producto.subtotal

    imagenes = list(
        ProductoImagen.objects
        .filter(
            producto=producto,
            ambiente__in=ambientes_imagenes_lectura(),
        )
        .order_by("orden", "id")
    )
    imagenes = seleccionar_imagenes_lectura(imagenes, limite=2)
    if (
        not config_catalogo.mostrar_productos_sin_foto
        and not imagenes
    ):
        raise Http404("Producto no disponible")

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
            "colores_disponibles": (
                config_catalogo.colores_disponibles_detalle
            ),
            **seo_producto(
                request,
                producto,
                image_url=producto.catalogo_imagen_url,
            ),
        },
    )


def catalogo_producto_legacy(request, producto_id):
    """Conserva enlaces históricos y los redirige a la URL amigable."""
    producto = get_object_or_404(
        Producto,
        id=producto_id,
        activo=True,
        solo_produccion=False,
    )
    return redirect(
        "catalogo_producto_detalle",
        slug=producto.slug,
        permanent=True,
    )


def catalogo_kit_detalle(request, slug):
    """Detalle público canónico de un kit por slug."""

    ambiente = entorno_imagenes()
    config_catalogo = (
        ConfiguracionCatalogo.objects.first()
        or ConfiguracionCatalogo()
    )

    kit = get_object_or_404(
        Kit.objects
        .filter(activo=True)
        .select_related("tipo_producto")
        .prefetch_related(
            "componentes__producto__tipo",
            "componentes__producto__insumos_asignados__insumo",
            "componentes__producto__componentes__componente__insumos_asignados__insumo",
        ),
        slug=slug,
    )

    # Un kit fijo puede heredar una categoría pública cuando toda su
    # composición pertenece al mismo tipo, sin alterar la receta persistida.
    if (
        kit.modalidad == "FIJO"
        and not kit.tipo_producto_id
    ):
        componentes_categoria = list(
            kit.componentes.all()
        )
        tipos_categoria = {
            componente.producto.tipo_id
            for componente in componentes_categoria
            if (
                componente.producto_id
                and componente.producto.tipo_id
            )
        }
        if len(tipos_categoria) == 1 and componentes_categoria:
            kit.tipo_producto = (
                componentes_categoria[0]
                .producto
                .tipo
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
            .prefetch_related(
                "insumos_asignados__insumo",
                "componentes__componente__insumos_asignados__insumo",
            )
            .order_by("nombre", "id")
        )

        validacion = KitEngine.validar_configuracion(
            kit,
            productos_categoria=productos,
        )
        if not validacion["valido"]:
            raise Http404("Kit no disponible")

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
        validacion = KitEngine.validar_configuracion(kit)
        if not validacion["valido"]:
            raise Http404("Kit no disponible")

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

    adicional_color_kit = (
        config_catalogo.adicional_color_kit_libre(
            kit.cantidad_productos
        )
        if kit.modalidad == "LIBRE_CATEGORIA"
        else 0
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
            "colores_disponibles": (
                config_catalogo.colores_disponibles_detalle
            ),
            "adicional_color_kit": adicional_color_kit,
            **seo_kit(
                request,
                kit,
                image_available=bool(
                    getattr(
                        kit,
                        "productos_visuales_collage",
                        [],
                    )
                ),
            ),
        },
    )


def catalogo_kit_legacy(request, kit_id):
    """Conserva enlaces históricos y los redirige a la URL amigable."""
    kit = get_object_or_404(
        Kit,
        id=kit_id,
        activo=True,
    )
    return redirect(
        "catalogo_kit_detalle",
        slug=kit.slug,
        permanent=True,
    )
