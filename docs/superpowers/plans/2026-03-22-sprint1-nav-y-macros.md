# Sprint 1: Navegación y Macros UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persistent tab navigation to all admin dashboard pages and create reusable Jinja2 UI macros (StatusBadge, EmptyState, LoadingSkeleton, ErrorBanner) that Sprint 2+ screens will import.

**Architecture:** Nav is a Jinja2 `{% include %}` partial that uses `request.path` for active-tab detection — no JS needed. Macros live in `templates/macros/ui.html` and are imported per-template via `{% from %}`. Monitor (`/dashboard/monitor`) uses a dark inline nav strip added directly to its template, since it has its own dark-mode styling that can't share the light-mode partial. No new Flask routes are needed.

**Tech Stack:** Jinja2 (includes + macros), Tailwind CSS (CDN, existing), Alpine.js (error_banner macro uses `x-show`/`x-cloak`).

---

## File Map

| Action | File | Purpose |
|--------|------|---------|
| CREATE | `templates/macros/ui.html` | StatusBadge, EmptyState, LoadingSkeleton, ErrorBanner macros |
| CREATE | `templates/dashboard/_nav.html` | Light-mode nav tabs partial — shared by index + all future screens |
| MODIFY | `templates/dashboard/index.html` | Add `{% include 'dashboard/_nav.html' %}` after the glass-panel `</header>` (line 130), before the alerts block |
| MODIFY | `templates/dashboard/monitor.html` | Replace the "← Dashboard" `<a>` link (lines 67-71, inside the header) with dark-mode tab links inline |
| CREATE | `tests/test_dashboard_sprint1.py` | Tests: nav links present in HTML, macros load in Jinja2 env |

---

## Task 1: Macros UI

**Files:**
- Create: `templates/macros/ui.html`
- Test: `tests/test_dashboard_sprint1.py`

- [ ] **Step 1: Escribir el test que verifica que los macros se cargan en Jinja2**

```python
# tests/test_dashboard_sprint1.py
def test_macros_ui_cargable_en_jinja2(app):
    """El archivo de macros existe y expone los 4 macros esperados."""
    with app.app_context():
        env = app.jinja_env
        template = env.get_template('macros/ui.html')
        modulo = template.module
        assert hasattr(modulo, 'status_badge'), "Falta macro status_badge"
        assert hasattr(modulo, 'empty_state'),  "Falta macro empty_state"
        assert hasattr(modulo, 'loading_skeleton'), "Falta macro loading_skeleton"
        assert hasattr(modulo, 'error_banner'), "Falta macro error_banner"
```

- [ ] **Step 2: Ejecutar test — debe fallar con TemplateNotFound**

```bash
pytest tests/test_dashboard_sprint1.py::test_macros_ui_cargable_en_jinja2 -v
```

Expected: `FAILED` — `TemplateNotFound: macros/ui.html`

- [ ] **Step 3: Crear `templates/macros/ui.html` con los 4 macros**

