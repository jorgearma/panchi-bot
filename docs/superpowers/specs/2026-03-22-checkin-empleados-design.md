# Check-in y registro de tiempo de empleados

**Fecha:** 2026-03-22
**Estado:** Aprobado

---

## Contexto

Panchi-Bot gestiona pedidos de restaurante vía WhatsApp. Los empleados (pickers y repartidores) acceden a `/empleado` como hub personal. Actualmente no hay registro de horas trabajadas ni de tiempo por rol.

El objetivo es añadir fichaje de entrada/salida con desglose automático del tiempo dedicado a cada rol (picker vs repartidor), visible para el propio empleado y almacenado para un futuro panel de manager.

---

## Decisiones de diseño

- **Tablas nuevas, sin tocar existentes** — `check_ins` y `tramos_turno` son independientes de `turnos` (planificación) y de `pedidos`.
- **Tabla `turnos` no se modifica** — sigue siendo el turno planificado por el manager. `check_ins` es el turno real fichado.
- **Tramos automáticos** — se generan al cambiar de rol, no requieren acción manual del empleado.
- **Un check-in por empleado por día** — constraint `UNIQUE (empleado_id, fecha)`.
- **Scope de esta iteración: solo `/empleado`** — el panel de manager queda para una iteración futura.

---

## Modelo de datos

### Tabla `check_ins`

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | Integer PK | autoincrement |
| `empleado_id` | Integer FK → empleados | NOT NULL |
| `fecha` | Date | NOT NULL |
| `inicio` | DateTime | NOT NULL |
| `fin` | DateTime | nullable — NULL si turno abierto |
| `created_at` | DateTime | default utcnow |

Constraint: `UNIQUE (empleado_id, fecha)`

### Tabla `tramos_turno`

| Campo | Tipo | Notas |
|-------|------|-------|
| `id` | Integer PK | autoincrement |
| `check_in_id` | Integer FK → check_ins | NOT NULL |
| `rol` | String(20) | `picker` \| `repartidor` |
| `inicio` | DateTime | NOT NULL |
| `fin` | DateTime | nullable — NULL si tramo activo |

### Relaciones ORM

```
Empleado ──< CheckIn ──< TramoTurno
```

---

## Flujo de eventos

### 1. Check-in (nuevo botón "Iniciar turno")
- Crea `CheckIn(empleado_id, fecha=hoy_utc, inicio=ahora_utc)`
- Si `empleado.rol_activo` tiene valor → crea `TramoTurno(rol=rol_activo, inicio=ahora_utc)`
- Cambia `estado_operativo` a `disponible` (alineado con valor existente en el sistema)
- **Zona horaria:** `fecha` y todos los timestamps usan UTC (`datetime.utcnow()`), consistente con el resto del proyecto

### 2. Cambiar rol (hook en `cambiarRol()` existente)
- Cierra tramo activo: `tramo.fin = ahora`
- Abre nuevo tramo: `TramoTurno(rol=nuevo_rol, inicio=ahora)`
- Solo actúa si hay un `CheckIn` abierto para hoy

### 3. Pausa (hook en `cambiarEstado('en_pausa')`)
- Cierra tramo activo si lo hay: `tramo.fin = ahora` (safe si no hay tramo)
- No abre tramo nuevo
- `estado_operativo` queda `en_pausa`, `rol_activo` no se modifica

### 4. Reanudar (hook en `cambiarEstado('disponible')`)
- Si hay `CheckIn` abierto y `rol_activo` tiene valor → abre nuevo tramo
- Si `rol_activo` es NULL → no se abre tramo (el empleado aún no tiene rol asignado)

### 5. Check-out ("Cerrar turno" / `cambiarEstado('desconectado')`)
- Cierra tramo activo si lo hay: `tramo.fin = ahora`
- Cierra `CheckIn`: `check_in.fin = ahora`

---

## Endpoints

### `POST /empleado/checkin`
- Requiere rol: todos los roles hub
- Crea `CheckIn` para hoy (falla con 409 si ya existe uno abierto)
- Respuesta: `{ check_in_id, inicio }`

### `POST /empleado/checkout`
- Requiere rol: todos los roles hub
- Cierra `CheckIn` activo del día y su tramo activo
- Respuesta: `{ fin, duracion_total_min, tramos: [{rol, minutos}] }`

