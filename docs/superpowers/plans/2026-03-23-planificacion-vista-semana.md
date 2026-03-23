# Vista Semana en Planificación de Turnos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir una vista de cuadrícula semanal (empleados × días) a la tab de Planificación del dashboard de turnos, con navegación ← → entre semanas y botón `+` en celdas vacías para crear turnos pre-rellenos.

**Architecture:** Todo el trabajo es frontend — Alpine.js para estado y helpers, Tailwind para estilos. El backend ya tiene los cambios necesarios (cap `per_page` subido a 200 en `blueprints/dashboard.py`). Se reutiliza el endpoint `/dashboard/turnos/planificacion` con `desde`/`hasta` de la semana y `per_page=200`. La vista tabla existente no cambia funcionalmente.

**Tech Stack:** Alpine.js 3.x, Tailwind CSS (CDN), Jinja2 macros (`empty_state`, `loading_skeleton`)

**Spec:** `docs/superpowers/specs/2026-03-23-planificacion-vista-semana-design.md`

---

## Archivos a modificar

| Archivo | Cambio |
|---------|--------|
| `templates/dashboard/turnos.html` | Único archivo — JS state/helpers, `cargarPlan()`, `abrirModalCrear()`, template HTML de la tab |

El cambio de backend (`blueprints/dashboard.py` línea 312) ya está aplicado (`per_page` cap = 200).

---

## Task 1: Añadir estado y helpers de vista semana al Alpine.js

**Files:**
- Modify: `templates/dashboard/turnos.html:641-648` (bloque `// ── Planificación ──`)
- Modify: `templates/dashboard/turnos.html:660-675` (función `init()`)
- Modify: `templates/dashboard/turnos.html:720-732` (bloque de helpers de formato)

- [ ] **Step 1: Añadir propiedades de estado nuevas**

En el bloque `// ── Planificación ──` (línea 641), justo después de `planFiltros: { ... },`, añadir:

```js
    // ── Vista semana ──
    vistaGrid: false,
    semanaBase: null,
```

- [ ] **Step 2: Inicializar `semanaBase` en `init()`**

Dentro de `init()`, al final del bloque (antes del cierre `}`), añadir:

```js
      this.semanaBase = this.lunes(new Date());
```

- [ ] **Step 3: Añadir helpers de fecha al bloque de utilidades**

Después de `formatHora()` (línea 732) y antes de `cargar()`, insertar los helpers:

```js
    formatISO(date) {
      // Date → 'YYYY-MM-DD' en hora local (evita desfase UTC)
      const y = date.getFullYear();
      const m = String(date.getMonth() + 1).padStart(2, '0');
      const d = String(date.getDate()).padStart(2, '0');
      return `${y}-${m}-${d}`;
    },

    lunes(date) {
      const d = new Date(date);
      const day = d.getDay(); // 0=dom, 1=lun, …
      const diff = (day === 0) ? -6 : 1 - day;
      d.setDate(d.getDate() + diff);
      d.setHours(0, 0, 0, 0);
      return d;
    },

    diasSemana() {
      return Array.from({ length: 7 }, (_, i) => {
        const d = new Date(this.semanaBase);
        d.setDate(d.getDate() + i);
        return d;
      });
    },

    semanaLabel() {
      const dias = this.diasSemana();
      const lun = dias[0];
      const dom = dias[6];
      const DIAS  = ['Dom','Lun','Mar','Mié','Jue','Vie','Sáb'];
      const MESES = ['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
      const labelLun = `${DIAS[lun.getDay()]} ${lun.getDate()}`;
      const labelDom = `${DIAS[dom.getDay()]} ${dom.getDate()}`;
      const mismoMes = lun.getMonth() === dom.getMonth();
      if (mismoMes) {
        return `${labelLun} — ${labelDom} ${MESES[dom.getMonth()]} ${dom.getFullYear()}`;
      }
      return `${labelLun} ${MESES[lun.getMonth()]} — ${labelDom} ${MESES[dom.getMonth()]} ${dom.getFullYear()}`;
    },

    esHoy(date) {
      const hoy = new Date();
      return date.getFullYear() === hoy.getFullYear()
          && date.getMonth()    === hoy.getMonth()
          && date.getDate()     === hoy.getDate();
    },

    semanaTurnos() {
      // { String(empleado_id): { 'YYYY-MM-DD': turno[] } }
      const mapa = {};
      for (const t of this.planTurnos) {
        const eid = String(t.empleado_id);
        if (!mapa[eid]) mapa[eid] = {};
        if (!mapa[eid][t.fecha]) mapa[eid][t.fecha] = [];
        mapa[eid][t.fecha].push(t);
      }
      return mapa;
    },

    empleadosSemana() {
      const vistos = new Set();
      const lista  = [];
      for (const t of this.planTurnos) {
        if (!vistos.has(t.empleado_id)) {
          vistos.add(t.empleado_id);
          lista.push({ id: t.empleado_id, nombre: t.empleado });
        }
      }
      lista.sort((a, b) => a.nombre.localeCompare(b.nombre));
      return lista;
    },
```

