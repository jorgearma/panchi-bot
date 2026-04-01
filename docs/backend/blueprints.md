# Blueprints

Resumen corto de la capa `blueprints/`.

## Qué hace esta capa

Los blueprints son la entrada HTTP del sistema. Su trabajo ideal es:

- recibir requests,
- validar sesión, firma o parámetros básicos,
- llamar a managers o controllers,
- devolver HTML o JSON.

No deberían concentrar lógica de negocio compleja.

## Blueprints principales

### `auth.py`

Gestiona login, logout y decoradores de acceso.

- decide el rol activo inicial del empleado,
- protege rutas por sesión o por rol,
- redirige al flujo de check-in cuando hace falta.

### `webhook.py`

Es la puerta de entrada de WhatsApp y de pagos.

- recibe mensajes desde Twilio o Meta,
- valida firmas,
- deriva al flujo de `registro` o `mensajes_registrados`,
- procesa confirmaciones de pago desde Monei.

Es uno de los puntos más sensibles del proyecto.

### `menu/`

Sostiene la experiencia web del cliente.

- abre el menú desde un token,
- muestra confirmación de pedido,
- muestra la vista final tras confirmar o pagar.

Trabaja muy pegado a Redis y al estado del pedido.

### `api/`

Expone endpoints usados por el menú web.

- catálogo de productos,
- confirmación de carrito,
- inicio de pago,
- seguimiento del pedido.

Aquí la idea es mantener endpoints simples y delegar la lógica fuerte.

### `dashboard/`

Agrupa las rutas del panel interno.

- monitor y métricas,
- historial y detalle de pedidos,
- planificación de turnos,
- asignación de picking y reparto.

Es la capa de supervisión para manager y admin.

### `picker.py`

PWA operativa para preparación de pedidos.

- lista pickings asignados,
- actualiza líneas de picking,
- busca sustitutos,
- permite coger trabajo de la cola.

### `repartidor.py`

PWA operativa para reparto.

- lista pedidos asignados,
- marca salida, entrega o incidencia,
- registra cobros,
- muestra cierre de caja,
- permite coger repartos pendientes.

### `empleado.py`

Hub del empleado autenticado.

- perfil y métricas,
- estado operativo,
- check-in y cambio de rol,
- fichaje y consulta de turnos.

Es el nexo entre autenticación, capacidades y operación diaria.

### `productos.py`

Panel ligero para administración de catálogo.

- stock,
- disponibilidad,
- precio.

### `metricas_operacion.py`

Da una foto rápida del estado actual del negocio.

- asistencia,
- colas,
- pedidos por estado,
- alertas.

### `metricas_analitica.py`

Expone métricas históricas y comparativas.

- resumen por periodo,
- picking,
- reparto,
- empleados,
- incidencias.

## Patrones que se repiten

- `requiere_rol(...)` para autorización.
- `jsonify(...)` o helpers `_ok/_err` para respuestas uniformes.
- render de plantillas cuando la salida es HTML.
- logs cortos para acciones sensibles.

## Regla práctica

Si una ruta empieza a decidir demasiadas reglas de negocio, probablemente esa lógica debería bajar a `controllers/`, `managers/` o `services/`.
