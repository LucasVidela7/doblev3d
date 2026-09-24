import json
from decimal import Decimal

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.http import HttpResponse
from django.templatetags.static import static
from django.urls import reverse

from kits.engine import KitEngine
from kits.models import Kit

from .image_environment import ambientes_imagenes_lectura
from .models import ConfiguracionCatalogo, Producto


def _absoluta(request, url):
    if not url:
        return ""
    if str(url).startswith(("http://", "https://")):
        return str(url)
    return request.build_absolute_uri(url)


def _json_ld(data):
    return (
        json.dumps(
            data,
            cls=DjangoJSONEncoder,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        .replace("</", "<\\/")
    )


def _organizacion(request, config=None):
    config = config or (
        ConfiguracionCatalogo.objects.first()
        or ConfiguracionCatalogo()
    )
    home = request.build_absolute_uri(reverse("catalogo"))
    data = {
        "@type": "Organization",
        "@id": home + "#organization",
        "name": "Doble V 3D",
        "url": home,
        "logo": request.build_absolute_uri(
            static("brand/logo.png")
        ),
    }

    same_as = []
    instagram = (
        config.instagram_usuario or ""
    ).strip().lstrip("@")
    if config.mostrar_instagram and instagram:
        same_as.append(
            f"https://www.instagram.com/{instagram}/"
        )
    if same_as:
        data["sameAs"] = same_as

    return data


def seo_catalogo(request, vista_catalogo, config=None):
    config = config or (
        ConfiguracionCatalogo.objects.first()
        or ConfiguracionCatalogo()
    )
    if vista_catalogo == "productos":
        title = "Productos impresos en 3D | Doble V 3D"
        description = (
            "Explorá productos impresos en 3D de Doble V 3D. "
            "Consultá fotos, precios, opciones de color y pedí tu "
            "presupuesto online."
        )
        canonical = request.build_absolute_uri(
            reverse("catalogo_productos")
        )
    elif vista_catalogo == "kits":
        title = "Kits impresos en 3D | Doble V 3D"
        description = (
            "Descubrí kits impresos en 3D de Doble V 3D. "
            "Elegí combinaciones, armá tu kit y pedí presupuesto online."
        )
        canonical = request.build_absolute_uri(
            reverse("catalogo_kits")
        )
    else:
        title = "Doble V 3D | Productos y kits impresos en 3D"
        description = (
            "Catálogo de Doble V 3D: productos y kits impresos en 3D "
            "con precios visibles, opciones personalizables y solicitud "
            "de presupuesto online."
        )
        canonical = request.build_absolute_uri(
            reverse("catalogo")
        )

    graph = {
        "@context": "https://schema.org",
        "@graph": [
            _organizacion(request, config),
            {
                "@type": "WebSite",
                "@id": (
                    request.build_absolute_uri(
                        reverse("catalogo")
                    )
                    + "#website"
                ),
                "url": request.build_absolute_uri(
                    reverse("catalogo")
                ),
                "name": "Doble V 3D",
                "publisher": {
                    "@id": (
                        request.build_absolute_uri(
                            reverse("catalogo")
                        )
                        + "#organization"
                    )
                },
            },
        ],
    }

    return {
        "seo_title": title,
        "seo_description": description,
        "seo_canonical_url": canonical,
        "seo_social_image_url": request.build_absolute_uri(
            static("brand/logo.png")
        ),
        "seo_json_ld": _json_ld(graph),
    }


def seo_producto(
    request,
    producto,
    *,
    image_url="",
):
    tipo = (
        producto.tipo.nombre
        if producto.tipo_id and producto.tipo
        else "impresión 3D"
    )
    title = (
        f"{producto.nombre} | {tipo} | Doble V 3D"
    )
    description = (
        f"{producto.nombre}, producto impreso en 3D de la categoría "
        f"{tipo}. Consultá precio, fotos y opciones disponibles y "
        "pedí presupuesto online en Doble V 3D."
    )
    canonical = request.build_absolute_uri(
        reverse(
            "catalogo_producto_detalle",
            args=[producto.id],
        )
    )
    social_image = request.build_absolute_uri(
        reverse(
            "catalogo_producto_social_preview",
            args=[producto.id],
        )
    )
    image = _absoluta(
        request,
        image_url or social_image,
    )
    price = Decimal(str(producto.catalogo_precio or 0))

    product = {
        "@type": "Product",
        "@id": canonical + "#product",
        "name": producto.nombre,
        "description": description,
        "url": canonical,
        "sku": producto.codigo,
        "category": tipo,
        "brand": {
            "@type": "Brand",
            "name": "Doble V 3D",
        },
    }
    if price > 0:
        product["offers"] = {
            "@type": "Offer",
            "url": canonical,
            "priceCurrency": "ARS",
            "price": f"{price:.2f}",
            "availability": "https://schema.org/InStock",
            "itemCondition": "https://schema.org/NewCondition",
        }
    if image:
        product["image"] = [image]

    breadcrumbs = {
        "@type": "BreadcrumbList",
        "@id": canonical + "#breadcrumb",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Inicio",
                "item": request.build_absolute_uri(
                    reverse("catalogo")
                ),
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": "Productos",
                "item": request.build_absolute_uri(
                    reverse("catalogo_productos")
                ),
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": producto.nombre,
                "item": canonical,
            },
        ],
    }

    return {
        "seo_title": title,
        "seo_description": description,
        "seo_canonical_url": canonical,
        "seo_json_ld": _json_ld(
            {
                "@context": "https://schema.org",
                "@graph": [
                    product,
                    breadcrumbs,
                ],
            }
        ),
        "social_description": description,
        "social_url": canonical,
        "social_image_url": social_image if image_url else (
            request.build_absolute_uri(
                static("brand/logo.png")
            )
        ),
        "social_image_is_generated": bool(image_url),
    }


