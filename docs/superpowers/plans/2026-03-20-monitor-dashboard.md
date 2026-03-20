# Monitor Dashboard — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir un Pipeline Kanban al monitor de operaciones y mejorar alertas, KPI bar y feed de actividad para que el encargado identifique cuellos de botella de un vistazo.

**Architecture:** Un cambio mínimo en backend (exponer `pedidos_activos()` en el endpoint del monitor) y cuatro bloques de cambios en el template HTML/Alpine.js existente. No se crean nuevos archivos — todo va en los dos ficheros que ya existen. El monitor sigue siendo solo lectura, sin acciones.

**Tech Stack:** Flask, SQLAlchemy, Alpine.js 3.x, Tailwind CSS (CDN). Tests con pytest + fakeredis.

---

## Archivos involucrados

| Fichero | Tipo | Qué cambia |
|---------|------|------------|
| `blueprints/dashboard.py` | Modificar | Añadir `pedidos_pipeline` al endpoint `/dashboard/monitor/datos` |
| `templates/dashboard/monitor.html` | Modificar | Pipeline Kanban, banner unificado, badge header, tooltip ingresos, feed cancelados |
| `tests/test_gestor_dashboard.py` | Modificar | Test de regresión para el campo `pedidos_pipeline` en el endpoint |

---

## Task 1: Backend — exponer `pedidos_pipeline` en el endpoint del monitor

**Files:**
- Modify: `blueprints/dashboard.py:63-79`
- Test: `tests/test_gestor_dashboard.py`

- [ ] **Step 1: Escribir el test que debe fallar**

Añadir al final de `tests/test_gestor_dashboard.py`:

```python
def test_monitor_datos_incluye_pedidos_pipeline(client, app):
    """El endpoint /dashboard/monitor/datos expone pedidos_pipeline como lista."""
    from unittest.mock import patch, MagicMock
    from services import gestor_dashboard

    # Mock gestor_dashboard.pedidos_activos para no necesitar BD
    pedido_mock = {
        "pedido_id": 99,
        "estado": "en-preparacion",
        "forma_pago": "online",
        "items": [{"detalle_id": 1}, {"detalle_id": 2}],
        "minutos_en_estado": 12,
        "total": 25.50,
        "cliente_nombre": "Test Cliente",
        "direccion_entrega": "Calle Test 1",
    }

    with app.app_context():
        with patch.object(gestor_dashboard, 'pedidos_activos', return_value=[pedido_mock]), \
             patch.object(gestor_dashboard, 'monitor_empleados', return_value={"pickers": [], "repartidores": [], "pedidos_sin_picker": [], "pedidos_sin_repartidor": []}), \
             patch.object(gestor_dashboard, 'metricas', return_value={"pedidos_hoy": 0}), \
             patch.object(gestor_dashboard, 'alertas', return_value=[]), \
             patch.object(gestor_dashboard, 'eventos', return_value=[]):
            # Autenticar: el endpoint requiere rol manager/admin
            with client.session_transaction() as sess:
                sess['empleado_id'] = 1
                sess['rol'] = 'admin'
            resp = client.get('/dashboard/monitor/datos')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'pedidos_pipeline' in data, "Falta clave pedidos_pipeline"
            assert isinstance(data['pedidos_pipeline'], list)
            assert len(data['pedidos_pipeline']) == 1
            p = data['pedidos_pipeline'][0]
            for key in ('pedido_id', 'estado', 'forma_pago', 'n_items', 'minutos_en_estado', 'total', 'cliente_nombre', 'direccion_entrega'):
                assert key in p, f"Falta campo {key} en pedido pipeline"
            assert p['n_items'] == 2  # len(items)
```

- [ ] **Step 2: Ejecutar el test y verificar que falla**

```bash
pytest tests/test_gestor_dashboard.py::test_monitor_datos_incluye_pedidos_pipeline -v
```

Resultado esperado: `FAILED` — `AssertionError: Falta clave pedidos_pipeline` (o error de autenticación si el decorador bloquea).

