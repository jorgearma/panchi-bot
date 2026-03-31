# Backend Overview

Documento común del backend de `panchi-bot`.

La idea de esta guía es dar una visión única del sistema sin obligarte a saltar entre `blueprints`, `controllers`, `services`, `maps/` y el código real.

## Qué es este proyecto

`panchi-bot` es un sistema de pedidos para restaurante con dos caras principales:

- el cliente entra por WhatsApp, abre un menú web, confirma el pedido y paga,
- el equipo interno opera el pedido desde panel, picking, reparto y fichaje.

El sistema mezcla conversación, web, operación interna y métricas sobre una misma base de datos.

## Núcleo real del sistema

Si quieres entender la base del proyecto, estos archivos son la fuente de verdad:

- [main.py](../../main.py): arranque, registro de blueprints, healthcheck y manejo global de errores.
- [container.py](../../container.py): ensamblaje real de gestores compartidos y cliente Monei.
- [models.py](../../models.py): entidades del negocio y relaciones ORM.
- [states.py](../../states.py): estados y transiciones válidas de registro, pedido, picking y reparto.
- [database.py](../../database.py): sesión SQLAlchemy por request.
- [config.py](../../config.py): variables de entorno y configuración sensible.

## Arquitectura en una frase

El proyecto sigue este flujo:

`blueprints -> controllers -> managers -> services -> externos`

Pero en la práctica hay dos rutas principales:

- flujo cliente: WhatsApp + menú web + pago,
- flujo interno: dashboard + picker + repartidor + empleado.

Ambos comparten estados, base de datos y managers.

## Capas y responsabilidad

### `blueprints/`

Gestionan HTTP.

- reciben requests,
- validan sesión, firma o parámetros básicos,
- llaman a la capa adecuada,
- devuelven HTML o JSON.

Los blueprints más sensibles son:

- [webhook.py](../../blueprints/webhook.py)
- [api/payments.py](../../blueprints/api/payments.py)
- [auth.py](../../blueprints/auth.py)

### `controllers/`

Orquestan el flujo conversacional y el negocio del pedido.

- registro de usuarios,
- gestión de mensajes de clientes ya registrados,
- apertura de menú,
- confirmación de carrito,
- inicio de pago online o contra entrega.

### `managers/`

Son la capa de datos y operación interna.

Hay cuatro gestores principales:

- [gestor_pedidos.py](../../managers/gestor_pedidos.py): ciclo de vida del pedido.
- [gestor_dashboard.py](../../managers/gestor_dashboard.py): pedidos activos, picking, reparto, turnos y rendimiento.
- [gestor_empleado.py](../../managers/gestor_empleado.py): perfil, roles, fichaje y métricas del empleado.
- [gestor_metricas.py](../../managers/gestor_metricas.py): tiempo real, analítica e indicadores de empleados.

Además, [estado_usuario.py](../../managers/estado_usuario.py) sostiene la máquina de estados del registro sobre Redis.

### `services/`

Aíslan integraciones externas.

- WhatsApp por Twilio o Meta,
- pagos con Monei,
- tokens temporales del menú,
- validación y geocodificación de direcciones.

## Dominios de negocio

### Cliente

- `usuarios`
- registro por WhatsApp
- token temporal para abrir el menú

### Pedido

- `pedidos`
- `pedido_detalles`
- `pagos`
- `historial_estados_pedido`

Es el centro del sistema y conecta cliente, picking, reparto y métricas.

### Operación interna

- `picking_pedido`
- `picking_items`
- `repartos`
- `incidencias`

Aquí vive la ejecución real del pedido una vez confirmado.

### RRHH y operación del personal

- `empleados`
- `roles`
- `empleado_capacidades`
- `turnos`
- `check_ins`
- `ausencias`
- `metricas_diarias_empleado`

## Estados que mandan el sistema

El archivo [states.py](../../states.py) es clave porque define qué cambios están permitidos.

### Registro

Flujo corto en Redis:

`saludo_inicial -> esperando_confirmacion -> esperando_nombre -> esperando_direccion -> confirmando_direccion`

### Pedido

Flujo principal:

`Pendiente -> enlace -> enlace2 -> confirmando-pago -> pagado/contra_reembolso -> en_preparacion -> preparado -> en_reparto -> entregado`

Y además:

- `cancelado`
- `reembolsado`

### Picking

`pendiente -> en_proceso -> completado`

Con variantes:

- `con_incidencias`
- `cancelado`

### Reparto

`pendiente -> asignado -> en_camino -> entregado`

Y también:

