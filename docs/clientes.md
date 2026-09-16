# Módulo de clientes

## Listado

El listado de clientes está pensado como una vista operativa y no sólo como una tabla de contactos.

Muestra:

- cantidad de clientes activos;
- clientes con saldo pendiente;
- total comprado;
- saldo pendiente total;
- teléfono y email;
- cantidad de pedidos;
- total comprado por cliente;
- saldo de cada cliente;
- último pedido registrado.

La búsqueda filtra por nombre, teléfono o email.

Los pedidos y relaciones necesarias se precargan para evitar consultas repetidas por cada cliente al construir los totales del listado.

## Detalle

La ficha abre siempre en modo consulta. Los campos personales no quedan editables accidentalmente.

El botón con lápiz habilita la edición inline de:

- nombre;
- teléfono;
- email;
- observaciones.

Cancelar vuelve al modo consulta sin guardar. Si una validación falla, la ficha vuelve a abrir en modo edición para poder corregir el dato.

Desde la misma pantalla se conserva la operatoria de pedidos: crear un pedido, editar/cancelar/eliminar cuando corresponde, entregar pedidos listos y registrar pagos.

## Tests

La suite específica se ejecuta con:

```bash
python manage.py test clientes --verbosity 2
```

Los tests aíslan redirección HTTPS, autenticación y almacenamiento de archivos estáticos para validar directamente el comportamiento del módulo.
