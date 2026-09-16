# Fotos de productos con ImageKit

Doble V 3D almacena las fotos comerciales de los productos en ImageKit y conserva en PostgreSQL únicamente las referencias necesarias para utilizarlas.

## Regla actual

- Cada producto puede tener **máximo 2 fotos**.
- La posición `1` es la foto **principal**.
- La posición `2` es la foto **secundaria**.
- Si se elimina la principal y existe una secundaria, la secundaria pasa automáticamente a ser principal.
- Se puede intercambiar la foto principal desde la pantalla de administración de imágenes.
- El límite de dos fotos se valida en backend, no sólo en la interfaz.

## Almacenamiento

Las imágenes no se guardan en el filesystem del contenedor de Railway. El navegador envía el archivo a Django y el backend lo sube inmediatamente a ImageKit. En la base sólo se almacenan:

- `file_id` de ImageKit;
- URL pública;
- URL de thumbnail;
- nombre del archivo;
- dimensiones;
- tamaño reportado por ImageKit;
- orden dentro del producto.

Los archivos se organizan por producto dentro de:

```text
/doblev3d/productos/<producto_id>/
```

La carpeta base puede modificarse con `IMAGEKIT_FOLDER`.

## Variables de entorno

Obligatoria para subir y eliminar imágenes:

```text
IMAGEKIT_PRIVATE_KEY=...
```

Opcional:

```text
IMAGEKIT_FOLDER=/doblev3d/productos
```

La private key es un secreto. Nunca debe incluirse en el repositorio, templates, JavaScript ni URLs públicas.

## Límites

Doble V 3D limita cada upload a **15 MB** y acepta archivos cuyo MIME type sea de imagen.

## Kits

Los kits no deben almacenar copias de imágenes propias cuando las fotos corresponden a sus productos:

- **FIJO:** utilizará las fotos principales de `KitComponente.producto`.
- **LIBRE_CATEGORIA:** utilizará las fotos de los productos activos disponibles en `tipo_producto`.

Esto evita duplicados y hace que actualizar la foto de un producto actualice también su representación en los kits.

## Validación en QA

La suite `productos.test_imagenes` cubre el límite de dos fotos, carga de referencias, cambio de principal, eliminación y visualización en el detalle del producto. Los servicios externos se simulan durante estos tests para no crear ni borrar archivos reales en ImageKit.