- `no_entregado`
- `cancelado`

## Flujos principales

### 1. Registro de usuario nuevo

- entra por [webhook.py](../../blueprints/webhook.py)
- pasa a [registro.py](../../controllers/registro.py)
- usa Redis vía [estado_usuario.py](../../managers/estado_usuario.py)
- valida dirección con [maps_service.py](../../services/maps_service.py)
- persiste el usuario en SQL Server

### 2. Pedido online

- el cliente escribe por WhatsApp
- [mensajes_registrados.py](../../controllers/mensajes_registrados.py) decide si abrir menú o reenviar enlace
- [token_service.py](../../services/token_service.py) crea el token del menú
- [menu/](../../blueprints/menu) renderiza la experiencia web
- [api/payments.py](../../blueprints/api/payments.py) inicia el pedido
- [pago.py](../../controllers/pago.py) valida el carrito y llama a [monei_service.py](../../services/monei_service.py)
- [webhook.py](../../blueprints/webhook.py) confirma el pago y mueve el estado a `pagado`

### 3. Pedido contra reembolso

Es parecido al anterior, pero en vez de crear pago online:

- confirma el pedido,
- guarda forma de pago,
- lo deja listo para operación interna.

### 4. Picking

- el pedido confirmado genera o reutiliza un `PickingPedido`
- la PWA de [picker.py](../../blueprints/picker.py) muestra cola y pickings asignados
- [gestor_dashboard.py](../../managers/gestor_dashboard.py) asigna, reclama, actualiza ítems y completa el picking
- al completar, el pedido pasa a `preparado`

### 5. Reparto

- la PWA de [repartidor.py](../../blueprints/repartidor.py) permite coger cola, salir a reparto, cobrar y cerrar
- el reparto usa `repartos` como entidad operativa
- al salir, el pedido pasa a `en_reparto`
- al entregar, pasa a `entregado`

### 6. Operación interna y personal

- [dashboard/](../../blueprints/dashboard) supervisa pedidos, turnos, rendimiento y estadísticas
- [empleado.py](../../blueprints/empleado.py) resuelve perfil, carga operativa, fichaje y cambio de rol
- [gestor_empleado.py](../../managers/gestor_empleado.py) y [gestor_metricas.py](../../managers/gestor_metricas.py) sostienen estas vistas

## Dónde está cada fuente de verdad

- estructura del negocio: [models.py](../../models.py)
- reglas de transición: [states.py](../../states.py)
- dependencias compartidas: [container.py](../../container.py)
- configuración y secretos: [config.py](../../config.py)
- documentación profunda: [PROJECT_MAP.md](../../maps/PROJECT_MAP.md), [DB_MAP.md](../../maps/DB_MAP.md), [UI_MAP.md](../../maps/UI_MAP.md), [QUERY_MAP.md](../../maps/QUERY_MAP.md)

## Cómo leer el repo sin perderte

Si quieres entender el proyecto con orden, este camino suele funcionar bien:

1. [overview.md](./overview.md)
2. [main.py](../../main.py)
3. [container.py](../../container.py)
4. [models.py](../../models.py)
5. [states.py](../../states.py)
6. `blueprints` del flujo que quieras seguir
7. `controllers` y `managers` implicados

## Si buscas algo concreto

- login y permisos: [auth.py](../../blueprints/auth.py)
- entrada de mensajes y pagos: [webhook.py](../../blueprints/webhook.py)
- pedido y pago: [pedido.py](../../controllers/pedido.py), [pago.py](../../controllers/pago.py)
- operaciones internas: [gestor_dashboard.py](../../managers/gestor_dashboard.py)
- métricas: [gestor_metricas.py](../../managers/gestor_metricas.py)
- validación de dirección: [maps_service.py](../../services/maps_service.py)
- tokens y menú: [token_service.py](../../services/token_service.py)

## Puntos sensibles del sistema

- firmas de webhooks en [webhook.py](../../blueprints/webhook.py)
- token interno del frontend en rutas `api`
- estados del pedido y sus transiciones
- expiración de tokens en Redis
- rutas administrativas y permisos por rol

## Idea clave

El proyecto no es solo un bot ni solo un dashboard.

Es un sistema de estados compartidos donde:

- WhatsApp abre el flujo,
- web confirma el pedido,
- operaciones internas ejecutan el trabajo,
- métricas y dashboard observan el resultado.

Si entiendes `models.py`, `states.py`, `container.py` y los flujos `webhook -> pedido/pago -> picking -> reparto`, entiendes casi todo el sistema.
