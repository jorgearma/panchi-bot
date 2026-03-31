# Services

Resumen corto de la capa `services/`.

## Qué hace esta capa

`services/` encapsula integraciones externas y utilidades de infraestructura compartida.

Su trabajo típico es:

- hablar con APIs externas,
- construir payloads o URLs,
- envolver SDKs con una interfaz simple,
- aislar credenciales, retries y detalles técnicos.

No debería decidir reglas fuertes de negocio ni estados del pedido.

## Servicios principales

### `__init__.py`

Es el punto de ensamblaje de servicios y gestores compartidos.

- expone instancias listas de `gestor_pedidos`, `gestor_usuarios`, `gestor_productos`, `gestor_dashboard` y `gestor_empleado`,
- reutiliza Redis como `cache`,
- crea el cliente de Monei en lazy loading con `get_monei()`.

Sirve como acceso central para dependencias usadas en varias capas.

### `whatsapp_service.py`

Centraliza el envío de mensajes de WhatsApp.

- soporta `Twilio` y `Meta`,
- elige proveedor con `WHATSAPP_PROVIDER`,
- aplica retries en errores transitorios,
- deja una única función pública: `enviar_mensaje_whatsapp(...)`.

Es una pieza sensible porque conecta con el canal principal del bot.

### `monei_service.py`

Encapsula la creación de pagos online.

- arma el payload para Monei,
- fija `amount`, `order_id`, cliente y dirección,
- construye la `completeUrl`,
- devuelve la URL de redirección o un error controlado.

La intención es que controllers y blueprints no conozcan detalles del SDK.

### `token_service.py`

Genera tokens temporales y enlaces del menú web.

- valida datos de usuario con Pydantic,
- guarda el payload en Redis,
- crea un token corto con expiración,
- devuelve el enlace que abre `/menu/<token>`.

Es la bisagra entre WhatsApp y la experiencia web del cliente.

### `maps_service.py`

Valida y geocodifica direcciones de entrega.

- limpia texto de dirección,
- consulta Google Maps Geocoding,
- comprueba si la coordenada cae dentro del polígono de Tarancón,
- descarta direcciones demasiado generales.

Aquí vive una parte importante de la validación territorial.

## Dependencias externas

- `Twilio` o `Meta WhatsApp API` para mensajería.
- `Monei` para pagos.
- `Google Maps Geocoding API` para direcciones.
- `Redis` para cache y tokens temporales.

## Patrones que se repiten

- inicialización lazy de clientes externos,
- uso de `config` o variables de entorno para credenciales,
- retorno simple tipo `bool`, `tuple` o URL para facilitar consumo,
- retries cuando la integración puede fallar por red o proveedor.

## Puntos sensibles

- `WHATSAPP_PROVIDER` cambia el canal real de salida.
- `PUBLIC_URL` y `completeUrl` afectan al flujo de pago.
- la expiración del token en Redis impacta directamente en el menú web.
- el polígono de Tarancón define qué direcciones se aceptan o rechazan.

## Regla práctica

Si un service empieza a decidir transiciones, validar estados de pedido o mezclar mensajes con negocio, esa parte probablemente debería volver a `controllers/` o `managers/`.
