# Doble V Gestión · Android

Aplicación Android interna para Doble V 3D.

## Entorno

Esta rama apunta deliberadamente a **Producción**:

- Inicio: `https://doblev3d.com.ar/gestion/`
- Backend, autenticación y datos: Django/Railway existentes.
- La app no replica lógica de negocio; muestra Gestión dentro de una WebView segura.

## Funciones v1

- Login y sesión persistente mediante cookies de WebView.
- Navegación interna dentro de Doble V 3D.
- WhatsApp, teléfono, mail y sitios externos se abren fuera de la app.
- Selector nativo para subir archivos, incluido G-code/3MF.
- Descargas mediante Download Manager conservando la cookie de sesión.
- Barra superior de progreso de navegación.
- Pantalla simple sin conexión.
- HTTP sin cifrar bloqueado y depuración de WebView desactivada.

## Build

GitHub Actions compila automáticamente la APK al modificar esta rama. La v1 se genera como APK debug para instalación directa y pruebas sobre Producción.

Para una distribución estable con actualizaciones sin reinstalar o para Google Play, crear una clave de firma privada y configurarla como secretos del repositorio; nunca commitear el keystore.