```jinja2
{#
  templates/macros/ui.html
  Macros reutilizables para el dashboard admin.

  Uso:
    {% from 'macros/ui.html' import status_badge, empty_state, loading_skeleton, error_banner %}

  error_banner depende de Alpine.js:
    - el componente padre debe tener `error` (string | null) en x-data
    - el componente padre debe tener un método `cargar()` para reintentar
#}


{# ─── STATUS BADGE ─────────────────────────────────────────────────────────
   Pinta una pastilla de color según el estado de un pedido o de un empleado.

   Uso: {{ status_badge('EN_PREPARACION') }}
        {{ status_badge(pedido.estado) }}
        {{ status_badge(empleado.estado_operativo) }}
#}
{% macro status_badge(estado) %}
  {% set _conf = {
    'PENDIENTE':         ('bg-slate-100 text-slate-600',    'Pendiente'),
    'ENLACE':            ('bg-slate-100 text-slate-600',    'Enlace'),
    'ENLACE2':           ('bg-slate-100 text-slate-600',    'Enlace 2'),
    'CONFIRMANDO_PAGO':  ('bg-yellow-100 text-yellow-700',  'Confirmando'),
    'PAGADO':            ('bg-emerald-100 text-emerald-700','Pagado'),
    'CONTRA_REEMBOLSO':  ('bg-violet-100 text-violet-700',  'Contrarremb.'),
    'EN_PREPARACION':    ('bg-blue-100 text-blue-700',      'Preparando'),
    'PREPARADO':         ('bg-indigo-100 text-indigo-700',  'Preparado'),
    'EN_REPARTO':        ('bg-orange-100 text-orange-700',  'En reparto'),
    'ENTREGADO':         ('bg-emerald-100 text-emerald-800','Entregado'),
    'CANCELADO':         ('bg-red-100 text-red-700',        'Cancelado'),
    'REEMBOLSADO':       ('bg-slate-100 text-slate-500',    'Reembolsado'),
    'disponible':        ('bg-emerald-100 text-emerald-700','Disponible'),
    'ocupado':           ('bg-blue-100 text-blue-700',      'Ocupado'),
    'en_pausa':          ('bg-yellow-100 text-yellow-700',  'En pausa'),
    'desconectado':      ('bg-slate-100 text-slate-500',    'Desconectado'),
  } %}
  {# Jinja2 no soporta multi-target {% set a, b = tuple %} — desempaquetar manualmente #}
  {% set _default = ('bg-slate-100 text-slate-500', estado) %}
  {% set _tuple = _conf.get(estado, _default) %}
  {% set _clases = _tuple[0] %}
  {% set _etiqueta = _tuple[1] %}
  <span class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold {{ _clases }}">
    {{ _etiqueta }}
  </span>
{% endmacro %}


{# ─── EMPTY STATE ──────────────────────────────────────────────────────────
   Pantalla vacía centrada. Usar cuando una tabla o lista no tiene resultados.

   Parámetros:
     icon        — emoji o símbolo grande (ej. '📭')
     title       — título corto (ej. 'Sin pedidos')
     message     — descripción explicativa
     action_text — texto del botón de acción (opcional)
     action_url  — URL del botón de acción (opcional)

   Uso: {{ empty_state('📭', 'Sin pedidos', 'No hay pedidos para este período.') }}
        {{ empty_state('📭', 'Sin pedidos', 'Prueba otro filtro.', 'Ver todos', '/dashboard/historial') }}
#}
{% macro empty_state(icon, title, message, action_text='', action_url='') %}
  <div class="flex flex-col items-center justify-center py-16 text-center">
    <div class="mb-4 text-5xl leading-none">{{ icon }}</div>
    <p class="text-base font-semibold text-slate-700">{{ title }}</p>
    <p class="mt-1 max-w-xs text-sm text-slate-500">{{ message }}</p>
    {% if action_text and action_url %}
      <a href="{{ action_url }}"
         class="mt-5 rounded-xl bg-slate-950 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-800">
        {{ action_text }}
      </a>
    {% endif %}
  </div>
{% endmacro %}


{# ─── LOADING SKELETON ────────────────────────────────────────────────────
   Filas grises animadas para el estado de carga de tablas.
   Nunca mostrar un spinner solo — el skeleton da contexto visual.

   Parámetros:
     rows — número de filas skeleton (default 5)
     cols — número de columnas por fila (default 5)

   Uso: {{ loading_skeleton() }}
        {{ loading_skeleton(rows=3, cols=4) }}
#}
{% macro loading_skeleton(rows=5, cols=5) %}
  <div class="animate-pulse">
    {% for _r in range(rows) %}
      <div class="flex items-center gap-3 border-b border-slate-100 px-4 py-3">
        {% for _c in range(cols) %}
          <div class="h-4 flex-1 rounded bg-slate-200"></div>
        {% endfor %}
      </div>
    {% endfor %}
  </div>
{% endmacro %}


{# ─── ERROR BANNER ────────────────────────────────────────────────────────
   Banner rojo controlado por Alpine.js.

   Requisitos del componente padre (x-data):
     - `error`   → string con el mensaje, o null cuando no hay error
     - `cargar()` → método que lanza/relanza la petición

   El banner es invisible mientras `error` sea null/falsy.
   El botón "Reintentar" limpia el error y llama a cargar().

   Uso: {{ error_banner() }}
        (colócalo justo después de la FilterBar o antes de la tabla)
#}
{% macro error_banner() %}
  <div x-show="error" x-cloak
       class="flex items-center gap-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
    <span class="text-base leading-none">⚠️</span>
    <span class="flex-1" x-text="error"></span>
    <button @click="error = null; cargar()"
            class="font-semibold underline underline-offset-2 hover:no-underline">
      Reintentar
    </button>
  </div>
{% endmacro %}
```

