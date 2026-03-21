# Spec: Rediseño de confirmacion_pago.html

**Fecha:** 2026-03-21
**Archivo objetivo:** `templates/confirmacion_pago.html`
**Estado:** Aprobado

---

## Objetivo

Rediseñar la página de confirmación de pedido para mejorar la claridad de los artículos, añadir un campo de indicaciones de entrega y modernizar la cabecera y los botones de pago, manteniendo la paleta de colores del proyecto.

---

## Paleta de colores (tokens existentes)

| Token | Valor | Uso |
|-------|-------|-----|
| `--primary` | `#FF6B35` | Cabecera, badges de cantidad, botón online |
| `--primary-dark` | `#E85D25` | Sombras y hover |
| `--success` | `#22C55E` | Badge envío gratis, botón efectivo |
| `--danger` | `#EF4444` | Botón quitar unidad |
| `--bg` | `#F7F7F7` | Fondo general |
| `--surface` | `#FFFFFF` | Tarjetas |
| `--border` | `#E8E8E8` | Bordes |
| `--text` | `#1A1A1A` | Texto principal |
| `--text-muted` | `#6B6B6B` | Texto secundario |

Fuentes: `Inter` (cuerpo), `Manrope` (títulos y valores numéricos importantes).

> **Nota de importación:** añadir `900` a la carga de Manrope en el `<link>` de Google Fonts:
> `family=Manrope:wght@700;800;900`

---

## Estructura de la página

```
┌─────────────────────────────────────┐
│ CABECERA (gradiente naranja)        │
│  Fila 1: [Hola, {nombre} 👋] [✓ Envío gratis] │
│  Fila 2: [📍 Dirección de entrega — {calle}]  │
├─────────────────────────────────────┤
│ TARJETA DE PEDIDO                   │
│  Cabecera: "Tu pedido" + #ID        │
│  Lista de artículos (filas)         │
│  Campo de indicaciones (opcional)   │
│  Total                              │
├─────────────────────────────────────┤
│ TIEMPO ESTIMADO (animado)           │
├─────────────────────────────────────┤
│ ACTION BAR (fija abajo)             │
│  [← Volver]  [💳 Online ›]  [🪙 Al recibir ›] │
└─────────────────────────────────────┘
```

---

## Componentes

### 1. Cabecera

- **Fondo:** gradiente `linear-gradient(135deg, #FF6B35, #FF4500)`
- **Border-radius inferior:** `24px` (redondeado solo abajo)
- **Círculos decorativos:** dos blobs translúcidos via `::before` / `::after`
- **Fila 1:** `display: flex; justify-content: space-between`
  - Izquierda: `"Hola, {{ name.split()[0] }} 👋"` — Manrope 900, 19px, blanco, pegado al borde
  - Derecha: badge `"✓ Envío gratis"` — fondo `--success`, border-radius pill, pegado al borde
- **Fila 2:** caja translúcida `rgba(255,255,255,0.15)` con borde `rgba(255,255,255,0.25)`, border-radius 12px, ancho completo
  - Icono 📍 en cuadrado redondeado `rgba(255,255,255,0.2)`
  - Etiqueta "DIRECCIÓN DE ENTREGA" en 9px mayúsculas + dirección en Manrope 800 13px blanco

### 2. Tarjeta de pedido

- Fondo `--surface`, border-radius `--radius` (12px), sombra `--shadow`
- **Cabecera de tarjeta:** "Tu pedido" (Manrope 800) + `#{pedidoID}` en pill gris a la derecha
- **Lista de artículos:** cada fila contiene:
  - Badge naranja con cantidad (Manrope 800, border-radius 7px)
  - Nombre del artículo (Inter 600)
  - Precio total del artículo
  - Botón `−` rojo (`#FEE2E2` / `--danger`) que quita una unidad; si llega a 0 elimina la fila
- **Campo de indicaciones** (dentro de la tarjeta, antes del total):
  - Etiqueta "✏️ Indicaciones de entrega (opcional)"
  - Fondo `#FFF8F5`, borde `#FFD5C2`, border-radius 8px
  - `<textarea id="notas">` con placeholder: `"Ej: no tocar el timbre, dejar en portería…"`
  - Máx. 300 caracteres; se envía como campo `notas` en el JSON del pedido
- **Total:** separador dashed + importe en Manrope 900, 15px, actualizado dinámicamente

