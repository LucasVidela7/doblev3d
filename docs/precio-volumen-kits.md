# Precio por volumen de kits

La lógica de precio por volumen de kits se activa desde 2 kits en total, aunque sean kits diferentes.

El volumen se calcula con la cantidad real de productos contenidos en los kits del pedido:

- Los kits de composición fija usan sus componentes configurados multiplicados por la cantidad de kits.
- Los kits libres por categoría usan los productos realmente seleccionados en el pedido.
- El costo productivo de los componentes usa el filamento económico de cantidad cuando está configurado.
- El margen objetivo se obtiene de la curva de cantidad usando el total de piezas agrupadas.
- La recomendación conservadora y la curva técnica siguen funcionando como referencia para determinar cuánto descuento tiene sentido liberar.
- Si el precio real ya está por debajo de esa referencia técnica pero todavía conserva margen por encima del piso operativo, la curva usa esa capacidad real disponible para que el descuento comience efectivamente desde la segunda unidad.
- El porcentaje se aplica sobre el precio real configurado del kit y crece progresivamente con la cantidad, con un tope comercial de 15%.
- El precio final intenta conservar el redondeo comercial a $100. Si ese redondeo borrara por completo un descuento válido desde 2 kits, se conserva el importe exacto de la curva para que el beneficio sea real.
- Ninguna línea se descuenta por debajo del margen mínimo operativo.
- Si un precio de lista ya está por debajo del piso rentable, el sistema no lo aumenta automáticamente y tampoco le aplica un descuento adicional.

## Precio acordado con el cliente

Nuevo Pedido y Editar Pedido permiten reemplazar el cálculo automático de una línea KIT por un **precio unitario acordado manualmente**.

Cuando una línea tiene precio acordado:

- el importe manual se persiste como parte del detalle del pedido;
- el cálculo por volumen no puede sobrescribir ese importe;
- el kit continúa contando para la cantidad total de kits y piezas que determina si la compra es mayorista;
- la vista de volumen funciona como referencia y avisa que el precio acordado prevalece.

El botón **Usar precio automático** devuelve la línea a la lógica comercial normal del kit y permite que vuelva a recibir el descuento de volumen correspondiente.

## Edición e historial

Al editar un pedido, los kits libres reconstruyen las posiciones originales aunque haya productos repetidos dentro del mismo kit. Para un kit fijo ya vendido, el backend conserva la composición guardada en el pedido al modificar cantidades, evitando que una actualización posterior de la receta maestra cambie silenciosamente la venta histórica.

Nuevo Pedido y Editar Pedido muestran una vista previa del volumen, precio de lista, precio final, ahorro y margen. Cuando el precio real de mercado modifica el resultado, la vista previa también muestra la referencia técnica utilizada. En las líneas automáticas, el backend vuelve a calcular el precio al guardar y persiste el precio unitario resultante en cada detalle de kit.
