# ImageKit por ambiente y reutilización en kits

Las imágenes de productos se aíslan por ambiente.

- QA: `/doblev3d/qa/productos/<id>/`
- Production: `/doblev3d/production/productos/<id>/`
- Cada `ProductoImagen` guarda su `ambiente`.
- Las vistas de producto sólo consultan, modifican y eliminan imágenes del ambiente actual.
- Una clonación Production → QA puede copiar referencias productivas en PostgreSQL, pero QA no las muestra ni permite operarlas.

## Kits

Los kits no almacenan imágenes propias.

- `FIJO`: reutiliza la foto principal de cada producto de `KitComponente` y conserva la cantidad del componente.
- `LIBRE_CATEGORIA`: reutiliza la foto principal de los productos activos y comerciales de la categoría seleccionada.
- En ambos casos se usa sólo la imagen del ambiente actual.
- El listado interno muestra hasta 8 productos por kit para mantener una interfaz compacta; el conjunto completo queda disponible en la preparación de datos para un catálogo futuro.

## Regresión específica

```bash
python manage.py test productos.test_imagenes productos.test_imagenes_ambiente kits.test_imagenes --verbosity 2 --keepdb
```

El test histórico `kits.test_listado_recomendaciones` conserva una expectativa HTTP sin HTTPS y en QA puede recibir el redireccionamiento 301 de `SECURE_SSL_REDIRECT`; no se usa como señal de esta integración.