### 3. Tiempo estimado (animado)

- Tarjeta `--surface` con border `--border`, border-radius 12px
- **Icono:** círculo naranja con ⏱ en el centro + dos anillos concéntricos que irradian (`::before` / `::after`) con `animation: ring-out 2s ease-out infinite`
- **Texto:** etiqueta "Tiempo estimado de entrega" (10px muted) + valor "~15 minutos" (Manrope 900)
- **Puntos latiendo:** tres dots naranjas alineados a la derecha, `animation: dot-beat 1.4s ease-in-out infinite` con delays escalonados (0s, 0.2s, 0.4s)

### 4. Action bar (fija)

- `position: fixed; bottom: 0; left: 0; right: 0` con fondo `--surface` y borde superior; el contenedor de scroll debe tener `padding-bottom` igual a la altura de la action bar para que el contenido no quede tapado
- **[← Volver]:** botón secundario `--bg` con borde `--border`; llama a `handleBack()` existente
- **[💳 Online ›]:** pill alargado naranja (`--primary`) con icono 💳 a la izquierda, texto "Online / Pago seguro" y flecha `›`; abre `modalOnline` (`id="modal-online"`)
- **[🪙 Al recibir ›]:** pill alargado verde claro (`#F0FDF4`) con borde `--success`; abre `modalEfectivo` (`id="modal-efectivo"`)

### 5. Modal de confirmación (bottom sheet)

Aparece al pulsar cualquier botón de pago. Fondo de página con `filter: blur(2px)` + overlay `rgba(0,0,0,0.45)`.

**Estructura del sheet:**
- Handle pill gris centrado arriba
- Icono grande (💳 o 🪙) en cuadrado redondeado de color suave
- Título: "¿Confirmas el pago online?" / "¿Confirmas el pedido?"
- Subtexto explicativo breve
- Resumen con total en naranja (Manrope 900)
- Botón de confirmación (naranja u verde según método)
- Enlace "Cancelar, volver al pedido"

**Endpoints:**
- Modal online → `submitOrder('/api/agregar_pedido')`
- Modal efectivo → `submitOrder('/api/agregar_pedido_efectivo')`

**Flujo de botones:**
1. El usuario pulsa un botón de pago en la action bar → se abre el modal correspondiente; los botones de la action bar permanecen activos (el usuario puede cerrar el modal y elegir otro método).
2. El usuario pulsa "Confirmar" en el modal → se deshabilita el botón de confirmación del modal (anti doble-envío) y se llama `submitOrder`.
3. Si `submitOrder` falla → se rehabilita el botón de confirmación del modal.

**Implementación:** dos `<div>` ocultos (`display:none`) con ids `modal-online` y `modal-efectivo`, que se muestran con `classList.add('visible')`. Sin dependencias externas.

---

## Comportamiento JavaScript

### Funciones existentes (conservar)

| Función | Descripción |
|---------|-------------|
| `quitarUnidad(btn)` | Quita 1 unidad; elimina fila si llega a 0 |
| `recalcularTotal()` | Recalcula total desde el DOM |
| `handleBack()` | Guarda carrito en sessionStorage, llama `/api/volver_al_menu`, navega a `/menu/{token}` |
| `buildOrder()` | Construye objeto de pedido desde el DOM |
| `submitOrder(endpoint, confirmBtn)` | POST al endpoint; deshabilita `confirmBtn` al inicio, lo rehabilita en `catch`; gestiona redirect y errores |

### Cambios

**`buildOrder()`**
- Incluye nuevo campo `notas: document.getElementById('notas').value.trim()`
- Sigue retornando `null` si `#productos li` está vacío (guard conservado)

**Guard de carrito vacío — se mueve al handler del botón de action bar:**
```js
function abrirModal(modalId) {
  if (!buildOrder()) {          // null = carrito vacío
    alert('No hay productos en el pedido.');
    return;
  }
  document.getElementById(modalId).style.display = 'flex';
}
```
Los botones de la action bar llaman `abrirModal('modal-online')` / `abrirModal('modal-efectivo')`.

**`submitOrder(endpoint, confirmBtn)`** — nueva firma con parámetro `confirmBtn`:
- El handler de cada modal pasa su propio botón de confirmación
- `submitOrder` deshabilita `confirmBtn` al inicio y lo rehabilita en el `catch`
- **Eliminar** el bloque existente que deshabilita `pagarOnline` / `pagarEfectivo` (líneas 177-180 del template actual) — en el nuevo flujo los botones de la action bar nunca se deshabilitan

