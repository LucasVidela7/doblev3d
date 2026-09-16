# Precio por volumen de kits

La lógica de precio mayorista de kits se activa cuando un pedido contiene 6 o más kits en total, aunque sean kits diferentes.

El volumen se calcula con la cantidad real de productos contenidos en los kits del pedido:

- Los kits de composición fija usan sus componentes configurados multiplicados por la cantidad de kits.
- Los kits libres por categoría usan los productos realmente seleccionados en el pedido.
- El costo productivo de los componentes usa el filamento económico de cantidad cuando está configurado.
- El margen objetivo se obtiene de la curva de cantidad usando el total de piezas agrupadas.
- Ninguna línea se descuenta por debajo del margen mínimo operativo.
- Si un precio de lista ya está por debajo del piso rentable, el sistema no lo aumenta automáticamente y tampoco le aplica un descuento adicional.

Nuevo Pedido y Editar Pedido muestran una vista previa del volumen, precio de lista, precio final, ahorro y margen. El backend vuelve a calcular el precio al guardar y persiste el precio unitario resultante en cada detalle de kit.