### `GET /empleado/checkin-hoy`
- Requiere rol: todos los roles hub
- Devuelve check-in de hoy (activo o cerrado) con tramos y resumen calculado
- Respuesta:
```json
{
  "activo": true,
  "inicio": "2026-03-22T09:00:00",
  "fin": null,
  "duracion_total_min": 210,
  "tramos": [
    { "rol": "picker",      "minutos": 130 },
    { "rol": "repartidor",  "minutos": 80  }
  ]
}
```
- Si no hay check-in hoy: `{ "activo": false }`

---

## Lógica de negocio (`GestorEmpleado`)

### `iniciar_turno(empleado_id) → CheckIn`
- Busca check-in abierto del día → si existe lanza `ValueError('ya_abierto')`
- Crea `CheckIn`
- Si `empleado.rol_activo` → crea primer `TramoTurno`

### `cerrar_turno(empleado_id) → dict`
- Busca check-in abierto → si no existe lanza `ValueError('no_abierto')`
- Cierra tramo activo y check-in
- Devuelve resumen calculado

### `_cerrar_tramo_activo(check_in, ahora)`
- Busca `TramoTurno` con `fin=NULL` en ese check-in → lo cierra
- Si no hay tramo abierto, no hace nada (safe)

### `_abrir_tramo(check_in, rol, ahora)`
- Crea `TramoTurno(check_in_id, rol, inicio=ahora)`

### `checkin_hoy(empleado_id) → dict`
- Busca check-in de hoy (abierto o cerrado)
- Calcula duración de cada tramo (los abiertos usan `utcnow` como fin provisional)
- Devuelve resumen
- **No colisiona con `turno_hoy()` existente** — ese método devuelve el turno planificado de tabla `turnos`

---

## UI en `/empleado`

### Bloque "Mi estado" (modificado)

**Sin check-in activo:**
```
[●  Desconectado]          [▶ Iniciar turno]  (botón verde prominente)
```

**Con check-in activo:**
```
[●  Conectado — desde 09:00]    [⏸ Pausa]  [⏹ Cerrar turno]
```

### Sección nueva "Mi turno de hoy" (debajo de "Colas ahora")

Visible si hay check-in del día (activo o cerrado):
```
Mi turno de hoy
─────────────────────────────
09:00 → 14:30   (5h 30min)
📦 Picker        3h 10min
🛵 Repartidor    2h 20min
```

Si no hay check-in: sección oculta.

---

## Gestión de errores

| Situación | Comportamiento |
|-----------|---------------|
| Check-in duplicado (mismo día) | 409 — el frontend muestra "Ya tienes un turno abierto hoy" |
| Checkout sin check-in abierto | 400 — botón no aparece si no hay check-in |
| Cambio de rol sin check-in activo | Hooks no hacen nada (guard silencioso) |
| Tramo sin fin al calcular duración | Se usa `utcnow` como fin provisional |

---

## Migración SQL

```sql
CREATE TABLE check_ins (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    empleado_id INT NOT NULL REFERENCES empleados(EmpleadoID),
    fecha       DATE NOT NULL,
    inicio      DATETIME NOT NULL,
    fin         DATETIME NULL,
    created_at  DATETIME NOT NULL DEFAULT GETUTCDATE(),
    CONSTRAINT uq_checkin_empleado_fecha UNIQUE (empleado_id, fecha)
);

CREATE TABLE tramos_turno (
    id           INT IDENTITY(1,1) PRIMARY KEY,
    check_in_id  INT NOT NULL REFERENCES check_ins(id),
    rol          VARCHAR(20) NOT NULL,
    inicio       DATETIME NOT NULL,
    fin          DATETIME NULL
);
```

---

## Archivos a modificar/crear

| Archivo | Acción |
|---------|--------|
| `models.py` | Añadir `CheckIn`, `TramoTurno` |
| `managers/gestor_empleado.py` | Añadir métodos `iniciar_turno`, `cerrar_turno`, `checkin_hoy`, helpers privados. Hooks en `cambiarEstado` y `cambiarRol` |
| `blueprints/empleado.py` | Añadir rutas `/checkin`, `/checkout`, `/checkin-hoy` |
| `templates/empleado/index.html` | Modificar bloque estado, añadir sección "Mi turno de hoy" |

**No se tocan:** `models.py` (tablas existentes), `blueprints/picker.py`, `blueprints/repartidor.py`, lógica de pedidos.