**`public_url`** — sigue siendo una variable JS inline en el template: `'{{ public_url }}'`; no cambia su uso dentro de `submitOrder`.

Modal online → `submitOrder('/api/agregar_pedido', confirmBtn)`
Modal efectivo → `submitOrder('/api/agregar_pedido_efectivo', confirmBtn)`

- `{{ token }}` en `sessionStorage` key `cart_{{ token }}`; conservado sin cambios

---

## Datos del template (variables Jinja2)

Todas las variables son inyectadas por `blueprints/menu.py` → `mostrar_confirmacion()` via `render_template("confirmacion_pago.html", ...)`. `pedidoID` proviene de `pedido["pedidoID"]` almacenado en Redis.

| Variable | Uso |
|----------|-----|
| `{{ name.split()[0] }}` | Primer nombre del cliente, en el saludo del header |
| `{{ calle }}` | Dirección corta mostrada en el header |
| `{{ direccion }}` | Dirección completa enviada en el JSON del pedido via `buildOrder()` |
| `{{ pedidoID }}` | ID del pedido mostrado en la cabecera de la tarjeta |
| `{{ productos }}` | Lista de productos con `codigo`, `nombre`, `cantidad`, `precio` |
| `{{ total }}` | Total inicial renderizado en el DOM |
| `{{ token }}` | Token de sesión; usado en `sessionStorage` key (`cart_{{ token }}`) y en `handleBack()` |
| `{{ userID }}` | ID de usuario enviado en `buildOrder()` |
| `{{ numero }}` | Número de teléfono WhatsApp enviado en `buildOrder()` |
| `{{ public_url }}` | URL base para las peticiones `fetch` |

---

## Archivos afectados

| Archivo | Cambio |
|---------|--------|
| `templates/confirmacion_pago.html` | Reescritura completa del HTML/CSS/JS |
| `static/css/styles.css` | Sin cambios (se usan los tokens existentes) |
| `models.py` | Añadir columna `Notas = Column(String(300), nullable=True)` a la clase `Pedido` |
| `blueprints/api.py` | En `agregar_pedido()` y `agregar_pedido_efectivo()`: leer `notas = data.get("notas", "")` y pasarlo como parámetro `notas=notas` a `iniciar_pago()` / `iniciar_pago_efectivo()` |
| `controllers/pago.py` | Añadir parámetro `notas: str = ""` a `iniciar_pago()` e `iniciar_pago_efectivo()`; asignar `pedido.Notas = notas` antes del `db.commit()` final |

> **Nota:** el campo `notas` se persiste en `Pedido.Notas` para que el personal (picker/repartidor) pueda consultarlo. La columna se añade con `ALTER TABLE pedidos ADD Notas NVARCHAR(300) NULL` (SQL Server); SQLAlchemy la crea automáticamente si se usa `Base.metadata.create_all()` en entornos de prueba.

---

## Criterios de aceptación



- [ ] La cabecera muestra gradiente naranja con bordes redondeados abajo, saludo y badge en fila 1, dirección en fila 2
- [ ] Cada artículo tiene badge de cantidad naranja y botón `−` que quita una unidad
- [ ] El campo de notas es visible dentro de la tarjeta, antes del total, y su valor se envía en el JSON
- [ ] El total se recalcula correctamente al quitar unidades
- [ ] El tiempo estimado muestra la animación de pulso y los puntos latiendo
- [ ] Al pulsar cualquier botón de pago aparece el modal de confirmación (bottom sheet)
- [ ] El modal muestra el total y el método de pago seleccionado
- [ ] Confirmar en el modal envía el pedido; cancelar cierra el modal sin enviar
- [ ] Solo el botón de confirmación del modal se deshabilita durante el envío; se rehabilita si hay error
- [ ] Si el carrito queda vacío (todos los artículos eliminados), al pulsar un botón de pago se muestra alerta y no se abre el modal
- [ ] La página funciona correctamente en móvil (viewport ≤ 390px)
- [ ] El contenido no queda tapado por la action bar fija en pantallas pequeñas
- [ ] La fuente Manrope se carga con pesos 700, 800 y 900 (verificable en DevTools → Network → Fonts)
- [ ] El campo `notas` del JSON llega al backend y se persiste en `Pedido.Notas`