> **Nota sobre autenticación:** Si el endpoint devuelve 302/401 en vez de 200, el decorador `@requiere_rol` está bloqueando. En ese caso, comprobar cómo otros tests del proyecto manejan la autenticación (revisar `tests/test_dashboard.py` si existe, o parchear `requiere_rol` con `patch`).

- [ ] **Step 3: Implementar el cambio en el endpoint**

En `blueprints/dashboard.py`, función `monitor_datos()` (líneas ~65-79), reemplazar el contenido del `try` por:

```python
    try:
        monitor_data = gestor_dashboard.monitor_empleados()
        metricas_data = gestor_dashboard.metricas()
        alertas_data = gestor_dashboard.alertas()
        eventos_data = gestor_dashboard.eventos(limit=25)

        pedidos_activos_data = gestor_dashboard.pedidos_activos()
        pedidos_pipeline = [
            {
                "pedido_id":       p["pedido_id"],
                "estado":          p["estado"],
                "forma_pago":      p["forma_pago"],
                "n_items":         len(p["items"]),
                "minutos_en_estado": p["minutos_en_estado"],
                "total":           p["total"],
                "cliente_nombre":  p["cliente_nombre"],
                "direccion_entrega": p["direccion_entrega"],
            }
            for p in pedidos_activos_data
        ]

        return _ok({
            **monitor_data,
            "metricas":         metricas_data,
            "alertas":          alertas_data,
            "eventos":          eventos_data,
            "pedidos_pipeline": pedidos_pipeline,
        })
    except Exception as e:
        logger.error("Error en /dashboard/monitor/datos: %s", e)
        return _err("Error interno", 500)
```

- [ ] **Step 4: Ejecutar el test y verificar que pasa**

```bash
pytest tests/test_gestor_dashboard.py -v
```

Resultado esperado: todos los tests `PASSED` (o `PASSED` + los de BD que hacen `pass` por `OperationalError`).

- [ ] **Step 5: Ejecutar la suite completa para detectar regresiones**

```bash
pytest -v --tb=short
```

Resultado esperado: mismos resultados que antes excepto el nuevo test que ahora pasa. Los 3 `TestWebhookMonei` pre-existentes pueden seguir fallando — son conocidos.

- [ ] **Step 6: Commit**

```bash
git add blueprints/dashboard.py tests/test_gestor_dashboard.py
git commit -m "feat: exponer pedidos_pipeline en /dashboard/monitor/datos"
```

---

## Task 2: Frontend — Alert banner unificado + badge en header

**Files:**
- Modify: `templates/dashboard/monitor.html:116-135` (alert banners actuales) y `:43-66` (header)

No hay tests pytest para cambios puramente HTML/Alpine. Verificación: abrir el monitor en el navegador y comprobar visualmente.

- [ ] **Step 1: Reemplazar los dos banners separados por uno unificado**

Localizar el bloque entre las líneas `<!-- ALERTS BANNER -->` y `<!-- MAIN GRID -->` (aprox. líneas 113-136). Reemplazar **ambos** divs de alerta por:

```html
  <!-- ═══════════════════════════════════════════════════════════════
       ALERTS BANNER — errores y warnings en una sola franja
  ═══════════════════════════════════════════════════════════════════ -->
  <div x-show="alertas.length > 0" x-cloak
       class="border-b border-gray-800 px-6 py-2"
       :class="alertas.some(a => a.nivel === 'error') ? 'bg-red-950/40' : 'bg-yellow-950/30'">
    <div class="flex items-center gap-3 overflow-x-auto slim-scroll">
      <!-- Errores -->
      <template x-for="a in alertas.filter(a => a.nivel === 'error').slice(0, 4)" :key="'e' + a.pedido_id + a.tipo">
        <span class="text-xs text-red-300 bg-red-900/50 rounded px-2 py-0.5 shrink-0 whitespace-nowrap flex items-center gap-1">
          <span class="w-1.5 h-1.5 rounded-full bg-red-400 shrink-0"></span>
          <span x-text="a.mensaje"></span>
        </span>
      </template>
      <!-- Divisor si hay ambos -->
      <template x-if="alertas.some(a => a.nivel === 'error') && alertas.some(a => a.nivel === 'warning')">
        <span class="h-4 w-px bg-gray-700 shrink-0"></span>
      </template>
      <!-- Warnings -->
      <template x-for="a in alertas.filter(a => a.nivel === 'warning').slice(0, 3)" :key="'w' + a.pedido_id + a.tipo">
        <span class="text-xs text-yellow-300 bg-yellow-900/40 rounded px-2 py-0.5 shrink-0 whitespace-nowrap flex items-center gap-1">
          <span class="text-yellow-500">⚠</span>
          <span x-text="a.mensaje"></span>
        </span>
      </template>
    </div>
  </div>
```