- [ ] **Step 4: Ejecutar el test — debe pasar**

```bash
pytest tests/test_dashboard_sprint1.py::test_macros_ui_cargable_en_jinja2 -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add templates/macros/ui.html tests/test_dashboard_sprint1.py
git commit -m "feat: add reusable Jinja2 UI macros (status_badge, empty_state, loading_skeleton, error_banner)"
```

---

## Task 2: Nav partial light-mode

**Files:**
- Create: `templates/dashboard/_nav.html`
- Test: `tests/test_dashboard_sprint1.py`

- [ ] **Step 1: Escribir el test que verifica que el parcial existe y es cargable**

Añadir al fichero de tests existente:

```python
def test_nav_partial_cargable_en_jinja2(app):
    """El parcial de navegación existe y Jinja2 puede cargarlo sin error."""
    with app.app_context():
        env = app.jinja_env
        # Lanza TemplateNotFound si el archivo no existe
        template = env.get_template('dashboard/_nav.html')
        assert template is not None
```

- [ ] **Step 2: Ejecutar test — debe fallar con TemplateNotFound**

```bash
pytest tests/test_dashboard_sprint1.py::test_nav_partial_cargable_en_jinja2 -v
```

Expected: `FAILED` — `TemplateNotFound: dashboard/_nav.html`

- [ ] **Step 3: Crear `templates/dashboard/_nav.html`**

```jinja2
{#
  templates/dashboard/_nav.html
  Barra de navegación entre secciones del dashboard admin. Light-mode.

  Uso: {% include 'dashboard/_nav.html' %}
       (incluir justo después del </header> principal de la página)

  La pestaña activa se detecta con request.path.
  En sub-rutas (ej. /dashboard/historial/123) la pestaña padre sigue activa
  gracias al startswith, excepto /dashboard que necesita coincidencia exacta
  para no quedar siempre activo.
#}

{% set _nav_links = [
  ('Operaciones',  '/dashboard'),
  ('Monitor',      '/dashboard/monitor'),
  ('Historial',    '/dashboard/historial'),
  ('Turnos',       '/dashboard/turnos'),
  ('Rendimiento',  '/dashboard/rendimiento'),
  ('Estadísticas', '/dashboard/estadisticas'),
] %}

{#
  IMPORTANT: No usar .glass-panel aquí. Esa clase solo existe en el <style> de index.html
  y no está disponible globalmente. Usar clases Tailwind equivalentes inline para que
  el parcial funcione en cualquier página que lo incluya (historial, turnos, etc.).

  Equivalencia de .glass-panel:
    background: rgba(255,255,255,0.86) → bg-white/80
    backdrop-filter: blur(16px)        → backdrop-blur-lg
    border: 1px solid rgba(148,163,184,0.22) → border border-slate-400/20
    box-shadow: 0 18px 40px ...        → shadow-lg
#}
<nav aria-label="Navegación dashboard"
     class="flex gap-1 overflow-x-auto rounded-2xl border border-slate-400/20 bg-white/80 p-1 shadow-lg backdrop-blur-lg">
  {% for _label, _href in _nav_links %}
    {% if _href == '/dashboard' %}
      {% set _activo = (request.path == '/dashboard') %}
    {% else %}
      {% set _activo = request.path.startswith(_href) %}
    {% endif %}
    <a href="{{ _href }}"
       class="whitespace-nowrap rounded-xl px-4 py-2 text-sm font-semibold transition
              {{ 'bg-slate-950 text-white shadow-sm' if _activo else 'text-slate-600 hover:bg-slate-100 hover:text-slate-900' }}">
      {{ _label }}
    </a>
  {% endfor %}
</nav>
```

- [ ] **Step 4: Ejecutar el test — debe pasar**

```bash
pytest tests/test_dashboard_sprint1.py::test_nav_partial_cargable_en_jinja2 -v
```

Expected: `PASSED`

- [ ] **Step 5: Commit**