def seo_kit(
    request,
    kit,
    *,
    image_available=False,
):
    tipo = (
        kit.tipo_producto.nombre
        if kit.tipo_producto_id and kit.tipo_producto
        else "productos impresos en 3D"
    )
    cantidad = max(
        int(kit.cantidad_productos or 0),
        1,
    )
    title = f"{kit.nombre} | Kit impreso en 3D | Doble V 3D"
    description = (
        f"{kit.nombre}, kit de {cantidad} "
        f"{'producto' if cantidad == 1 else 'productos'} de {tipo}. "
        "Consultá composición, precio y opciones disponibles y "
        "pedí presupuesto online en Doble V 3D."
    )
    canonical = request.build_absolute_uri(
        reverse(
            "catalogo_kit_detalle",
            args=[kit.id],
        )
    )
    social_image = request.build_absolute_uri(
        reverse(
            "catalogo_kit_social_preview",
            args=[kit.id],
        )
    )
    price = Decimal(str(kit.precio or 0))

    product = {
        "@type": "Product",
        "@id": canonical + "#product",
        "name": kit.nombre,
        "description": description,
        "url": canonical,
        "sku": kit.codigo,
        "category": tipo,
        "brand": {
            "@type": "Brand",
            "name": "Doble V 3D",
        },
    }
    if price > 0:
        product["offers"] = {
            "@type": "Offer",
            "url": canonical,
            "priceCurrency": "ARS",
            "price": f"{price:.2f}",
            "availability": "https://schema.org/InStock",
            "itemCondition": "https://schema.org/NewCondition",
        }
    if image_available:
        product["image"] = [social_image]

    breadcrumbs = {
        "@type": "BreadcrumbList",
        "@id": canonical + "#breadcrumb",
        "itemListElement": [
            {
                "@type": "ListItem",
                "position": 1,
                "name": "Inicio",
                "item": request.build_absolute_uri(
                    reverse("catalogo")
                ),
            },
            {
                "@type": "ListItem",
                "position": 2,
                "name": "Kits",
                "item": request.build_absolute_uri(
                    reverse("catalogo_kits")
                ),
            },
            {
                "@type": "ListItem",
                "position": 3,
                "name": kit.nombre,
                "item": canonical,
            },
        ],
    }

    return {
        "seo_title": title,
        "seo_description": description,
        "seo_canonical_url": canonical,
        "seo_json_ld": _json_ld(
            {
                "@context": "https://schema.org",
                "@graph": [
                    product,
                    breadcrumbs,
                ],
            }
        ),
        "social_description": description,
        "social_url": canonical,
        "social_image_url": (
            social_image
            if image_available
            else request.build_absolute_uri(
                static("brand/logo.png")
            )
        ),
        "social_image_is_collage": bool(image_available),
    }