- [ ] **Step 2: Añadir badge de alertas en el header**

Localizar en el header (aprox. línea 44-46) el bloque del indicador EN VIVO:

```html
      <div class="flex items-center gap-1.5" x-show="!error">
        <span class="w-2 h-2 rounded-full bg-green-400 pulse"></span>
        <span class="text-xs text-gray-500">EN VIVO</span>
      </div>
```

Añadir justo después del `</div>` de este bloque (pero dentro del `flex gap-4` del header):

```html
      <!-- Badge de alertas -->
      <template x-if="alertas.length > 0">
        <span class="bg-orange-500 text-white text-xs font-bold rounded-full px-1.5 py-0.5 leading-none min-w-[1.25rem] text-center"
              x-text="alertas.length"></span>
      </template>
```

- [ ] **Step 3: Verificar visualmente**

Iniciar el servidor: `python main.py`
Abrir `http://localhost:5000/dashboard/monitor`.
Comprobar:
- El banner de alertas muestra errores y warnings en la misma franja
- Si no hay alertas, el banner no aparece
- El badge naranja aparece en el header junto a EN VIVO cuando hay alertas

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard/monitor.html
git commit -m "feat: unificar alert banner y añadir badge de alertas en header"
```

---

## Task 3: Frontend — Pipeline Kanban (zona principal nueva)

**Files:**
- Modify: `templates/dashboard/monitor.html`

Esta es la adición principal. Se añade una franja fija de ~200px entre la KPI bar/alert banner y el employees grid.

- [ ] **Step 1: Añadir el HTML del Pipeline Kanban**

Localizar el comentario `<!-- MAIN GRID -->` (aprox. línea 140). Insertar justo **antes** de ese bloque:

```html
  <!-- ═══════════════════════════════════════════════════════════════
       PIPELINE KANBAN
  ═══════════════════════════════════════════════════════════════════ -->
  <div class="bg-gray-900 border-b border-gray-800 px-4 py-2" style="height:196px; overflow:hidden;">
    <div class="grid gap-2 h-full" style="grid-template-columns: 1fr 1.2fr 1fr 1.2fr 0.7fr;">

      <!-- ── COL: PAGADO / CR ───────────────────────────────────── -->
      <div class="flex flex-col min-h-0 rounded-lg overflow-hidden"
           :class="esEmbudoPipeline(['pagado','contra-reembolso']) ? 'ring-1 ring-red-700 bg-red-950/30 animate-pulse' : 'bg-gray-800/40'">
        <div class="px-2 py-1 flex items-center justify-between shrink-0">
          <span class="text-xs font-bold text-emerald-400 uppercase tracking-wide">Pagado/CR</span>
          <span class="text-xs font-mono text-gray-500"
                x-text="pedidosPipeline.filter(p => ['pagado','contra-reembolso'].includes(p.estado)).length"></span>
        </div>
        <div class="flex-1 overflow-hidden px-1.5 pb-1.5 space-y-1">
          <template x-for="p in tarjetasPipeline(['pagado','contra-reembolso'])" :key="p.pedido_id">
            <div class="rounded bg-gray-800/70 border border-gray-700/50 px-2 flex items-center justify-between gap-1 cursor-default group relative"
                 :class="pedidosPipeline.filter(q => ['pagado','contra-reembolso'].includes(q.estado)).length <= 3 ? 'py-1.5' : 'py-0.5'">
              <div class="flex items-center gap-1.5 min-w-0">
                <span class="text-xs font-bold text-white shrink-0">#<span x-text="p.pedido_id"></span></span>
                <span class="text-xs shrink-0" x-text="pagoIconPipeline(p.forma_pago)"></span>
                <span class="text-xs text-gray-600 shrink-0"><span x-text="p.n_items"></span>u</span>
              </div>
              <span class="text-xs font-semibold shrink-0"
                    :class="timerClassPipeline(p.estado, p.minutos_en_estado)"
                    x-text="p.minutos_en_estado != null ? p.minutos_en_estado + 'm' : '—'"></span>
              <!-- Tooltip portátil -->
              <div class="absolute bottom-full left-0 mb-1 z-20 hidden group-hover:block bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs shadow-xl whitespace-nowrap">
                <div class="font-semibold text-white" x-text="p.cliente_nombre"></div>
                <div class="text-gray-400 mt-0.5" x-text="p.direccion_entrega"></div>
                <div class="text-gray-500 mt-0.5"><span x-text="p.total ? p.total.toFixed(2) + '€' : ''"></span></div>
              </div>
            </div>
          </template>
          <template x-if="overflowPipeline(['pagado','contra-reembolso']) > 0">
            <div class="rounded bg-red-900/50 border border-red-700/50 px-2 py-0.5 text-center">
              <span class="text-xs font-bold text-red-300">+<span x-text="overflowPipeline(['pagado','contra-reembolso'])"></span> más</span>
            </div>
          </template>
        </div>
      </div>

      <!-- ── COL: EN PREPARACIÓN ───────────────────────────────── -->
      <div class="flex flex-col min-h-0 rounded-lg overflow-hidden"
           :class="esEmbudoPipeline(['en-preparacion']) ? 'ring-1 ring-red-700 bg-red-950/30 animate-pulse' : 'bg-gray-800/40'">
        <div class="px-2 py-1 flex items-center justify-between shrink-0">
          <span class="text-xs font-bold text-blue-400 uppercase tracking-wide">En prep.</span>
          <span class="text-xs font-mono text-gray-500"
                x-text="pedidosPipeline.filter(p => p.estado === 'en-preparacion').length"></span>
        </div>
        <div class="flex-1 overflow-hidden px-1.5 pb-1.5 space-y-1">
          <template x-for="p in tarjetasPipeline(['en-preparacion'])" :key="p.pedido_id">
            <div class="rounded bg-gray-800/70 border border-gray-700/50 px-2 flex items-center justify-between gap-1 cursor-default group relative"
                 :class="pedidosPipeline.filter(q => q.estado === 'en-preparacion').length <= 3 ? 'py-1.5' : 'py-0.5'">
              <div class="flex items-center gap-1.5 min-w-0">
                <span class="text-xs font-bold text-white shrink-0">#<span x-text="p.pedido_id"></span></span>
                <span class="text-xs shrink-0" x-text="pagoIconPipeline(p.forma_pago)"></span>
                <span class="text-xs text-gray-600 shrink-0"><span x-text="p.n_items"></span>u</span>
              </div>
              <span class="text-xs font-semibold shrink-0"
                    :class="timerClassPipeline(p.estado, p.minutos_en_estado)"
                    x-text="p.minutos_en_estado != null ? p.minutos_en_estado + 'm' : '—'"></span>
              <div class="absolute bottom-full left-0 mb-1 z-20 hidden group-hover:block bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs shadow-xl whitespace-nowrap">
                <div class="font-semibold text-white" x-text="p.cliente_nombre"></div>
                <div class="text-gray-400 mt-0.5" x-text="p.direccion_entrega"></div>
                <div class="text-gray-500 mt-0.5"><span x-text="p.total ? p.total.toFixed(2) + '€' : ''"></span></div>
              </div>
            </div>
          </template>
          <template x-if="overflowPipeline(['en-preparacion']) > 0">
            <div class="rounded bg-red-900/50 border border-red-700/50 px-2 py-0.5 text-center">
              <span class="text-xs font-bold text-red-300">+<span x-text="overflowPipeline(['en-preparacion'])"></span> más</span>
            </div>
          </template>
        </div>
      </div>

      <!-- ── COL: PREPARADO ────────────────────────────────────── -->
      <div class="flex flex-col min-h-0 rounded-lg overflow-hidden"
           :class="esEmbudoPipeline(['preparado']) ? 'ring-1 ring-red-700 bg-red-950/30 animate-pulse' : 'bg-gray-800/40'">
        <div class="px-2 py-1 flex items-center justify-between shrink-0">
          <span class="text-xs font-bold text-indigo-400 uppercase tracking-wide">Preparado</span>
          <span class="text-xs font-mono text-gray-500"
                x-text="pedidosPipeline.filter(p => p.estado === 'preparado').length"></span>
        </div>
        <div class="flex-1 overflow-hidden px-1.5 pb-1.5 space-y-1">
          <template x-for="p in tarjetasPipeline(['preparado'])" :key="p.pedido_id">
            <div class="rounded bg-gray-800/70 border border-gray-700/50 px-2 flex items-center justify-between gap-1 cursor-default group relative"
                 :class="pedidosPipeline.filter(q => q.estado === 'preparado').length <= 3 ? 'py-1.5' : 'py-0.5'">
              <div class="flex items-center gap-1.5 min-w-0">
                <span class="text-xs font-bold text-white shrink-0">#<span x-text="p.pedido_id"></span></span>
                <span class="text-xs shrink-0" x-text="pagoIconPipeline(p.forma_pago)"></span>
                <span class="text-xs text-gray-600 shrink-0"><span x-text="p.n_items"></span>u</span>
              </div>
              <span class="text-xs font-semibold shrink-0"
                    :class="timerClassPipeline(p.estado, p.minutos_en_estado)"
                    x-text="p.minutos_en_estado != null ? p.minutos_en_estado + 'm' : '—'"></span>
              <div class="absolute bottom-full left-0 mb-1 z-20 hidden group-hover:block bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs shadow-xl whitespace-nowrap">
                <div class="font-semibold text-white" x-text="p.cliente_nombre"></div>
                <div class="text-gray-400 mt-0.5" x-text="p.direccion_entrega"></div>
                <div class="text-gray-500 mt-0.5"><span x-text="p.total ? p.total.toFixed(2) + '€' : ''"></span></div>
              </div>
            </div>
          </template>
          <template x-if="overflowPipeline(['preparado']) > 0">
            <div class="rounded bg-red-900/50 border border-red-700/50 px-2 py-0.5 text-center">
              <span class="text-xs font-bold text-red-300">+<span x-text="overflowPipeline(['preparado'])"></span> más</span>
            </div>
          </template>
        </div>
      </div>

      <!-- ── COL: EN REPARTO ───────────────────────────────────── -->
      <div class="flex flex-col min-h-0 rounded-lg overflow-hidden"
           :class="esEmbudoPipeline(['en-reparto']) ? 'ring-1 ring-red-700 bg-red-950/30 animate-pulse' : 'bg-gray-800/40'">
        <div class="px-2 py-1 flex items-center justify-between shrink-0">
          <span class="text-xs font-bold text-orange-400 uppercase tracking-wide">En reparto</span>
          <span class="text-xs font-mono text-gray-500"
                x-text="pedidosPipeline.filter(p => p.estado === 'en-reparto').length"></span>
        </div>
        <div class="flex-1 overflow-hidden px-1.5 pb-1.5 space-y-1">
          <template x-for="p in tarjetasPipeline(['en-reparto'])" :key="p.pedido_id">
            <div class="rounded bg-gray-800/70 border border-gray-700/50 px-2 flex items-center justify-between gap-1 cursor-default group relative"
                 :class="pedidosPipeline.filter(q => q.estado === 'en-reparto').length <= 3 ? 'py-1.5' : 'py-0.5'">
              <div class="flex items-center gap-1.5 min-w-0">
                <span class="text-xs font-bold text-white shrink-0">#<span x-text="p.pedido_id"></span></span>
                <span class="text-xs shrink-0" x-text="pagoIconPipeline(p.forma_pago)"></span>
                <span class="text-xs text-gray-600 shrink-0"><span x-text="p.n_items"></span>u</span>
              </div>
              <span class="text-xs font-semibold shrink-0"
                    :class="timerClassPipeline(p.estado, p.minutos_en_estado)"
                    x-text="p.minutos_en_estado != null ? p.minutos_en_estado + 'm' : '—'"></span>
              <div class="absolute bottom-full left-0 mb-1 z-20 hidden group-hover:block bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs shadow-xl whitespace-nowrap">
                <div class="font-semibold text-white" x-text="p.cliente_nombre"></div>
                <div class="text-gray-400 mt-0.5" x-text="p.direccion_entrega"></div>
                <div class="text-gray-500 mt-0.5"><span x-text="p.total ? p.total.toFixed(2) + '€' : ''"></span></div>
              </div>
            </div>
          </template>
          <template x-if="overflowPipeline(['en-reparto']) > 0">
            <div class="rounded bg-red-900/50 border border-red-700/50 px-2 py-0.5 text-center">
              <span class="text-xs font-bold text-red-300">+<span x-text="overflowPipeline(['en-reparto'])"></span> más</span>
            </div>
          </template>
        </div>
      </div>

      <!-- ── COL: ENTREGADOS (stats only) ─────────────────────── -->
      <div class="flex flex-col items-center justify-center rounded-lg bg-gray-800/40 px-2 py-2 text-center">
        <div class="text-xs font-bold text-green-400 uppercase tracking-wide mb-1">Entregados</div>
        <div class="text-3xl font-black text-white leading-none" x-text="metricas.entregados_hoy ?? '—'"></div>
        <div class="text-xs text-gray-500 mt-1">hoy</div>
        <div class="text-sm font-semibold text-emerald-400 mt-2"
             x-text="metricas.ingresos_hoy_eur != null ? metricas.ingresos_hoy_eur.toFixed(0) + '€' : ''"></div>
      </div>

    </div>
  </div>
