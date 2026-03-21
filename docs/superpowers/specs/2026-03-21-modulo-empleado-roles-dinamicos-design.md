# Módulo Empleado — Roles Dinámicos

**Fecha:** 2026-03-21
**Rama:** `refactorizar-estructura`
**Estado:** Aprobado para implementación

---

## Contexto y problema

El sistema actual asigna a cada empleado un único rol fijo (`rol_id` FK en `empleados`). Ese rol se escribe en `session['rol']` al hacer login y no cambia. Esto impide que un mismo empleado pueda actuar como picker un día y como repartidor otro según la demanda operativa.

**Objetivo de este sprint:** que cualquier empleado con múltiples capacidades pueda elegir su rol al iniciar el turno y cambiarlo durante el día, sin necesidad de cambiar su cuenta ni hacer logout/login.

---

## Decisiones clave

| Decisión | Opción elegida | Razones |
|---|---|---|
| ¿Quién asigna el rol por turno? | El empleado (con sugerencia del manager) | Flexibilidad operativa real |
| ¿Puede cambiar rol con tareas activas? | No — bloqueo duro | Evita pedidos huérfanos |
| Enfoque arquitectónico | Tabla `empleado_capacidades` + `rol_activo` en sesión | Mínima fricción con código existente |
| UX de selección de rol | Check-in screen al primer acceso del día | Ritual claro, contexto operativo, sin saturar el hub |

---

## Modelo de datos

### Tabla nueva: `empleado_capacidades`

```sql
-- SQL Server
CREATE TABLE empleado_capacidades (
    id          INT PRIMARY KEY IDENTITY(1,1),
    empleado_id INT NOT NULL REFERENCES empleados(EmpleadoID),
    rol         VARCHAR(20) NOT NULL,  -- 'picker' | 'repartidor'
    UNIQUE (empleado_id, rol)
);
```

En el modelo SQLAlchemy: `Column(Integer, primary_key=True, autoincrement=True)` (SQLAlchemy traduce correctamente a IDENTITY en SQL Server).

Un empleado dedicado tiene una fila. Un polivalente tiene dos.

### Columna nueva en `empleados`

```sql
ALTER TABLE empleados ADD rol_activo VARCHAR(20) NULL;
-- picker | repartidor | NULL (desconectado / sin seleccionar)
```

Persiste el último rol usado para restaurarlo si la sesión expira.

### Columna opcional en `turnos` (Fase 2, no este sprint)

```sql
ALTER TABLE turnos ADD rol_planificado VARCHAR(20) NULL;
-- sugerencia del manager, no obligatoria
```

### Migración de datos

Al desplegar:

1. Poblar `empleado_capacidades` desde `rol_id` actual de todos los empleados operativos (picker / repartidor). Los empleados con rol manager/admin no reciben entradas en esta tabla.
2. Pre-poblar `rol_activo` para empleados actualmente conectados (`estado_operativo != 'desconectado'`) para evitar que queden bloqueados mid-turno durante el despliegue.

```python
# Pseudocódigo de migración
for empleado in session.query(Empleado).join(Rol).filter(
    Rol.nombre.in_(['picker', 'repartidor'])
):
    session.add(EmpleadoCapacidad(
        empleado_id=empleado.EmpleadoID,
        rol=empleado.rol.nombre
    ))
    # Pre-poblar rol_activo para no romper sesiones activas
    if empleado.rol_activo is None:
        empleado.rol_activo = empleado.rol.nombre
```

3. Migrar `AuditLog.pedido_id` a nullable (ver sección Trazabilidad).

---

## Lógica de autenticación — cambios

### Login (auth.py)

```python
# Antes:
session['rol'] = empleado.rol.nombre  # FK fijo

# Después (tres ramas bien separadas):
capacidades = [c.rol for c in empleado.capacidades]

if not capacidades:
    # Sin capacidades — no debe pasar tras la migración, pero se maneja:
    # Redirigir a una página de error informativa, no al dashboard
    # (manager/admin no tienen capacidades operativas y siguen por rol_id)
    session['rol'] = empleado.rol.nombre if empleado.rol else None
elif len(capacidades) == 1:
    session['rol'] = capacidades[0]
elif empleado.rol_activo in capacidades:
    session['rol'] = empleado.rol_activo  # restaurar último usado
else:
    # Polivalente sin rol_activo previo: asignar temporalmente la primera
    # capacidad para que requiere_rol no bloquee, y redirigir a check-in
    session['rol'] = capacidades[0]
```