def robots_txt(request):
    if getattr(settings, "APP_ENV", "") != "production":
        body = "User-agent: *\nDisallow: /\n"
    else:
        body = "\n".join(
            [
                "User-agent: *",
                "Allow: /",
                "Disallow: /gestion/",
                "Disallow: /carrito/",
                "Disallow: /solicitud/",
                "Disallow: /pedido/",
                "Disallow: /metricas/",
                "Disallow: /healthz/",
                "Disallow: /arrepentimiento/gracias/",
                "",
                "Sitemap: "
                + request.build_absolute_uri(
                    reverse("sitemap_xml")
                ),
                "",
            ]
        )

    response = HttpResponse(
        body,
        content_type="text/plain; charset=utf-8",
    )
    response["Cache-Control"] = "public, max-age=3600"
    return response


def sitemap_xml(request):
    urls = [
        request.build_absolute_uri(reverse("catalogo")),
        request.build_absolute_uri(
            reverse("catalogo_productos")
        ),
        request.build_absolute_uri(
            reverse("catalogo_kits")
        ),
        request.build_absolute_uri(
            reverse("catalogo_terminos")
        ),
        request.build_absolute_uri(
            reverse("catalogo_privacidad")
        ),
    ]

    config = (
        ConfiguracionCatalogo.objects.first()
        or ConfiguracionCatalogo()
    )
    productos = (
        Producto.objects
        .filter(
            activo=True,
            solo_produccion=False,
        )
        .select_related("tipo")
        .order_by("id")
    )
    if not config.mostrar_productos_sin_foto:
        productos = productos.filter(
            imagenes__ambiente__in=ambientes_imagenes_lectura()
        ).distinct()

    for producto in productos:
        urls.append(
            request.build_absolute_uri(
                reverse(
                    "catalogo_producto_detalle",
                    args=[producto.id],
                )
            )
        )

    kits = (
        Kit.objects
        .filter(activo=True)
        .select_related("tipo_producto")
        .prefetch_related(
            "componentes__producto",
        )
        .order_by("id")
    )
    for kit in kits:
        productos_categoria = None
        if (
            kit.modalidad == "LIBRE_CATEGORIA"
            and kit.tipo_producto_id
        ):
            productos_categoria = list(
                Producto.objects.filter(
                    tipo_id=kit.tipo_producto_id,
                    activo=True,
                    solo_produccion=False,
                )
            )
        if not KitEngine.validar_configuracion(
            kit,
            productos_categoria=productos_categoria,
        )["valido"]:
            continue
        urls.append(
            request.build_absolute_uri(
                reverse(
                    "catalogo_kit_detalle",
                    args=[kit.id],
                )
            )
        )

    escaped = [
        (
            url.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )
        for url in urls
    ]
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(
            f"  <url><loc>{url}</loc></url>\n"
            for url in escaped
        )
        + "</urlset>\n"
    )

    response = HttpResponse(
        body,
        content_type="application/xml; charset=utf-8",
    )
    response["Cache-Control"] = "public, max-age=900"
    return response