```

- [ ] **Step 2: Añadir las funciones Alpine.js del pipeline**

Dentro del objeto `monitor()` en el bloque `<script>`, localizar la línea `// ── Helpers ──` y añadir estas funciones **antes** de `abrirHistorial`:

```js
        // ── Pipeline helpers ─────────────────────────────────────
        pedidosPorEstadoPipeline(estados) {
          return this.pedidosPipeline.filter(p => estados.includes(p.estado));
        },

        tarjetasPipeline(estados) {
          return this.pedidosPorEstadoPipeline(estados).slice(0, 5);
        },

        overflowPipeline(estados) {
          const total = this.pedidosPorEstadoPipeline(estados).length;
          return total > 5 ? total - 5 : 0;
        },

        esEmbudoPipeline(estados) {
          const umbralesError = {
            'pagado': 15, 'contra-reembolso': 15,
            'en-preparacion': 30, 'preparado': 15, 'en-reparto': 60,
          };
          const rojos = this.pedidosPorEstadoPipeline(estados).filter(p =>
            p.minutos_en_estado != null &&
            p.minutos_en_estado >= (umbralesError[p.estado] || 999)
          );
          return rojos.length >= 3;
        },

        timerClassPipeline(estado, minutos) {
          if (minutos == null) return 'text-gray-500';
          const u = {
            'pagado':            { w: 10, e: 15 },
            'contra-reembolso':  { w: 10, e: 15 },
            'en-preparacion':    { w: 20, e: 30 },
            'preparado':         { w: 10, e: 15 },
            'en-reparto':        { w: 40, e: 60 },
          }[estado];
          if (!u) return 'text-gray-500';
          if (minutos >= u.e) return 'text-red-400 font-bold';
          if (minutos >= u.w) return 'text-yellow-400';
          return 'text-green-400';
        },

        pagoIconPipeline(forma_pago) {
          return forma_pago === 'online' ? '💳' : '💵';
        },
```

