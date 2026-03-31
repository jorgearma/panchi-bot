# Controllers

Resumen corto de la capa `controllers/`.

## Qué hace esta capa

Los controllers coordinan flujos de negocio.

Su trabajo típico es:

- interpretar intención del usuario,
- validar reglas del flujo,
- mover estados,
- apoyarse en managers y services,
- disparar notificaciones cuando corresponde.

Son la capa más cercana a la lógica conversacional del bot.

## Controllers principales

### `registro.py`

Gestiona el alta conversacional del usuario.

- usa una máquina de estados en Redis,
- pide confirmación inicial,
- recoge nombre,
- valida dirección,
- confirma datos y crea el usuario.

Es el flujo base para pasar de contacto nuevo a cliente operativo.

### `registro_notifier.py`

Contiene los mensajes WhatsApp del flujo de registro.

- bienvenida,
- solicitud de nombre,
- solicitud y confirmación de dirección,
- mensajes de error o reintento.

Separar estos textos ayuda a mantener limpio el orquestador.

### `mensajes_registrados.py`

Gestiona mensajes de usuarios ya registrados.

- recupera usuario y pedido activo,
- decide si abrir pedido nuevo,
- reenvía enlace de pedido o de pago,
- bloquea pedidos duplicados cuando ya hay uno en curso.

Es el router principal del bot para clientes existentes.

### `mensajes_registrados_notifier.py`

Centraliza los mensajes de soporte del flujo anterior.

- errores de usuario o sistema,
- reenvío de enlaces,
- estado del pedido en curso.

### `pedido.py`

Coordina el paso de selección a menú web.

- interpreta la opción escrita por el cliente,
- detecta si debe abrir la tienda online,
- genera enlace único,
- confirma el carrito antes del pago.

Es la bisagra entre WhatsApp y la experiencia web.

### `pago.py`

Orquesta la confirmación económica del pedido.

- valida el carrito contra la BD,
- inicia pago online con Monei,
- o confirma pago en efectivo,
- mueve el pedido al estado correcto.

Aquí vive una parte importante de la protección antifraude.

### `pago_notifier.py`

Envía el mensaje final cuando el pedido queda confirmado en efectivo.

## Patrones que se repiten

- orquestación primero, persistencia después,
- validación de estado antes de cambiar de fase,
- textos de WhatsApp separados en módulos `*_notifier.py`,
- uso de managers para DB/Redis y services para integraciones.

## Regla práctica

Si una función empieza a mezclar acceso directo a infraestructura, armado de mensajes y lógica de transición, conviene separarla en:

- controller para la decisión,
- notifier para el texto,
- manager o service para la operación externa.