- [ ] **Step 4: Verificar en navegador que no hay errores de JS**

Abrir `http://localhost:5000/dashboard/turnos`, abrir consola del navegador, confirmar sin errores. Los nuevos helpers son llamables desde la consola: `document.querySelector('[x-data]').__x.$data.semanaLabel()` debe devolver un string con la semana actual.

- [ ] **Step 5: Commit**

```bash
git add templates/dashboard/turnos.html
git commit -m "feat(turnos): add week-grid Alpine state and date helpers"
```

---

## Task 2: Actualizar `cargarPlan()` y `abrirModalCrear()`

**Files:**
- Modify: `templates/dashboard/turnos.html:740-762` (`cargarPlan()`)
- Modify: `templates/dashboard/turnos.html:776-790` (`abrirModalCrear()`)

- [ ] **Step 1: Reemplazar `cargarPlan()` con ramificación por `vistaGrid`**

Reemplazar el cuerpo completo de `cargarPlan()` (líneas 740-762):

```js
    async cargarPlan() {
      this.planCargando = true;
      try {
        const params = new URLSearchParams();
        if (this.vistaGrid) {
          const dias = this.diasSemana();
          params.set('desde',    this.formatISO(dias[0]));
          params.set('hasta',    this.formatISO(dias[6]));
          params.set('per_page', 200);
        } else {
          if (this.planFiltros.desde) params.set('desde', this.planFiltros.desde);
          if (this.planFiltros.hasta) params.set('hasta', this.planFiltros.hasta);
          if (this.planFiltros.rol)   params.set('rol',   this.planFiltros.rol);
          params.set('page',     this.planPage);
          params.set('per_page', 25);
        }
        const resp = await fetch('/dashboard/turnos/planificacion?' + params.toString());
        if (!resp.ok) throw new Error('Error ' + resp.status);
        const data = await resp.json();
        this.planTurnos  = data.turnos;
        this.planTotal   = data.total;
        this.planPage    = data.page;
        this.planPages   = data.pages;
        this.planCargado = true;
      } catch (e) {
        this.error = 'No se pudo cargar la planificación. ' + e.message;
      } finally {
        this.planCargando = false;
      }
    },
```

- [ ] **Step 2: Actualizar `abrirModalCrear()` para aceptar `empleadoId` y `fecha` opcionales**

Reemplazar la firma y el cuerpo de `abrirModalCrear()` (líneas 776-790):

```js
    async abrirModalCrear(empleadoId = null, fecha = null) {
      this.modalModo    = 'crear';
      this.turnoEdicion = null;
      this.formError    = null;
      this.form = {
        empleado_id: '',
        fecha: this.planFiltros.desde || new Date().toISOString().slice(0, 10),
        hora_inicio: '',
        hora_fin: '',
        tipo: '',
        notas: '',
      };
      await this._cargarEmpleados();
      // Pre-rellenar si se llamó desde una celda de la cuadrícula
      if (empleadoId !== null) this.form.empleado_id = String(empleadoId);
      if (fecha      !== null) this.form.fecha       = fecha;
      this.modalAbierto = true;
    },
```

- [ ] **Step 3: Verificar en navegador**