- [ ] **Step 3: Añadir `pedidosPipeline` al estado Alpine y al método `cargar()`**

En el objeto `monitor()`, localizar la sección de propiedades iniciales (aprox. línea 633-649):

```js
        metricas: {},
        pipeline: {},
        pickers: [],
        ...
```

Cambiar `pipeline: {},` por `pedidosPipeline: [],` (la variable `pipeline` estaba huérfana — el endpoint nunca la devolvía).

En el método `cargar()`, localizar la línea:
```js
            this.pipeline           = data.pipeline || {};
```
Reemplazarla por:
```js
            this.pedidosPipeline    = data.pedidos_pipeline || [];
```

- [ ] **Step 4: Ajustar la altura del main grid**

El main grid actualmente tiene: `h-[calc(100vh-200px)]`.
Con la nueva franja de pipeline (~196px), actualizar a: `h-[calc(100vh-390px)]`.

Localizar en el HTML:
```html
  <div class="grid grid-cols-[1fr_1fr_340px] gap-4 p-4 h-[calc(100vh-200px)] overflow-hidden">
```
Cambiar a:
```html
  <div class="grid grid-cols-[1fr_1fr_340px] gap-4 p-4 h-[calc(100vh-390px)] overflow-hidden">
```

> **Ajuste fino:** El valor exacto depende de si el alert banner está visible (0–40px adicionales). Si el layout se ve cortado en pruebas reales, ajustar el valor de `390px` en incrementos de 10px hasta que todo quepa en 100vh.

