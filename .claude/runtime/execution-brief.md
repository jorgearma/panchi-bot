# Execution Brief — Dashboard Estado-Acción

**Archivo objetivo:** `templates/dashboard/index.html`
**Agente:** frontend

---

## Resumen

Consolidar la información de estado + tiempo en una sola celda de la tabla de pedidos, con colores de badge de alto contraste y mensajes de acción orientados al operador.

---

## Pasos

### Step 1 — badgePedidoClass: nuevos colores

| Estado | Antes | Después |
|---|---|---|
| `pagado` | bg-emerald-100 text-emerald-800 | **bg-amber-400 text-amber-900** |
| `contra_reembolso` | bg-purple-100 text-purple-800 | **bg-amber-400 text-amber-900** |
| `en_preparacion` | bg-blue-100 text-blue-800 | **bg-blue-500 text-white** |
| `preparado` | bg-indigo-100 text-indigo-800 | **bg-emerald-500 text-white** |
| `en_reparto` | bg-orange-100 text-orange-800 | **bg-orange-500 text-white** |
| `entregado` | bg-green-100 text-green-800 | **bg-slate-200 text-slate-500** |
| `cancelado` | bg-red-100 text-red-700 | **bg-red-600 text-white** |

### Step 2 — estadoLabel: labels cortos

| Estado | Antes | Después |
|---|---|---|
| `pagado` | Pagado | **Pago OK** |
| `contra_reembolso` | Contra reembolso | **Efectivo** |
| `en_preparacion` | En picking | **Picking** |
| `preparado` | Preparado | **Listo** |
| `en_reparto` | En reparto | **En ruta** |

### Step 3 — Mensajes de acción (HTML ~línea 264)

| Estado | Antes | Después |
|---|---|---|
| pagado/contra_reembolso | → Asignar picker | **→ Asignar picker ahora** |
| en_preparacion | → Preparando... | **→ Picker en curso** |
| preparado | → Asignar repartidor | → Asignar repartidor *(sin cambio)* |
| en_reparto | → En camino | **→ En camino al cliente** |
| entregado | *(vacío)* | **✓ Completado** |
| cancelado | *(vacío)* | **✗ Cancelado** |

### Step 4 — Añadir minutos en celda de estado

Insertar después del `<p>` de acción, antes del `</td>`:

```html
<div x-show="!['entregado','cancelado','reembolsado','enlace','enlace2','confirmando-pago'].includes(p.estado)" class="mt-1.5">
  <p class="text-xs font-black tabular-nums leading-none"
     :class="p.minutos_en_estado > 30 ? 'text-red-600' : p.minutos_en_estado > 20 ? 'text-amber-500' : 'text-slate-700'"
     x-text="formatMinutos(p.minutos_en_estado)"></p>
  <div class="mt-1 h-1 w-12 overflow-hidden rounded-full bg-slate-100">
    <div class="h-1 rounded-full transition-all"
         :class="p.minutos_en_estado > 30 ? 'bg-red-500' : p.minutos_en_estado > 20 ? 'bg-amber-400' : 'bg-emerald-400'"
         :style="'width:' + Math.min((p.minutos_en_estado / 40) * 100, 100) + '%'"></div>
  </div>
</div>
```

### Step 5 — Eliminar columna separada de tiempo

- Eliminar el `<td>` de tiempo (~líneas 311-322) incluyendo el comentario `<!-- Tiempo en estado -->`.
- Eliminar el `<th>` correspondiente del `<thead>` de la tabla.

---

## Criterios de aceptación

- [ ] Badges con colores sólidos de alto contraste por estado operativo
- [ ] Labels cortos (≤10 caracteres) en todos los badges
- [ ] Mensajes de acción concretos y orientados a tarea
- [ ] Minutos + barra de urgencia dentro de la celda de estado
- [ ] Columna de tiempo eliminada (thead y tbody consistentes)
- [ ] Estados terminales no muestran bloque de minutos