1. Ir a tab Planificación
2. Abrir consola, ejecutar: `document.querySelector('[x-data]').__x.$data.vistaGrid = true`
3. Ejecutar `document.querySelector('[x-data]').__x.$data.cargarPlan()`
4. Confirmar en Network tab que la request tiene `desde`, `hasta` y `per_page=200`

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard/turnos.html
git commit -m "feat(turnos): update cargarPlan() for week mode, abrirModalCrear() pre-fill"
```

---

## Task 3: Reemplazar el HTML de la tab Planificación

**Files:**
- Modify: `templates/dashboard/turnos.html:391-514` (bloque `<!-- ── TAB PLANIFICACIÓN ──`)

- [ ] **Step 1: Reemplazar el bloque completo de la tab**

Reemplazar desde `<!-- ── TAB PLANIFICACIÓN ──` (línea 391) hasta `</div><!-- end tab plan -->` (línea 514) inclusive con:

```html
  <!-- ── TAB PLANIFICACIÓN ─────────────────────────────────────────────────── -->
  <div x-show="tab === 'plan'" x-cloak>

    <!-- Cabecera: toggle vista + botón nuevo turno -->
    <div class="glass-panel rounded-2xl px-5 py-4 mb-4">
      <div class="flex items-center justify-between gap-3 flex-wrap">
        <!-- Toggle tabla / semana -->
        <div class="flex items-center gap-1 bg-slate-100 rounded-xl p-1">
          <button
            @click="vistaGrid = false; planPage = 1; cargarPlan()"
            :class="!vistaGrid ? 'bg-white text-blue-700 shadow-sm font-semibold' : 'text-slate-500 hover:text-slate-700'"
            class="px-3 py-1.5 text-sm rounded-lg transition">
            ≡ Tabla
          </button>
          <button
            @click="vistaGrid = true; cargarPlan()"
            :class="vistaGrid ? 'bg-white text-blue-700 shadow-sm font-semibold' : 'text-slate-500 hover:text-slate-700'"
            class="px-3 py-1.5 text-sm rounded-lg transition">
            ▦ Semana
          </button>
        </div>

        <!-- Filtros tabla (ocultos en modo semana) -->
        <div x-show="!vistaGrid" class="flex flex-wrap gap-3 items-end">
          <div>
            <label class="block text-xs font-semibold text-slate-500 mb-1">Desde</label>
            <input type="date" x-model="planFiltros.desde"
              @change="planPage = 1; cargarPlan()"
              class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-500 mb-1">Hasta</label>
            <input type="date" x-model="planFiltros.hasta"
              @change="planPage = 1; cargarPlan()"
              class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40" />
          </div>
          <div>
            <label class="block text-xs font-semibold text-slate-500 mb-1">Rol</label>
            <select x-model="planFiltros.rol" @change="planPage = 1; cargarPlan()"
              class="rounded-xl border border-slate-200 bg-white/80 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500/40">
              <option value="">Todos</option>
              <option value="picker">Picker</option>
              <option value="repartidor">Repartidor</option>
              <option value="manager">Manager</option>
            </select>
          </div>
          <button @click="planFiltros.rol = ''; planPage = 1; cargarPlan()"
            class="px-3 py-2 text-sm text-slate-500 hover:text-slate-700 rounded-xl hover:bg-slate-100 transition">
            Limpiar
          </button>
        </div>

        <button @click="abrirModalCrear()"
          class="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-xl text-sm font-semibold hover:bg-blue-700 transition">
          <span class="text-base leading-none">+</span> Nuevo turno
        </button>
      </div>

      <!-- Navegación semanal (solo en modo semana) -->
      <div x-show="vistaGrid" class="flex items-center justify-between mt-3 pt-3 border-t border-slate-100">
        <button
          @click="semanaBase = lunes(new Date(semanaBase.getTime() - 7 * 86400000)); cargarPlan()"
          class="px-3 py-1.5 text-sm text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition">
          ← Anterior
        </button>
        <span class="text-sm font-semibold text-slate-700" x-text="semanaBase ? semanaLabel() : ''"></span>
        <button
          @click="semanaBase = lunes(new Date(semanaBase.getTime() + 7 * 86400000)); cargarPlan()"
          class="px-3 py-1.5 text-sm text-slate-600 hover:text-slate-900 hover:bg-slate-100 rounded-lg transition">
          Siguiente →
        </button>
      </div>
    </div>

    <!-- Loading (compartido por tabla y semana) -->
    <div x-show="planCargando" x-cloak>
      {{ loading_skeleton(rows=5, cols=5) }}
    </div>

    <!-- ── VISTA TABLA ── -->
    <template x-if="!vistaGrid">
      <div>
        <!-- Empty state tabla -->
        <div x-show="!planCargando && planTurnos.length === 0" x-cloak>
          {{ empty_state('📅', 'Sin turnos', 'No hay turnos para este período. Crea uno con el botón +.') }}
        </div>

        <!-- Tabla -->
        <div x-show="!planCargando && planTurnos.length > 0" x-cloak>
          <div class="glass-panel rounded-2xl overflow-hidden">
            <table class="w-full text-sm">
              <thead class="bg-slate-50/60 border-b border-slate-200">
                <tr>
                  <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Fecha</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Empleado</th>
                  <th class="hidden sm:table-cell px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Rol</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Horario</th>
                  <th class="hidden md:table-cell px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Tipo</th>
                  <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide">Estado</th>
                  <th class="px-4 py-3 text-right text-xs font-semibold text-slate-500 uppercase tracking-wide">Acciones</th>
                </tr>
              </thead>
              <tbody>
                <template x-for="t in planTurnos" :key="t.id">
                  <tr class="border-b border-slate-100 hover:bg-slate-50/60 transition">
                    <td class="px-4 py-3 font-medium text-slate-800" x-text="t.fecha"></td>
                    <td class="px-4 py-3 text-slate-700" x-text="t.empleado"></td>
                    <td class="hidden sm:table-cell px-4 py-3 text-slate-500 capitalize" x-text="t.rol || '—'"></td>
                    <td class="px-4 py-3 font-mono text-slate-700">
                      <span x-text="t.hora_inicio"></span>–<span x-text="t.hora_fin"></span>
                    </td>
                    <td class="hidden md:table-cell px-4 py-3 capitalize text-slate-500" x-text="t.tipo || '—'"></td>
                    <td class="px-4 py-3">
                      <span class="inline-block px-2 py-0.5 rounded-full text-xs font-semibold"
                        :class="{
                          'bg-blue-100 text-blue-700':       t.estado === 'planificado',
                          'bg-emerald-100 text-emerald-700': t.estado === 'completado',
                          'bg-red-100 text-red-600':         t.estado === 'cancelado',
                        }"
                        x-text="t.estado"></span>
                    </td>
                    <td class="px-4 py-3 text-right">
                      <template x-if="t.estado !== 'cancelado'">
                        <div class="flex items-center justify-end gap-2">
                          <button @click="abrirModalEditar(t)"
                            class="p-1.5 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-lg transition"
                            title="Editar">✏️</button>
                          <button @click="confirmarCancelar(t.id)"
                            class="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-lg transition"
                            title="Cancelar turno">✕</button>
                        </div>
                      </template>
                      <span x-show="t.estado === 'cancelado'" class="text-xs text-slate-300 italic">—</span>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>

          <!-- Paginación -->
          <div x-show="planPages > 1" class="flex items-center justify-between mt-4 text-sm text-slate-500">
            <span><span x-text="planTotal"></span> turnos</span>
            <div class="flex gap-1">
              <button @click="planPage--; cargarPlan()" :disabled="planPage <= 1"
                class="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition">
                ← Anterior
              </button>
              <span class="px-3 py-1.5 text-slate-600">
                <span x-text="planPage"></span> / <span x-text="planPages"></span>
              </span>
              <button @click="planPage++; cargarPlan()" :disabled="planPage >= planPages"
                class="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 disabled:opacity-40 disabled:cursor-not-allowed transition">
                Siguiente →
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- ── VISTA SEMANA ── -->
    <template x-if="vistaGrid">
      <div>
        <!-- Empty state semana -->
        <div x-show="!planCargando && empleadosSemana().length === 0" x-cloak>
          {{ empty_state('📅', 'Sin turnos', 'Sin turnos esta semana. Pulsa + en cualquier celda para crear uno.') }}
        </div>

        <!-- Cuadrícula -->
        <div x-show="!planCargando && empleadosSemana().length > 0" x-cloak
          class="glass-panel rounded-2xl overflow-x-auto">
          <table class="w-full text-sm border-collapse">
            <thead>
              <tr>
                <!-- Columna nombre empleado -->
                <th class="px-4 py-3 text-left text-xs font-semibold text-slate-500 uppercase tracking-wide border-b border-slate-200 bg-slate-50/60 min-w-[140px]">
                  Empleado
                </th>
                <!-- 7 columnas de días -->
                <template x-for="dia in diasSemana()" :key="formatISO(dia)">
                  <th class="px-2 py-3 text-center text-xs font-semibold uppercase tracking-wide border-b border-slate-200 min-w-[110px]"
                    :class="esHoy(dia) ? 'bg-blue-50 text-blue-700' : 'bg-slate-50/60 text-slate-500'">
                    <div x-text="['Lun','Mar','Mié','Jue','Vie','Sáb','Dom'][dia.getDay() === 0 ? 6 : dia.getDay() - 1]"></div>
                    <div class="text-base font-bold mt-0.5" x-text="dia.getDate()"></div>
                  </th>
                </template>
              </tr>
            </thead>
            <tbody>
              <template x-for="emp in empleadosSemana()" :key="emp.id">
                <tr class="border-b border-slate-100 hover:bg-slate-50/30 transition">
                  <!-- Nombre -->
                  <td class="px-4 py-3 font-semibold text-slate-700 text-sm">
                    <span x-text="emp.nombre"></span>
                  </td>
                  <!-- Celda por día -->
                  <template x-for="dia in diasSemana()" :key="formatISO(dia)">
                    <td class="px-2 py-2 text-center align-top"
                      :class="esHoy(dia) ? 'bg-blue-50/40' : ''">
                      <template x-if="(semanaTurnos()[String(emp.id)] || {})[formatISO(dia)]">
                        <!-- Uno o más chips de turno -->
                        <div class="flex flex-col gap-1 items-center">
                          <template x-for="t in (semanaTurnos()[String(emp.id)] || {})[formatISO(dia)] || []" :key="t.id">
                            <span class="inline-block px-2 py-1 rounded-lg text-xs font-semibold font-mono leading-none"
                              :class="{
                                'bg-blue-100 text-blue-700':     t.tipo === 'mañana',
                                'bg-amber-100 text-amber-700':   t.tipo === 'tarde',
                                'bg-indigo-100 text-indigo-700': t.tipo === 'noche',
                                'bg-emerald-100 text-emerald-700': t.tipo === 'partido',
                                'bg-slate-100 text-slate-600':   !t.tipo,
                              }"
                              x-text="(t.hora_inicio || '?') + '–' + (t.hora_fin || '?')">
                            </span>
                          </template>
                        </div>
                      </template>
                      <template x-if="!((semanaTurnos()[String(emp.id)] || {})[formatISO(dia)])">
                        <!-- Celda vacía: botón + -->
                        <button
                          @click="abrirModalCrear(emp.id, formatISO(dia))"
                          class="w-full h-8 flex items-center justify-center text-slate-300 hover:text-blue-500 hover:bg-blue-50 rounded-lg transition text-lg leading-none"
                          title="Crear turno">
                          +
                        </button>
                      </template>
                    </td>
                  </template>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
      </div>
    </template>

  </div><!-- end tab plan -->