- [ ] **Step 5: Verificar visualmente**

Iniciar el servidor: `python main.py`
Abrir `http://localhost:5000/dashboard/monitor`.
Comprobar:
- La franja del pipeline aparece entre las KPIs y los employees
- Las columnas muestran los pedidos activos (puede estar vacío sin datos reales)
- Las tarjetas muestran #ID, icono pago, número de items, timer
- El timer verde/amarillo/rojo funciona al inspeccionar con datos de prueba
- El hover sobre una tarjeta muestra el tooltip con nombre, dirección, total
- Todo cabe en pantalla sin scroll vertical

- [ ] **Step 6: Commit**

```bash
git add templates/dashboard/monitor.html
git commit -m "feat: añadir Pipeline Kanban al monitor de operaciones"
```

---

## Task 4: Frontend — Tooltip KPI ingresos + eventos cancelados en rojo

**Files:**
- Modify: `templates/dashboard/monitor.html`

- [ ] **Step 1: Añadir `mostrarTooltipIngresos: false` al estado Alpine**

En el objeto `monitor()`, en la sección de propiedades iniciales, añadir:
```js
        mostrarTooltipIngresos: false,
```

- [ ] **Step 2: Reemplazar el chip "Ingresos hoy" con versión con tooltip**

Localizar en la KPI bar el chip de ingresos (aprox. líneas 94-98):
```html
      <div class="flex flex-col items-center justify-center py-1.5 px-2 rounded-lg bg-gray-800/50 border border-gray-700/50">
        <div class="text-xs text-gray-500 font-medium mb-0.5 whitespace-nowrap">Ingresos hoy</div>
        <div class="text-xl font-black leading-tight text-emerald-400"
             x-text="metricas.ingresos_hoy_eur != null ? metricas.ingresos_hoy_eur.toFixed(2) + '€' : '—'"></div>
      </div>
```

