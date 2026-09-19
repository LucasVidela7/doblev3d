# Pendientes Doble V 3D

## Analítica del catálogo

- [ ] Implementar métricas internas del catálogo con una tabla liviana `EventoCatalogo`.
- [ ] Registrar únicamente eventos comerciales útiles: visita, agregar al carrito, quitar del carrito, iniciar checkout, enviar solicitud y contacto.
- [ ] Usar una sesión anónima para relacionar eventos sin repetir datos personales.
- [ ] Evitar registrar cada cambio de cantidad o cada clic para mantener bajo el volumen de datos.
- [ ] Crear una pantalla de métricas con períodos de 7, 30 y 90 días.
- [ ] Medir el embudo: visitas → carritos → checkout → solicitudes → presupuestos → pedidos.
- [ ] Mostrar conversión, abandono, ticket promedio y productos/kits más vistos, agregados y abandonados.
- [ ] Mantener `RegistroAuditoria` para trazabilidad administrativa y usar `EventoCatalogo` exclusivamente para analytics.
- [ ] Evaluar una política de retención de eventos crudos (por ejemplo 12 meses) y luego resumirlos por período.
- [ ] Dejar preparado el diseño para integrar PostHog u otro proveedor externo más adelante, sin depender de él para el histórico comercial.
