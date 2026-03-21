# Diseño: Página de seguimiento de pedido (`/pago_confirmado`)

**Fecha:** 2026-03-21
**Estado:** Aprobado por el usuario

---

## Contexto

`/pago_confirmado` es la última página del flujo del cliente. Actualmente es estática: muestra un resumen básico del pedido y un tiempo estimado fijo ("~15 minutos"). El objetivo es convertirla en una página de seguimiento en tiempo real, útil y coherente con la identidad visual del resto de la web.

---

## Objetivos

- Mostrar el estado actual del pedido con actualización automática cada 15 segundos.
- Informar al cliente de en qué fase está su pedido (preparando → en camino → entregado).
- Mostrar nombre del repartidor, calle de destino y botón de WhatsApp cuando el reparto esté asignado.
- Incluir los items del pedido para que el cliente pueda verificar su compra.
- Mostrar teléfono y dirección del almacén como contacto.
- Usar los tokens de color y componentes visuales del proyecto (`--primary: #FF6B35`, Inter/Manrope, `page-header` naranja) para mantener consistencia de marca.

---

## Diseño visual aprobado

**Estilo:** Tracker vertical estilo app móvil (opción A del brainstorming).

### Estructura de la página

```
[ page-header (naranja, igual que el resto de webs) ]
  Avatar del cliente | Calle de entrega | Badge "Envío gratis"

[ Status hero ]
  Emoji + título del estado + subtítulo + #PedidoID

[ Timeline vertical ]
  ✓ Pedido recibido           (verde, con hora)
  ● Preparando en almacén     (naranja, activo) ← estado actual
  ○ En camino                 (gris, pendiente)
  ○ Entregado                 (gris, pendiente)

[ Tarjeta repartidor ]
  - Si no asignado: aviso "Se asignará cuando esté listo" (fondo naranja claro)
  - Si asignado: avatar + nombre + "En camino a <calle>" + botón WhatsApp verde

[ Sección "Tu pedido" ]
  Lista de items: nombre, badge qty naranja, precio
  Fila total con importe en naranja
  (estáticos — cargados una vez desde Redis al renderizar la página)

[ Sección "Almacén" ]
  📞 Teléfono de contacto
  📍 Dirección del almacén

[ Refresh bar ]
  Punto pulsante naranja + "Actualizando en Xs…"
  (oculto cuando el pedido está en estado terminal)
```

### Estados y su representación visual

| Estado BD (`Pedido.Estado`) | Hero emoji + título | Timeline activo | Polling |
|---|---|---|---|
| `PAGADO` / `CONFIRMANDO_PAGO` | 📦 Pedido recibido, preparando… | Paso 1 activo | ✓ |
| `CONTRA_REEMBOLSO` | 📦 Pedido recibido, preparando… | Paso 1 activo | ✓ |
| `EN_PREPARACION` | 📦 Preparando en almacén | Paso 2 activo | ✓ |
| `PREPARADO` | 📦 Listo, asignando repartidor | Paso 2 completado | ✓ |
| `EN_REPARTO` | 🏍 ¡Tu pedido viene de camino! | Paso 3 activo + tarjeta repartidor | ✓ |
| `ENTREGADO` | ✅ ¡Pedido entregado! | Todos en verde | **se detiene** |
| `CANCELADO` | ❌ Pedido cancelado | Banner rojo, sin timeline | **se detiene** |
| `REEMBOLSADO` | 💸 Pedido reembolsado | Banner gris informativo, sin timeline | **se detiene** |
| Cualquier otro | 📦 Procesando tu pedido | Paso 1 activo | ✓ |

### Colores (tokens del proyecto)

- Activo / badges qty: `--primary` `#FF6B35`
- Completado: `--success` `#22C55E`
- Pendiente: `--border` `#E8E8E8`
- Fondo: `--bg` `#F7F7F7`
- Tarjetas: `--surface` `#FFFFFF`
- Botón WhatsApp: `#25D366` (color oficial de marca, excepción justificada)

---

## Arquitectura técnica

### Cómo llega el `PedidoID` al frontend

La vista `/pago_confirmado` en `blueprints/menu.py` ya recibe `pedidoID=pedido["pedidoID"]` del JSON almacenado en Redis. Este valor es el `PedidoID` entero de SQL Server (no el `redisID` UUID). El template lo inyecta directamente como variable JS:

```html
<script>const PEDIDO_ID = {{ pedidoID }};</script>
```

`blueprints/menu.py` **no necesita cambios**.

### Items del pedido

Los items (`productos`, `total`) se renderizan en el HTML inicial a partir de los datos de Redis. **No viajan en el endpoint de polling** — son estáticos durante toda la página. Esto es correcto porque el pedido ya está confirmado y no cambia.

### Nuevo endpoint de seguimiento

```
GET /api/seguimiento/<pedido_db_id>
```

**Autenticación:** ninguna. El `PedidoID` entero no es predecible externamente (secuencia desde 2000), pero expone datos mínimos (solo estado y datos del repartidor — sin datos personales sensibles del cliente).

**Respuesta exitosa (200):**

```json
{
  "estado": "EN_REPARTO",
  "forma_pago": "online",
  "reparto": {
    "estado": "en_camino",
    "hora_estimada_entrega": "15:05",
    "hora_salida": "14:52",
    "repartidor_nombre": "Carlos Moreno",
    "repartidor_telefono": "612345678",
    "calle_destino": "Calle Mayor 5"
  }
}
```

- Cuando no hay reparto asignado aún: `"reparto": null`
- Pedido no encontrado: `404 {"error": "Pedido no encontrado"}`

**Ubicación:** `blueprints/api.py` (patrón existente).

### Datos del almacén

Teléfono y dirección del almacén como variables de entorno:

```
STORE_PHONE=612345678
STORE_ADDRESS=C/ Ejemplo 12, Madrid
```

Se añaden a `config.py` y se pasan al template en la ruta `/pago_confirmado` de `blueprints/menu.py`.

### Auto-refresco (frontend)

- `setInterval` cada 15 segundos llamando a `GET /api/seguimiento/<PEDIDO_ID>`.
- Actualiza solo el DOM de la sección de estado y tarjeta repartidor (no recarga la página).
- El contador "Actualizando en Xs…" hace cuenta atrás visible.
- El polling se detiene cuando `estado` es `ENTREGADO`, `CANCELADO` o `REEMBOLSADO`.
- Al detectar un cambio de estado, la UI se actualiza sin parpadeo (actualización de clases CSS).

---

## Archivos afectados

| Archivo | Cambio |
|---|---|
| `templates/ver_comandas.html` | Reescritura completa |
| `blueprints/api.py` | Nuevo endpoint `GET /api/seguimiento/<id>` |
| `config.py` | Añadir `STORE_PHONE`, `STORE_ADDRESS` |
| `blueprints/menu.py` | Añadir `store_phone` y `store_address` al `render_template` |
| `.env.example` | Documentar las dos nuevas variables |

> Nota: `blueprints/menu.py` solo necesita los dos nuevos parámetros de config — la ruta y la lógica no cambian.

---

## Pendiente externo (no en este plan)

- El valor real de `STORE_PHONE` y `STORE_ADDRESS` lo configura el operador en producción.