**Regla:** `session['rol']` nunca debe quedar en `None` para empleados operativos. `requiere_rol` devuelve 403 si el valor no está en la lista de roles permitidos, lo que bloquearía el acceso antes de renderizar cualquier página.

### Destino tras login

```python
destinos = {
    'manager':    '/dashboard',
    'admin':      '/dashboard',
    'picker':     '/empleado',
    'repartidor': '/empleado',
}
destino = destinos.get(session['rol'], '/empleado')

# Polivalente sin rol_activo previo → ir directo al check-in
if len(capacidades) > 1 and not empleado.rol_activo:
    destino = '/empleado/checkin'
```

---

## Nuevos endpoints — `blueprints/empleado.py`

### `GET /empleado/checkin`

**Control de acceso:** decorado con un helper que solo verifica `session['empleado_id']` presente, sin chequeo de rol. Implementar como `@requiere_autenticacion` (nuevo helper en `auth.py`) o inline con `if 'empleado_id' not in session: redirect(login)`. No usar `@requiere_rol` aquí — el empleado puede llegar con rol temporal asignado o sin él.

Renderiza la pantalla de selección de rol. Solo accesible si el empleado tiene `>= 1` capacidad. Si tiene exactamente 1, redirige directamente al hub (no necesita elegir).

Datos que necesita mostrar:
- Lista de capacidades del empleado
- Carga operativa en tiempo real (nº de pickings pendientes, nº de repartos listos)
- `rol_planificado` del turno de hoy si existe (sugerencia del manager) — Fase 2

### `POST /empleado/cambiar-rol`

```
Body: { "rol": "picker" | "repartidor" }

Validaciones:
1. rol ∈ capacidades del empleado → 403 si no
2. Tareas activas con rol actual:
   - picker activo: PickingPedido WHERE empleado_id=X AND estado='en_proceso'
   - repartidor activo: Reparto WHERE repartidor_id=X AND estado IN ('asignado','en_camino')
   → 409 con lista de pedidos bloqueantes si las hay
3. Si ok:
   - UPDATE empleados SET rol_activo = nuevo_rol
   - session['rol'] = nuevo_rol
   - Si estado_operativo IN ('desconectado', 'en_pausa'): setear `empleado.estado_operativo = 'disponible'` directamente en el ORM y commit.
     → NO usar `gestor_empleado.cambiar_estado()` aquí — ese método solo acepta `_ESTADOS_MANUALES = {'en_pausa', 'desconectado'}` por diseño (cambios iniciados por el empleado). El cambio a 'disponible' en check-in lo inicia el sistema, así que se escribe directamente en el modelo.
     → Cubre tanto el check-in inicial (venía de 'desconectado') como el cambio mid-turno desde pausa
   - INSERT en log (ver sección Trazabilidad)
   → 200 { ok: True, rol: nuevo_rol }
```

### `GET /empleado/carga-operativa`

```json
{
  "picker": { "pendientes": 7, "en_proceso": 2 },
  "repartidor": { "listos_para_entregar": 4, "en_camino": 1 }
}
```

Usado por la pantalla de check-in para mostrar contexto de decisión. No requiere rol específico, solo autenticación.

### `GET /empleado/capacidades`

```json
{ "capacidades": ["picker", "repartidor"], "rol_activo": "picker" }
```

Usado por el hub para saber si mostrar el enlace "⇄ Cambiar rol".

---

## Manager `GestorEmpleado` — métodos nuevos

```python
def capacidades(self, empleado_id: int) -> list[str]:
    """Roles que puede desempeñar el empleado. Ej: ['picker', 'repartidor']"""

def es_polivalente(self, empleado_id: int) -> bool:
    """True si el empleado tiene más de una capacidad operativa."""

def tiene_rol_activo(self, empleado_id: int) -> bool:
    """True si empleado.rol_activo no es NULL en BD."""

def cambiar_rol(self, empleado_id: int, nuevo_rol: str) -> tuple[bool, str, list]:
    """
    Intenta cambiar el rol activo del empleado.
    También setea estado_operativo = 'disponible' si venía de 'desconectado' o 'en_pausa'.
    Returns: (ok, mensaje, pedidos_bloqueantes)
    pedidos_bloqueantes: lista de dicts {id, tipo, estado} si hay bloqueo
    """

def carga_operativa(self) -> dict:
    """Nº de pedidos en cada cola para la pantalla de check-in."""
```