Reemplazar por:
```html
      <div class="flex flex-col items-center justify-center py-1.5 px-2 rounded-lg bg-gray-800/50 border border-gray-700/50 relative cursor-default"
           @mouseenter="mostrarTooltipIngresos = true"
           @mouseleave="mostrarTooltipIngresos = false">
        <div class="text-xs text-gray-500 font-medium mb-0.5 whitespace-nowrap">Ingresos hoy</div>
        <div class="text-xl font-black leading-tight text-emerald-400"
             x-text="metricas.ingresos_hoy_eur != null ? metricas.ingresos_hoy_eur.toFixed(2) + '€' : '—'"></div>
        <!-- Tooltip desglose -->
        <div x-show="mostrarTooltipIngresos" x-cloak
             class="absolute top-full mt-1 left-1/2 -translate-x-1/2 z-30 bg-gray-800 border border-gray-600 rounded-lg px-3 py-2 text-xs shadow-xl whitespace-nowrap">
          <template x-if="metricas.ingresos_por_metodo">
            <div class="space-y-1">
              <template x-for="[metodo, valor] in Object.entries(metricas.ingresos_por_metodo || {})" :key="metodo">
                <div class="flex items-center justify-between gap-4">
                  <span class="text-gray-400 capitalize" x-text="metodo"></span>
                  <span class="text-white font-semibold" x-text="valor.toFixed(2) + '€'"></span>
                </div>
              </template>
              <template x-if="metricas.cancelaciones_hoy && Object.keys(metricas.cancelaciones_hoy).length > 0">
                <div class="border-t border-gray-700 pt-1 mt-1">
                  <span class="text-red-400">❌ Cancelaciones: </span>
                  <span class="text-red-300 font-semibold"
                        x-text="Object.values(metricas.cancelaciones_hoy || {}).reduce((a,b)=>a+b,0)"></span>
                </div>
              </template>
            </div>
          </template>
        </div>
      </div>
```

