# UI_MAP.md

> Mapa técnico completo de la interfaz de usuario de **panchi-bot** — templates, rutas, flujos y sistema de diseño.

---

## Índice

1. [Visión General](#1-visión-general)
2. [Árbol de Archivos](#2-árbol-de-archivos)
3. [Rutas y Templates por Blueprint](#3-rutas-y-templates-por-blueprint)
4. [Páginas — Cliente](#4-páginas--cliente)
5. [Páginas — Empleado (Hub y Fichaje)](#5-páginas--empleado-hub-y-fichaje)
6. [Páginas — Picker (PWA)](#6-páginas--picker-pwa)
7. [Páginas — Repartidor (PWA)](#7-páginas--repartidor-pwa)
8. [Páginas — Dashboard (Admin/Manager)](#8-páginas--dashboard-adminmanager)
9. [Páginas — Administración de Productos](#9-páginas--administración-de-productos)
10. [Páginas — Autenticación](#10-páginas--autenticación)
11. [Sistema de Diseño](#11-sistema-de-diseño)
12. [Flujos de Usuario](#12-flujos-de-usuario)
13. [Problemas e Inconsistencias](#13-problemas-e-inconsistencias)

---

## 1. Visión General

El UI está dividido en cuatro audiencias con tecnologías y estilos diferentes:

| Audiencia       | Acceso                     | Tecnología             | Tema         |
|-----------------|----------------------------|------------------------|--------------|
| **Cliente**     | WhatsApp → link único      | HTML/CSS/JS inline     | Naranja      |
| **Picker**      | Login → Hub → PWA          | Tailwind + Alpine.js   | Azul         |
| **Repartidor**  | Login → Hub → PWA          | Tailwind + Alpine.js   | Naranja      |
| **Admin/Manager**| Login → Dashboard          | Tailwind + Alpine.js   | Gris/glass   |

No hay un base template compartido — cada sección tiene su propia estructura HTML completa.

---

## 2. Árbol de Archivos

```
templates/
├── auth/
│   └── login.html                  # Login del personal
├── dashboard/
│   ├── index.html                  # Dashboard principal (admin)
│   ├── monitor.html                # Vista de monitoreo en tiempo real
│   ├── historial.html              # Historial de pedidos
│   ├── turnos.html                 # Gestión de turnos
│   ├── rendimiento.html            # Métricas de rendimiento por empleado
│   ├── estadisticas.html           # Analítica del negocio
│   └── _nav.html                   # Navegación compartida (macro)
├── empleado/
│   ├── index.html                  # Hub operativo del empleado
│   └── checkin.html                # Selector de rol al iniciar turno
├── picker/
│   ├── index.html                  # App de picking (PWA)
│   ├── manifest.json               # Manifiesto PWA
│   └── sw.js                       # Service worker
├── repartidor/
│   ├── index.html                  # App de reparto (PWA)
│   ├── manifest.json               # Manifiesto PWA
│   └── sw.js                       # Service worker
├── productos/
│   └── index.html                  # CRUD de productos (admin)
├── macros/
│   └── ui.html                     # Macros Jinja2 reutilizables
├── quiniela.html                   # Menú interactivo del cliente
├── confirmacion_pago.html          # Resumen de pedido + elección de pago
├── ver_comandas.html               # Seguimiento tras pagar
└── error.html                      # Página de error genérica

static/
├── css/
│   └── styles.css                  # Design tokens + estilos compartidos
├── picker/
│   ├── icon.svg
│   ├── icon-180.png
│   └── icon-192.png
└── repartidor/
    ├── icon.svg
    ├── icon-180.png
    └── icon-192.png
```

---

## 3. Rutas y Templates por Blueprint

### `auth.py`
| Método | Ruta             | Template          |
|--------|------------------|-------------------|
| GET    | `/auth/login`    | `auth/login.html` |
| POST   | `/auth/login`    | `auth/login.html` (con errores) |
| POST   | `/auth/logout`   | redirect → login  |

### `menu.py` (cliente)
| Método | Ruta                    | Template                   |
|--------|-------------------------|----------------------------|
| GET    | `/menu/<token>`         | `quiniela.html`            |
| GET    | `/confirmacion_pago`    | `confirmacion_pago.html`   |
| GET    | `/pago_confirmado`      | `ver_comandas.html`        |

### `api.py` (JSON, sin templates)
| Método | Ruta                              | Descripción                              |
|--------|-----------------------------------|------------------------------------------|
| POST   | `/api/confirmacion`               | Guarda carrito en Redis                  |
| POST   | `/api/agregar_pedido`             | Crea pedido + inicia pago Monei          |
| POST   | `/api/agregar_pedido_efectivo`    | Crea pedido contra reembolso             |
| GET    | `/api/productos`                  | Catálogo en JSON (para el menú)          |
| GET    | `/api/seguimiento/<redis_id>`     | Estado del pedido (polling)              |
| POST   | `/api/cambiar_estado_a_enlace`    | Interno — protegido por token            |

### `dashboard.py`
| Método | Ruta                          | Template                        |
|--------|-------------------------------|---------------------------------|
| GET    | `/dashboard`                  | `dashboard/index.html`          |
| GET    | `/dashboard/monitor`          | `dashboard/monitor.html`        |
| GET    | `/dashboard/historial`        | `dashboard/historial.html`      |
| GET    | `/dashboard/turnos`           | `dashboard/turnos.html`         |
| GET    | `/dashboard/rendimiento`      | `dashboard/rendimiento.html`    |
| GET    | `/dashboard/estadisticas`     | `dashboard/estadisticas.html`   |
| GET    | `/dashboard/metricas`         | JSON                            |
| GET    | `/dashboard/pedidos-activos`  | JSON                            |
| GET    | `/dashboard/picking`          | JSON                            |
| GET    | `/dashboard/repartidores`     | JSON                            |
| GET    | `/dashboard/alertas`          | JSON                            |
| GET    | `/dashboard/eventos`          | JSON (SSE)                      |
| GET    | `/dashboard/mapa`             | JSON                            |
| GET    | `/dashboard/empleados`        | JSON                            |

### `picker.py`
| Método | Ruta                                  | Template / Respuesta          |
|--------|---------------------------------------|-------------------------------|
| GET    | `/picker`                             | `picker/index.html`           |
| GET    | `/picker/manifest.json`               | `picker/manifest.json`        |
| GET    | `/picker/sw.js`                       | `picker/sw.js`                |
| GET    | `/picker/cola`                        | JSON — pedidos disponibles    |
| POST   | `/picker/cola/coger/<id>`             | JSON — asignar pedido         |
| GET    | `/picker/mis-pedidos`                 | JSON                          |
| POST   | `/picker/item/<id>/estado`            | JSON                          |
| GET    | `/picker/buscar-productos`            | JSON                          |
| POST   | `/picker/picking/<id>/finalizar`      | JSON                          |

### `repartidor.py`
| Método | Ruta                                       | Template / Respuesta          |
|--------|--------------------------------------------|-------------------------------|
| GET    | `/repartidor`                              | `repartidor/index.html`       |
| GET    | `/repartidor/manifest.json`                | `repartidor/manifest.json`    |
| GET    | `/repartidor/sw.js`                        | `repartidor/sw.js`            |
| GET    | `/repartidor/cierre`                       | `repartidor/cierre.html`      |
| GET    | `/repartidor/cola`                         | JSON                          |
| POST   | `/repartidor/cola/coger/<id>`              | JSON                          |
| GET    | `/repartidor/mis-pedidos`                  | JSON                          |
| POST   | `/repartidor/reparto/<id>/salida`          | JSON                          |
| POST   | `/repartidor/reparto/<id>/entregar`        | JSON                          |
| POST   | `/repartidor/reparto/<id>/no-entregar`     | JSON                          |
| POST   | `/repartidor/reparto/<id>/registrar-cobro` | JSON                          |
| GET    | `/repartidor/cierre/datos`                 | JSON                          |

### `empleado.py`
| Método | Ruta                          | Template / Respuesta          |
|--------|-------------------------------|-------------------------------|
| GET    | `/empleado`                   | `empleado/index.html`         |
| GET    | `/empleado/checkin`           | `empleado/checkin.html`       |
| GET    | `/empleado/perfil`            | JSON                          |
| GET    | `/empleado/estado`            | JSON                          |
| POST   | `/empleado/cambiar-rol`       | JSON                          |
| POST   | `/empleado/fichaje`           | JSON — iniciar turno          |
| POST   | `/empleado/fichaje/cerrar`    | JSON — cerrar turno           |
| GET    | `/empleado/fichaje/hoy`       | JSON                          |
| GET    | `/empleado/turno-hoy`         | JSON                          |
| GET    | `/empleado/metricas`          | JSON                          |
| GET    | `/empleado/carga-operativa`   | JSON                          |

### `productos.py`
| Método | Ruta                                  | Template / Respuesta      |
|--------|---------------------------------------|---------------------------|
| GET    | `/productos-admin`                    | `productos/index.html`    |
| GET    | `/productos-admin/lista`              | JSON                      |
| POST   | `/productos-admin/<id>/stock`         | JSON                      |
| POST   | `/productos-admin/<id>/disponible`    | JSON                      |
| POST   | `/productos-admin/<id>/precio`        | JSON                      |

---

## 4. Páginas — Cliente

### `quiniela.html` — Menú interactivo
**Ruta:** `GET /menu/<token>`
**Acceso:** Link enviado por WhatsApp (token Redis con TTL)

**Secciones:**
- **Header fijo:** saludo con nombre del cliente, badge "envío gratuito", dirección de entrega
- **Barra de búsqueda:** filtrado en tiempo real por nombre de producto
- **Tabs de categorías:** navegación horizontal scrollable
- **Grid de productos:** tarjeta por producto (imagen, nombre, precio, descuento, botón +/-)
- **Cart sheet:** panel deslizable desde abajo con resumen del carrito, subtotal, botón confirmar

**Estado del carrito:** `sessionStorage` — persiste entre páginas del mismo tab pero no entre sesiones.

**Llamadas JS:**
- `GET /api/productos` — carga el catálogo al inicio
- `POST /api/confirmacion` — al confirmar el carrito → redirige a `/confirmacion_pago`

---

### `confirmacion_pago.html` — Confirmación de pedido
**Ruta:** `GET /confirmacion_pago`

**Secciones:**
- **Resumen del pedido:** lista de ítems con cantidad, precio unitario, botón × para eliminar
- **Total y tiempo estimado:** 15 min, animado con icono pulsante
- **Número de pedido:** `#PedidoID` memorable
- **Notas opcionales:** textarea libre
- **Barra de acciones (fija en bottom):**
  - Botón "Pagar online" → modal de tarjeta
  - Botón "Pagar en efectivo" → modal de contra reembolso

**Modales:**
- **Online:** botón que llama `POST /api/agregar_pedido` → redirige a URL de Monei
- **Efectivo:** botón que llama `POST /api/agregar_pedido_efectivo` → redirige a `/pago_confirmado`

---

### `ver_comandas.html` — Seguimiento del pedido
**Ruta:** `GET /pago_confirmado`

**Secciones:**
- Número de pedido confirmado
- Estado actual (animación de cocina/preparando)
- Icono pulsante con cuenta atrás estimada
- Teléfono de soporte del restaurante

**Polling:** `GET /api/seguimiento/<redis_id>` cada N segundos para actualizar el estado en vivo.

---

## 5. Páginas — Empleado (Hub y Fichaje)

### `empleado/index.html` — Hub operativo
**Ruta:** `GET /empleado`
**Tecnología:** Tailwind CSS + Alpine.js, tema oscuro (`#111827`)

**Secciones:**
- **Header:** nombre del empleado, rol activo, badge de estado operativo (conectado/ocupado/pausa/desconectado)
- **Tarjeta de turno:** hora de inicio/fin del turno planificado, botón fichar entrada/salida
- **Tarjetas de cola:** pedidos pendientes de picking / repartos pendientes (con badge rojo animado si hay cola)
- **Selector de rol** (solo polivalentes): botones picker / repartidor — bloquea si hay tareas activas
- **Accesos rápidos:** enlace a app de picking, app de repartidor
- **Métricas del día:** pedidos completados, tiempo medio, incidencias
- **Acciones secundarias:** rendimiento, turnos, información empresa, cierre de caja, logout
- **Modal de bloqueo:** avisa si hay pedidos activos al intentar cambiar de rol

**Llamadas JS (al cargar):**
- `GET /empleado/perfil`
- `GET /empleado/turno-hoy`
- `GET /empleado/metricas`
- `GET /empleado/carga-operativa`

---

### `empleado/checkin.html` — Selector de rol
**Ruta:** `GET /empleado/checkin`
**Cuándo se usa:** empleados polivalentes que pueden hacer picking y reparto

**Secciones:**
- Saludo con fecha de hoy
- Horario del turno planificado
- Dos tarjetas de rol:
  - **Picker** (gradiente azul): cantidad de pedidos en cola de picking
  - **Repartidor** (gradiente naranja): cantidad de pedidos en cola de reparto
- Estado de carga durante la selección

**Llamadas JS:**
- `GET /empleado/carga-operativa` — para mostrar tamaño de colas
- `POST /empleado/cambiar-rol` → redirige a `/picker` o `/repartidor`

---

## 6. Páginas — Picker (PWA)

### `picker/index.html` — App de preparación
**Ruta:** `GET /picker`
**Tecnología:** Tailwind + Alpine.js, tema azul (`#2563eb`), instalable como PWA

**Vistas (tabs internas controladas por Alpine):**

#### Vista: Mis pedidos
- Lista de pedidos asignados al picker actual
- Cada tarjeta muestra: número de pedido, cliente, dirección, cantidad de ítems
- Al abrir una tarjeta: vista de ticket con ítems individuales

#### Vista: Ticket de pedido
- Item por item del pedido
- Por cada ítem: nombre, cantidad pedida, botones de estado:
  - ✓ Encontrado
  - ✗ Sin stock → abre búsqueda de sustituto
  - ~ Sustituido (tras buscar alternativa)
- Campo de cantidad encontrada (si difiere de la pedida)
- Buscador de productos sustitutos (`GET /picker/buscar-productos`)
- Botón "Finalizar picking" (`POST /picker/picking/<id>/finalizar`) — habilitado cuando todos los ítems tienen estado

#### Vista: Cola de pedidos
- Pedidos disponibles sin picker asignado
- Botón "Coger pedido" (`POST /picker/cola/coger/<id>`)
- Badge con número de pedidos disponibles

**PWA:** `manifest.json` + `sw.js` — soporta offline básico (cachea shell de la app).

---

## 7. Páginas — Repartidor (PWA)

### `repartidor/index.html` — App de reparto
**Ruta:** `GET /repartidor`
**Tecnología:** Tailwind + Alpine.js, tema naranja (`#ea580c`), instalable como PWA

**Vistas (tabs internas):**

#### Vista: Mis entregas
- Lista de repartos asignados al repartidor actual
- Cada tarjeta: número de pedido, dirección, distancia estimada, estado

#### Vista: Detalle de entrega
- Mapa Leaflet.js con marcador de destino y ruta
- Dirección completa, nombre del cliente, teléfono
- Nota del pedido
- Acciones en orden:
  1. "Salir a repartir" (`POST /repartidor/reparto/<id>/salida`)
  2. "Marcar como entregado" (`POST /repartidor/reparto/<id>/entregar`)
  3. "No se pudo entregar" (`POST /repartidor/reparto/<id>/no-entregar`) → motivo requerido
- Cobro presencial: modal que aparece al entregar pedidos de efectivo/contra reembolso
  - `POST /repartidor/reparto/<id>/registrar-cobro`
  - Campos: método (efectivo/tarjeta/mixto), importes, cambio devuelto

#### Vista: Cola de repartos
- Pedidos preparados sin repartidor asignado
- Botón "Coger entrega" (`POST /repartidor/cola/coger/<id>`)

#### Vista: Resumen del día
- Entregas completadas, fallidas, importe cobrado total

### `repartidor/cierre.html` — Cierre de caja
**Ruta:** `GET /repartidor/cierre`
- Resumen de cobros en efectivo del día
- Total esperado vs total cobrado
- Descuadres detectados

**PWA:** `manifest.json` + `sw.js` — soporta offline básico.

---

## 8. Páginas — Dashboard (Admin/Manager)

Todas las vistas comparten `dashboard/_nav.html` como barra de navegación con tabs.

### `dashboard/index.html` — Centro de operaciones
**Ruta:** `GET /dashboard`
**Tecnología:** Tailwind + Alpine.js + glass morphism

**Paneles:**
- **Métricas rápidas:** pedidos activos, en preparación, en reparto, entregados hoy
- **Pipeline de pedidos:** visualización kanban de estados (Pagado → Preparando → Preparado → En reparto)
- **Asignación de picker:** asignar empleado a pedido en preparación
- **Asignación de repartidor:** asignar empleado a pedido preparado
- **Alertas activas:** pedidos con retraso, incidencias abiertas
- **Log de eventos:** stream en tiempo real de cambios de estado

**Llamadas JS (polling/SSE):**
- `GET /dashboard/pedidos-activos`
- `GET /dashboard/picking`
- `GET /dashboard/repartidores`
- `GET /dashboard/alertas`
- `GET /dashboard/eventos` (Server-Sent Events)

---

### `dashboard/monitor.html` — Monitoreo en tiempo real
**Ruta:** `GET /dashboard/monitor`

- Estado operativo de cada empleado (conectado/desconectado/ocupado)
- Métricas del sistema en vivo
- Mapa de entregas activas (`GET /dashboard/mapa`)

---

### `dashboard/historial.html` — Historial de pedidos
**Ruta:** `GET /dashboard/historial`

- Tabla de pedidos con filtros: fecha, estado, cliente, empleado, forma de pago
- Paginación
- Detalle expandible por pedido (ítems, historial de estados, pago)

---

### `dashboard/turnos.html` — Gestión de turnos
**Ruta:** `GET /dashboard/turnos`

- Calendario semanal de turnos por empleado
- Crear/editar/eliminar turno
- Vista de ausencias y solicitudes de cambio pendientes
- Aprobación de solicitudes de cambio de turno

---

### `dashboard/rendimiento.html` — Rendimiento por empleado
**Ruta:** `GET /dashboard/rendimiento`

- Selector de empleado y rango de fechas
- Gráficas: pedidos completados por día, tiempo medio de operación, incidencias
- Tabla de métricas diarias (`metricas_diarias_empleado`)

---

### `dashboard/estadisticas.html` — Analítica del negocio
**Ruta:** `GET /dashboard/estadisticas`

- Ventas por día/semana/mes
- Productos más pedidos
- Horas pico de pedidos
- Tasa de cancelación
- Ingresos por forma de pago (online vs efectivo)

---

## 9. Páginas — Administración de Productos

### `productos/index.html`
**Ruta:** `GET /productos-admin`
**Acceso:** Solo admin

- Tabla de productos con búsqueda
- Por cada producto: ajuste de stock (absoluto o delta), cambio de precio, toggle disponibilidad
- Cambios en tiempo real via JSON API (sin recarga)

---

## 10. Páginas — Autenticación

### `auth/login.html`
**Ruta:** `GET|POST /auth/login`

- Layout split en desktop: historia del negocio (izquierda) + formulario (derecha)
- Mobile: solo formulario
- Campos: email, contraseña
- Mensaje de error en rojo si credenciales incorrectas
- Tras login exitoso: redirige según rol → `/empleado` (picker/repartidor), `/dashboard` (admin/manager)

**Decoradores de protección de rutas:**
- `@requiere_autenticacion` — redirige a login si no hay sesión
- `@requiere_rol('admin', 'manager')` — redirige a login si el rol no está permitido

---

## 11. Sistema de Diseño

### Design tokens (`static/css/styles.css`)

```css
:root {
  --primary:       #FF6B35;    /* naranja principal */
  --primary-dark:  #E85D25;
  --surface:       #FFFFFF;
  --bg:            #F7F7F7;
  --text:          #1A1A1A;
  --text-muted:    #6B6B6B;
  --border:        #E8E8E8;
  --success:       #22C55E;
  --success-dark:  #16A34A;
  --danger:        #EF4444;
  --danger-dark:   #DC2626;
  --radius:        12px;
  --radius-sm:     8px;
  --shadow:        0 2px 8px rgba(0,0,0,0.08);
  --shadow-md:     0 4px 16px rgba(0,0,0,0.12);
}
```

### Tipografía

| Sección                    | Fuente               | Carga         |
|----------------------------|----------------------|---------------|
| Páginas de cliente         | Manrope (headings) + Inter (body) | Google Fonts CDN |
| Apps empleado/dashboard    | Inter (Tailwind default) | Tailwind CDN |

### Stack por sección

| Sección         | CSS         | JS              | Extras              |
|-----------------|-------------|-----------------|---------------------|
| Cliente (menú)  | Inline      | Vanilla JS      | —                   |
| Empleado/Picker/Repartidor | Tailwind CDN | Alpine.js CDN | Leaflet.js (repartidor) |
| Dashboard       | Tailwind CDN | Alpine.js CDN  | Chart.js (gráficas) |
| Auth            | Inline + `styles.css` | —       | —                   |
| Productos       | Tailwind CDN | Alpine.js CDN  | —                   |

### Colores temáticos por rol

| Sección       | Color principal | Fondo           |
|---------------|-----------------|-----------------|
| Cliente       | `#FF6B35` naranja | `#FFFFFF` blanco |
| Picker        | `#2563eb` azul  | Gris claro      |
| Repartidor    | `#ea580c` naranja | Gris cálido   |
| Hub empleado  | Multicolor      | `#111827` oscuro |
| Dashboard     | Gris neutro     | `#F3F4F6` claro |
| Auth          | `#FF6B35` naranja | Blanco/gradiente |

### Animaciones

- Cart sheet: slide-up desde abajo + overlay oscuro
- Modales de pago: fade-in con `backdrop-blur`
- Icono pulsante en seguimiento de pedido: `animate-pulse`
- Badge de cola: brillo animado (`animate-ping`) cuando hay pedidos nuevos
- Botones: `active:scale-95` (Tailwind press effect)

---

## 12. Flujos de Usuario

### Cliente
```
WhatsApp recibe link
        │
        ▼
GET /menu/<token>  →  quiniela.html
        │  (navega, añade al carrito)
        ▼
POST /api/confirmacion
        │
        ▼
GET /confirmacion_pago  →  confirmacion_pago.html
        │
        ├─ [Online] POST /api/agregar_pedido → redirect Monei → POST /webhook/monei → GET /pago_confirmado
        └─ [Efectivo] POST /api/agregar_pedido_efectivo → GET /pago_confirmado
        │
        ▼
GET /pago_confirmado  →  ver_comandas.html  (polling estado)
```

### Picker
```
GET /auth/login → POST /auth/login
        │
        ▼
GET /empleado  →  empleado/index.html
        │  (ficha entrada, selecciona rol picker)
        ▼
GET /picker  →  picker/index.html
        │  (cola → coger pedido → ticket → marcar ítems → finalizar)
        ▼
POST /picker/picking/<id>/finalizar → pedido pasa a PREPARADO
```

### Repartidor
```
GET /auth/login → POST /auth/login
        │
        ▼
GET /empleado  →  empleado/index.html
        │  (ficha entrada, selecciona rol repartidor)
        ▼
GET /repartidor  →  repartidor/index.html
        │  (cola → coger reparto → salida → mapa → entregar/cobrar)
        ▼
POST /repartidor/reparto/<id>/entregar → pedido pasa a ENTREGADO
```

### Admin/Manager
```
GET /auth/login → POST /auth/login
        │
        ▼
GET /dashboard  →  dashboard/index.html
        │  (asigna pickers, asigna repartidores, monitorea alertas)
        ├──  /dashboard/monitor      (estado en tiempo real)
        ├──  /dashboard/historial    (búsqueda de pedidos pasados)
        ├──  /dashboard/turnos       (planificación de horarios)
        ├──  /dashboard/rendimiento  (métricas por empleado)
        └──  /dashboard/estadisticas (analítica del negocio)
```

---

## 13. Problemas e Inconsistencias

### 13.1 No hay base template compartida

Cada sección tiene un HTML completo independiente. No existe un `base.html` con `{% block content %}`. Cambios en el head (meta tags, CDN, favicon) requieren modificar todos los archivos individualmente.

### 13.2 Dos sistemas de estilos coexistentes

- Páginas de cliente usan estilos **inline** (`<style>` en el HTML) + `styles.css`
- Apps de empleados usan **Tailwind CDN** (sin compilar)

Esto implica que los design tokens de `styles.css` (variables CSS) no aplican en los componentes Tailwind, creando divergencias de colores entre secciones del mismo producto.

### 13.3 Tailwind vía CDN (sin compilar)

Todas las apps de empleados cargan Tailwind desde CDN en tiempo de ejecución (`<script src="https://cdn.tailwindcss.com">`). En producción esto:
- Añade ~300 KB por página
- No permite purgar clases no usadas
- Genera un flash of unstyled content en conexiones lentas

### 13.4 Alpine.js vía CDN

Similar a Tailwind — Alpine se carga desde CDN sin bundle ni caché de producción. Cualquier caída del CDN deja las apps sin interactividad.

### 13.5 `confirmacion_pago.html.bak` en templates/

Hay un archivo `.bak` dentro de `templates/`. Flask no lo sirve directamente pero está en el directorio de templates y contamina el árbol. Debería eliminarse o moverse fuera de `templates/`.

### 13.6 Estado del carrito solo en `sessionStorage`

El carrito del cliente vive únicamente en `sessionStorage`. Si el cliente cierra el tab o cambia de navegador, el carrito se pierde. El token de menú (Redis) sigue válido pero el carrito local se vacía.

### 13.7 Leaflet.js solo en repartidor

El mapa de entregas usa Leaflet.js pero solo está incluido en `repartidor/index.html`. Si en el futuro se quiere añadir mapa al dashboard o al cliente, habrá que incluirlo de nuevo manualmente.

### 13.8 Sin manejo de errores de red en las apps PWA

Las llamadas `fetch` en las apps de picker y repartidor no tienen un patrón consistente de manejo de errores de red. Si la API devuelve 500 o hay timeout, en varios casos el error se silencia o la UI queda en estado de carga indefinido.

---

*Generado el 2026-03-23 a partir de `templates/`, `static/` y `blueprints/`.*