```

- [ ] **Step 2: Verificar en navegador — modo tabla intacto**

1. Ir a tab Planificación, confirmar que la tabla sigue mostrando turnos correctamente
2. Confirmar que la paginación funciona
3. Confirmar que los filtros de fecha y rol funcionan

- [ ] **Step 3: Verificar en navegador — modo semana**

1. Hacer clic en "▦ Semana"
2. Confirmar que la cuadrícula aparece con una fila por empleado y 7 columnas
3. Confirmar que hoy tiene columna con fondo azul
4. Confirmar que los chips de turno tienen el color correcto según tipo
5. Hacer clic en `← Anterior` y `Siguiente →`, confirmar que el label cambia y los datos se recargan
6. Hacer clic en un `+` en celda vacía, confirmar que el modal se abre con empleado y fecha pre-rellenados
7. Crear un turno desde el modal, confirmar que aparece en la cuadrícula al guardarse

- [ ] **Step 4: Verificar semana sin turnos**

Navegar a una semana futura sin turnos planificados. Confirmar que aparece el `empty_state` con "Sin turnos esta semana."

- [ ] **Step 5: Commit**

```bash
git add templates/dashboard/turnos.html
git commit -m "feat(turnos): add weekly grid view to Planificacion tab"
```

---

## Verificación final

```bash
pytest -v --tb=short
```

Esperado: todos los tests existentes pasan. Los 3 tests `TestWebhookMonei` conocidos pueden seguir fallando (no son regresión de este cambio).