```bash
git add templates/dashboard/_nav.html tests/test_dashboard_sprint1.py
git commit -m "feat: add light-mode nav partial for dashboard admin pages"
```

---

## Task 3: Añadir nav a `dashboard/index.html`

**Files:**
- Modify: `templates/dashboard/index.html` — insertar include tras `</header>` (línea 130) en la línea en blanco 131
- Test: `tests/test_dashboard_sprint1.py`

**Contexto:** El header de `index.html` es un `<header class="glass-panel ...">` que cierra en la línea 130 con `</header>`. La nav va entre ese cierre y el bloque de alertas de la línea 132. La ruta `/dashboard` solo llama a `render_template("dashboard/index.html")` sin consultas a BD — el test no necesita mock de base de datos.

- [ ] **Step 1: Escribir test que verifica que la página renderiza los links de nav**

```python
def test_dashboard_index_contiene_links_de_navegacion(client):
    """GET /dashboard renderiza HTML con links a todas las secciones."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    resp = client.get('/dashboard')
    assert resp.status_code == 200
    html = resp.data.decode()

    rutas_esperadas = [
        '/dashboard/historial',
        '/dashboard/turnos',
        '/dashboard/rendimiento',
        '/dashboard/estadisticas',
        '/dashboard/monitor',
    ]
    for ruta in rutas_esperadas:
        assert ruta in html, f"Link '{ruta}' no encontrado en /dashboard"
```

- [ ] **Step 2: Ejecutar test — debe fallar**

```bash
pytest tests/test_dashboard_sprint1.py::test_dashboard_index_contiene_links_de_navegacion -v
```

Expected: `FAILED` — los hrefs de historial/turnos/etc. no están en el HTML

- [ ] **Step 3: Insertar el include en `templates/dashboard/index.html`**

Buscar el bloque exacto (líneas 130-132):

```html
    </header>

    <div x-show="alertasError.length > 0" x-cloak
```

Reemplazarlo por:

```html
    </header>

    {% include 'dashboard/_nav.html' %}

    <div x-show="alertasError.length > 0" x-cloak
```

- [ ] **Step 4: Ejecutar test — debe pasar**

```bash
pytest tests/test_dashboard_sprint1.py::test_dashboard_index_contiene_links_de_navegacion -v
```

Expected: `PASSED`

- [ ] **Step 5: Verificación visual rápida**

Arrancar el servidor dev y abrir `http://0.0.0.0:5000/dashboard`.
Comprobar:
- La barra de tabs aparece entre el header y el bloque de alertas.
- La pestaña "Operaciones" está resaltada (fondo negro).
- Las otras pestañas son grises y tienen hover.
- En móvil (DevTools, 375px) la barra hace scroll horizontal sin wrap.

- [ ] **Step 6: Commit**

```bash
git add templates/dashboard/index.html
git commit -m "feat: add nav tabs to dashboard index page"
```

---

## Task 4: Añadir nav a `dashboard/monitor.html`

**Files:**
- Modify: `templates/dashboard/monitor.html` — reemplazar el link "← Dashboard" (líneas 67-71, dentro del `<header>`) por nav tabs inline con estilo dark
- Test: `tests/test_dashboard_sprint1.py`

**Contexto:** `monitor.html` usa dark mode (`bg-gray-950`). No puede compartir el parcial light-mode. El link "← Dashboard" (líneas 67-71) está dentro del `<div class="flex items-center gap-4">` en el lado derecho del header. Se reemplaza ese link por los tab links con estilo dark, manteniéndose dentro del header.

- [ ] **Step 1: Escribir test que verifica que el monitor renderiza los links de nav**

```python
def test_dashboard_monitor_contiene_links_de_navegacion(client):
    """GET /dashboard/monitor renderiza HTML con links a todas las secciones."""
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = 'admin'

    # La ruta /dashboard/monitor solo hace render_template — sin queries a BD.
    # Alpine.js llama a /dashboard/monitor/datos en el cliente (JS), no en el render.
    resp = client.get('/dashboard/monitor')
    assert resp.status_code == 200
    html = resp.data.decode()

    rutas_esperadas = [
        '/dashboard',
        '/dashboard/historial',
        '/dashboard/turnos',
        '/dashboard/rendimiento',
        '/dashboard/estadisticas',
    ]
    for ruta in rutas_esperadas:
        assert ruta in html, f"Link '{ruta}' no encontrado en /dashboard/monitor"
```