- [ ] **Step 3: Resaltar eventos cancelados en el feed**

Localizar en el feed de actividad la línea (aprox. línea 525):
```html
            <div class="flex items-start gap-2 py-1.5 px-2 rounded-lg hover:bg-gray-800/40 transition fade-in">
```

Reemplazar por:
```html
            <div class="flex items-start gap-2 py-1.5 px-2 rounded-lg transition fade-in"
                 :class="e.estado_nuevo === 'cancelado' ? 'bg-red-950/40 hover:bg-red-950/60' : 'hover:bg-gray-800/40'">
```

- [ ] **Step 4: Verificar visualmente**

Iniciar el servidor: `python main.py`
Abrir `http://localhost:5000/dashboard/monitor`.
Comprobar:
- Hover sobre el chip "Ingresos hoy" muestra el desglose por método de pago
- Si hay cancelaciones, aparece la línea de cancelaciones en el tooltip
- Los eventos `cancelado` en el feed tienen fondo rojo tenue

- [ ] **Step 5: Ejecutar tests finales**

```bash
pytest -v --tb=short
```

Resultado esperado: todos los tests pasan (o fallan solo los 3 `TestWebhookMonei` pre-existentes).

- [ ] **Step 6: Commit**

```bash
git add templates/dashboard/monitor.html
git commit -m "feat: tooltip de ingresos en KPI bar y eventos cancelados resaltados en feed"
```

---

## Verificación final

- [ ] Abrir el monitor en un TV/pantalla grande y comprobar que todo es legible sin acercarse
- [ ] Simular datos con varios pedidos en el mismo estado y verificar el overflow ("+N más")
- [ ] Verificar que el layout no hace scroll vertical en una pantalla de 1080p (1920×1080)
- [ ] Verificar la auto-actualización cada 15 segundos con el indicador EN VIVO

---

## Notas de implementación

- **Autenticación en tests:** El decorador `@requiere_rol` usa sesión Flask. Si el test del Task 1 falla por 302/401, parchear el decorador: `@patch('blueprints.dashboard.requiere_rol', lambda *a, **kw: lambda f: f)`.
- **Ajuste fino de altura del main grid:** La KPI bar actual tiene `200px` en el cálculo. Con pipeline (+196px) + header (~48px) + KPI bar (~52px) + alert banner opcional (~40px), el grid debe calcularse: `100vh - header - kpi - alert - pipeline - padding`. Si el alert banner es variable, usar `390px` como estimación conservadora y ajustar visualmente.
- **Estado Alpine huérfano `pipeline`:** Al eliminar `this.pipeline = data.pipeline || {}` no se rompe nada — ese campo nunca fue renderizado en el template.
