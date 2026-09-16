# Stock real en Impresiones por producto

La pantalla **Impresiones por producto** debe mostrar y utilizar el stock real de la unidad física que se imprime.

## Regla

- Producto simple: usa `Producto.stock`.
- Producto compuesto: primero descuenta el stock del producto terminado; si debe fabricar unidades nuevas, expande la necesidad a sus piezas.
- Pieza de producto compuesto: usa el `stock` real de esa pieza para reducir la necesidad estándar de impresión.
- Personalizados: no consumen stock genérico; continúan como fabricación específica.
- Producciones `PENDIENTE` e `IMPRIMIENDO` siguen descontándose al calcular cuánto falta iniciar/planificar.

Ejemplo: si un compuesto requiere 2 piezas por unidad, hay un pedido de 2 unidades y la pieza tiene stock 3, la necesidad física es 4, el stock mostrado es 3 y **A imprimir** es 1.

## Regresión

```bash
python manage.py test pedidos.test_impresiones_stock pedidos.test_planificacion_productos --verbosity 2 --keepdb
```