- [ ] **Step 2: Ejecutar test — debe fallar**

```bash
pytest tests/test_dashboard_sprint1.py::test_dashboard_monitor_contiene_links_de_navegacion -v
```

Expected: `FAILED` — solo `/dashboard` existe actualmente (el link "← Dashboard")

- [ ] **Step 3: Modificar `templates/dashboard/monitor.html`**

Buscar el bloque exacto (líneas 67-71):

```html
      <!-- Back to dashboard -->
      <a href="/dashboard"
         class="text-xs text-gray-500 hover:text-orange-400 transition border border-gray-700 rounded px-2 py-1">
        ← Dashboard
      </a>
```

Reemplazarlo por:

```html
      <!-- Navegación entre secciones -->
      {% set _monitor_links = [
        ('Ops',          '/dashboard'),
        ('Monitor',      '/dashboard/monitor'),
        ('Historial',    '/dashboard/historial'),
        ('Turnos',       '/dashboard/turnos'),
        ('Rendimiento',  '/dashboard/rendimiento'),
        ('Estadísticas', '/dashboard/estadisticas'),
      ] %}
      <nav class="flex items-center gap-0.5 overflow-x-auto" aria-label="Navegación dashboard">
        {% for _label, _href in _monitor_links %}
          {% if _href == '/dashboard' %}
            {% set _activo = (request.path == '/dashboard') %}
          {% else %}
            {% set _activo = request.path.startswith(_href) %}
          {% endif %}
          <a href="{{ _href }}"
             class="whitespace-nowrap rounded px-2.5 py-1 text-xs font-semibold transition
                    {{ 'bg-gray-700 text-white' if _activo else 'text-gray-500 hover:text-gray-300 hover:bg-gray-800' }}">
            {{ _label }}
          </a>
        {% endfor %}
      </nav>
```

- [ ] **Step 4: Ejecutar test — debe pasar**

```bash
pytest tests/test_dashboard_sprint1.py::test_dashboard_monitor_contiene_links_de_navegacion -v
```

Expected: `PASSED`

- [ ] **Step 5: Verificación visual rápida**

Abrir `http://0.0.0.0:5000/dashboard/monitor`.
Comprobar:
- Los links aparecen en el header, a la derecha del indicador "EN VIVO".
- La pestaña "Monitor" tiene fondo `bg-gray-700`.
- Las demás son texto gris con hover.
- El "← Dashboard" antiguo ya no está.

- [ ] **Step 6: Ejecutar suite completa para confirmar que nada rompió**

```bash
pytest -v --tb=short
```

Expected: misma cantidad de tests que antes + los 4 nuevos en PASSED.
Los 3 tests `TestWebhookMonei` pre-existentes siguen fallando — es conocido y no bloquea.

- [ ] **Step 7: Commit**

```bash
git add templates/dashboard/monitor.html tests/test_dashboard_sprint1.py
git commit -m "feat: add dark-mode nav tabs to dashboard monitor page"
```

---

## Verificación final de Sprint 1

- [ ] Ejecutar suite completa: `pytest -v --tb=short`
- [ ] Confirmar que los 4 nuevos tests pasan
- [ ] Confirmar que no se introdujeron regresiones
- [ ] Abrir `/dashboard` y `/dashboard/monitor` en un navegador y verificar visualmente las tabs

**Trade-off conocido:** La lista de tabs está duplicada — una vez en `_nav.html` (`_nav_links`) y otra vez inline en `monitor.html` (`_monitor_links`). Es una consecuencia aceptada de que monitor usa dark-mode y no puede compartir el parcial. Si se añade una pestaña nueva en el futuro, hay que editar los dos archivos. Se documenta aquí para que no sorprenda.

**Entregables del sprint:**
- `templates/macros/ui.html` — listo para importar en Sprint 2+
- `templates/dashboard/_nav.html` — listo para incluir en nuevas páginas con `{% include 'dashboard/_nav.html' %}`
- `/dashboard` y `/dashboard/monitor` con navegación funcional
- 4 tests nuevos en `tests/test_dashboard_sprint1.py`