---

## Cambios al hub (`templates/empleado/index.html`)

### Header
Mostrar rol activo en el subtítulo, ya lo hace (`rolLabel`). Sin cambios.

### CTA principal
Añadir al fondo del bloque gradient, condicionado a que el empleado tenga más de una capacidad:

```html
<template x-if="capacidades.length > 1">
  <div class="border-t border-white/10 mt-2 pt-2 text-center">
    <button @click="cambiarRol()" class="text-xs text-blue-200">
      ⇄ Cambiar a <span x-text="rolOpuesto"></span>
      <!-- rolOpuesto asume exactamente 2 capacidades (picker/repartidor).
           Si en el futuro hay más roles, reemplazar por un selector. -->
    </button>
  </div>
</template>
```

### Alpine component — datos nuevos
- `capacidades: []` — cargado desde `/empleado/capacidades`
- `async cambiarRol()` — llama a `POST /empleado/cambiar-rol`, maneja bloqueo con modal
- Modal de bloqueo: lista pedidos activos + botón "Ir a terminarlos"

### Redirect a check-in

**Mecanismo primario — server-side:** La ruta `/empleado` comprueba en Python si el empleado es polivalente y no tiene `rol_activo` en BD (no en sesión, para sobrevivir restauraciones de sesión):

```python
@blueprint_empleado.route('/empleado', strict_slashes=False)
@requiere_rol(*_ROLES_HUB)
def index():
    empleado_id = session.get('empleado_id')
    # Redirigir a check-in solo si: polivalente Y sin rol_activo en BD
    # Usar BD (no sesión) para que sobreviva cierre/reapertura del navegador
    if gestor_empleado.es_polivalente(empleado_id) and not gestor_empleado.tiene_rol_activo(empleado_id):
        return redirect('/empleado/checkin')
    return render_template('empleado/index.html', ...)
```

`rol_activo` en BD se setea en `POST /empleado/cambiar-rol`. Se pone a `NULL` solo al hacer logout (`session.clear()` + `empleado.rol_activo = None`).

**Esto resuelve la restauración de sesión:** si el empleado cierra el navegador y vuelve a conectar con la misma sesión Flask activa, `rol_activo` ya está en BD → no se redirige a check-in.

**Mecanismo secundario — cliente:** El Alpine `init()` puede reforzar con `sessionStorage` como fallback UX (para nuevas pestañas), pero no es el control primario.

---

## Pantalla de check-in (`templates/empleado/checkin.html`)

Pantalla nueva, diseño aprobado. Elementos:
- Header igual al hub (fecha, saludo, nombre)
- Título "¿Cómo entras hoy?"
- Turno del día (hora_inicio – hora_fin) si existe
- Sugerencia del manager si `turno.rol_planificado` está seteado (★)
- Dos cards grandes (picker / repartidor) con carga operativa en tiempo real
- Cada card: emoji grande, nombre del rol, contador de pedidos en cola
- Nota pie: "Podrás cambiarlo más tarde si hace falta"
- Tecnología: Alpine.js + Tailwind, consistente con el resto del módulo

Al confirmar rol:
1. `POST /empleado/cambiar-rol`
2. `sessionStorage.setItem('checkin_date', new Date().toDateString())`
3. Redirect a `/empleado`

---

## Estados operativos

| Estado | Quién lo setea | Cambio de rol | Acceso a app |
|---|---|---|---|
| `desconectado` | Empleado (logout / "Salir") | — | No |
| `disponible` | Sistema (tras check-in) | Sí, si no hay activas | Sí |
| `ocupado` | Sistema (tarea asignada) | No | Sí (ya está en ella) |
| `en_pausa` | Empleado | Sí | No (hasta volver) |

El campo `estado_operativo` en `Empleado` ya existe. No cambia su estructura.

---

## Trazabilidad — AuditLog

**Migración requerida:** en `models.py`, `AuditLog.pedido_id` está definido como `nullable=False`. Para registrar eventos de empleado sin pedido asociado, hay que migrarlo:

```python
# models.py — cambio en AuditLog
pedido_id = Column(Integer, ForeignKey('pedidos.PedidoID'), nullable=True)  # era False
```

```sql
-- SQL Server
ALTER TABLE audit_log ALTER COLUMN pedido_id INT NULL;
```

Eventos nuevos registrados en `audit_log`:

