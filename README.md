# Doble V 3D

Sistema interno de gestión para **Doble V 3D**, desarrollado con Django para centralizar productos, kits, pedidos, costos, stock y producción de impresiones 3D.

## Funcionalidades principales

- Gestión de productos y tipos de producto.
- Productos simples y compuestos.
- Gestión de kits fijos y kits libres por categoría.
- Clientes y pedidos.
- Stock y movimientos de stock.
- Planificación y seguimiento de producción.
- Gestión de impresoras y estado de impresión.
- Dashboard operativo con información de producción.
- Configuración de costos productivos.
- Calculadora de precios y márgenes.
- Auditoría de operaciones.
- Interfaz responsive para escritorio, tablet y móvil.

## Precios, costos y rentabilidad

El sistema calcula costos productivos considerando, entre otros datos configurados:

- consumo de filamento;
- costo normal de filamento;
- costo de filamento económico para cantidad;
- tiempo de impresión;
- energía;
- amortización;
- tasa de fallos;
- margen configurado por producto.

La lógica de precios utiliza **margen sobre precio de venta**, no solamente recargo sobre costo.

### Filamento económico

El precio normal se mantiene para ventas individuales y cantidades bajas. Para operaciones que califican como venta por cantidad, el sistema puede utilizar el costo de filamento económico configurado.

Si no existe un costo económico válido, se utiliza el costo estándar como respaldo.

### Kits fijos

Los kits de composición fija se calculan como una compra combinada real:

- se suma el costo productivo de todos sus componentes;
- se toma la cantidad total de piezas del kit;
- se ponderan los márgenes de los productos que lo componen;
- los escenarios de precio se calculan sobre el conjunto y no como una simple suma de precios individuales.

Esto permite que un kit combinado pueda tener un precio recomendado menor que comprar sus bloques por separado, sin perder control sobre la rentabilidad.

### Precio por volumen de kits

Desde **5 kits en un mismo pedido**, incluso si son kits diferentes, el sistema evalúa el volumen real de piezas agrupadas para calcular un precio mayorista.

La recomendación técnica no reemplaza el valor comercial configurado para el kit. Si un kit tiene un precio real definido por comparación de mercado, ese precio funciona como **ancla comercial**: el porcentaje de descuento por volumen se obtiene de la referencia técnica y luego se aplica sobre el precio real del kit.

De esta forma, una diferencia entre costo técnico y precio de mercado no se transforma automáticamente en un descuento excesivo.

También se protege un margen mínimo operativo antes de aplicar cualquier reducción.

Más detalle: [`docs/precio-volumen-kits.md`](docs/precio-volumen-kits.md).

## Entornos

El proyecto distingue los entornos mediante `APP_ENV` y las variables provistas por Railway.

- `local`: desarrollo local.
- `qa`: validación de cambios antes de producción.
- `production`: entorno productivo.

La rama `qa` se utiliza para validar cambios y la rama `main` corresponde al código destinado a producción.

> Los cambios deben probarse en QA antes de pasar a `main`.

## Base de datos

En desarrollo local, si no se define `DATABASE_URL`, Django utiliza SQLite.

En Railway se utiliza PostgreSQL mediante `DATABASE_URL`.

### Regla de seguridad de datos

Para refrescar datos de prueba se permite únicamente:

**Production → QA**

Nunca debe copiarse, restaurarse, sincronizarse ni propagarse información en sentido:

**QA → Production**

Production debe tratarse como origen de datos en las operaciones de clonado hacia QA, nunca como destino.

## Instalación local

Requiere Python compatible con las dependencias del proyecto.

```bash
python -m venv .venv
```

Activar el entorno virtual y luego instalar dependencias:

```bash
pip install -r requirements.txt
```

Copiar `.env.example` como referencia y configurar las variables necesarias.

Aplicar migraciones:

```bash
python manage.py migrate
```

Crear un usuario administrador si es necesario:

```bash
python manage.py createsuperuser
```

Ejecutar el servidor local:

```bash
python manage.py runserver
```

La configuración local utiliza `DEBUG=True` por defecto cuando no se está ejecutando dentro de Railway.

## Variables de entorno

Consultar [`.env.example`](.env.example).

Variables relevantes:

- `SECRET_KEY`
- `DEBUG`
- `DATABASE_URL`
- `APP_ENV`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `SECURE_SSL_REDIRECT`

No deben almacenarse contraseñas, claves privadas ni URLs con credenciales reales dentro del repositorio.

## Railway

La aplicación se despliega con Gunicorn y WhiteNoise.

Flujo habitual del servicio Django:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

Las migraciones se ejecutan antes del arranque de la aplicación.

## Tests

Para ejecutar los tests de Django:

```bash
python manage.py test
```

Para validar específicamente la lógica de precio por volumen de kits:

```bash
python manage.py test pedidos.test_kits_volumen --verbosity 2
```

Este conjunto cubre, entre otros casos:

- activación desde 5 kits;
- combinación de distintos kits en un mismo pedido;
- cálculo según cantidad real de piezas;
- kits libres con productos seleccionados;
- aplicación del precio al guardar el pedido;
- conservación del posicionamiento comercial cuando el precio real del kit está por encima de la referencia técnica.

## Estructura principal

```text
auditoria/    Registro y trazabilidad de operaciones
calculadora/  Lógica general de precios y márgenes
clientes/     Gestión de clientes
config/       Configuración Django y middleware
costos/       Configuración de costos productivos
dashboard/    Resumen operativo
kits/         Kits, componentes y recomendaciones
pedidos/      Pedidos, detalle y precios por volumen
produccion/   Planificación e impresión
productos/    Catálogo y composición de productos
stock/        Existencias y movimientos
```

## Convenciones de trabajo

1. Desarrollar y validar cambios fuera de `main`.
2. Llevar los cambios a `qa` para validación funcional.
3. Ejecutar migraciones y tests correspondientes.
4. Verificar el comportamiento responsive cuando haya cambios de interfaz.
5. Pasar a `main` únicamente cuando el cambio esté validado.

---

Proyecto de uso interno de **Doble V 3D**.