| `accion` | `empleado_id` | `pedido_id` | `detalles` (JSON) |
|---|---|---|---|
| `checkin` | ✓ | NULL | `{rol, turno_id}` |
| `cambio_rol` | ✓ | NULL | `{de: "picker", a: "repartidor"}` |
| `cambio_rol_bloqueado` | ✓ | NULL | `{rol_destino, pedidos_activos: [...]}` |

> Este cambio en `nullable` no afecta a los registros existentes en `audit_log`, que siempre tienen `pedido_id` relleno.

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Sesión expira con rol activo en mitad de turno | Al re-login, restaurar `empleado.rol_activo` si la capacidad sigue vigente |
| Empleado sin capacidades asignadas | Hub muestra mensaje "Contacta al manager para que te asigne un rol" en lugar de CTA |
| Manager no asigna capacidades al crear empleado | Migración inicial cubre todos los existentes; el panel de gestión de capacidades en dashboard (Fase 2) lo resuelve de forma permanente |
| Métricas inconsistentes tras múltiples cambios de rol | Las métricas usan `PickingPedido.empleado_id` y `Reparto.repartidor_id` directamente — son precisas independientemente del rol de sesión actual |
| Acceso cruzado a picker siendo repartidor | `requiere_rol` bloquea por `session['rol']`; al cambiar rol se actualiza la sesión — protección automática |

---

## Arquitectura de pantallas

```
/auth/login
    └─→ /empleado  (hub)
            ├─→ /empleado/checkin  [NUEVO]  ← primer acceso del día si polivalente
            │       └─→ POST /empleado/cambiar-rol  [NUEVO]
            │               └─→ /empleado
            ├─→ /picker  (sin cambios)
            ├─→ /repartidor  (sin cambios)
            └─→ "⇄ Cambiar rol"  → POST /empleado/cambiar-rol  [NUEVO]
                                        ├─→ OK: hub actualizado
                                        └─→ 409: modal de bloqueo con pedidos activos
```

---

## Fases de implementación

### Fase 1 — Este sprint (MVP)
- [ ] Tabla `empleado_capacidades` + modelo SQLAlchemy
- [ ] Columna `rol_activo` en `empleados`
- [ ] Migración de datos desde `rol_id` actual
- [ ] Métodos nuevos en `GestorEmpleado`
- [ ] Endpoints nuevos en `blueprints/empleado.py`
- [ ] Pantalla `/empleado/checkin`
- [ ] Hub actualizado (capacidades, enlace cambiar rol, modal bloqueo)
- [ ] Lógica de login actualizada en `auth.py`
- [ ] Tests unitarios para `cambiar_rol` (bloqueo, éxito, sin capacidad)

### Fase 2 — Horarios
- [ ] Columna `rol_planificado` en `turnos`
- [ ] `/empleado/turnos` — vista calendario + lista
- [ ] `/empleado/historial` — días trabajados con rol real vs planificado
- [ ] Check-in muestra sugerencia del manager

### Fase 3 — Estadísticas y panel admin
- [ ] `/empleado/estadisticas` — KPIs semana/mes por rol
- [ ] Panel en dashboard: gestión de capacidades de empleados
- [ ] Notificación push cuando hay pico de demanda en una cola

---

## Resumen de cambios por archivo

| Archivo | Tipo de cambio |
|---|---|
| `models.py` | Nuevo modelo `EmpleadoCapacidad`; columna `rol_activo` en `Empleado`; `AuditLog.pedido_id` → nullable |
| `blueprints/auth.py` | Lógica de login actualizada; nuevo helper `requiere_autenticacion`; `session['checkin_hoy']` cleared en logout |
| `blueprints/empleado.py` | 4 endpoints nuevos; redirect a check-in server-side en `/empleado` |
| `managers/gestor_empleado.py` | 5 métodos nuevos: `capacidades`, `es_polivalente`, `tiene_rol_activo`, `cambiar_rol`, `carga_operativa` |
| `templates/empleado/index.html` | Alpine: carga capacidades, enlace cambiar rol, modal bloqueo |
| `templates/empleado/checkin.html` | Pantalla nueva |
| `services/__init__.py` | Sin cambios (gestor_empleado ya está registrado) |
| `blueprints/picker.py` | Sin cambios |
| `blueprints/repartidor.py` | Sin cambios |
| Decorator `requiere_rol` | Sin cambios |
| `templates/picker/index.html` | Sin cambios |
| `templates/repartidor/index.html` | Sin cambios |
