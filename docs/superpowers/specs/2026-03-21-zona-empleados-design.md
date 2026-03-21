# Zona de empleados — Sub-proyecto 1: Hub + Estado operativo

**Fecha:** 2026-03-21
**Estado:** Aprobado
**Proyecto:** panchi-bot
**Rama base:** refactorizar-estructura

---

## Contexto

El sistema actual envía al picker directamente a `/picker` y al repartidor directamente a `/repartidor` tras el login. No existe ninguna capa intermedia ni concepto de "estado operativo" del empleado. El manager solo puede deducir si alguien está activo mirando si tiene pickings o repartos abiertos.

Este sub-proyecto añade:
1. Una **zona de empleados centralizada** (`/empleado`) como hub post-login.
2. Un **estado operativo** por empleado visible en el dashboard del manager.

Sub-proyectos futuros (fuera de scope aquí): autoasignación de pedidos, horarios gestionables, métricas históricas avanzadas.

---

## Decisiones de diseño

| Pregunta | Decisión |
|---|---|
| Estructura de navegación | Hub con tarjetas (opción A) |
| Apps picker/repartidor | Se mantienen intactas; el hub es la capa de entrada |
| Estados operativos | 4: `disponible`, `ocupado`, `en_pausa`, `desconectado` |
| Gestión del estado | Semi-automática: sistema actualiza `ocupado`/`disponible`; empleado controla `en_pausa`/`desconectado` |
| Persistencia del estado | Columna `estado_operativo` en tabla `empleados` (BD SQL Server) |
| Tiempo real en dashboard | Polling existente (sin SSE ni WebSockets) |

---

## Alcance

### Incluido

- Nuevo blueprint `empleado` con rutas `/empleado`, `/empleado/perfil`, `/empleado/estado`, `/empleado/turno-hoy`, `/empleado/metricas`
- Nuevo template `templates/empleado/index.html` (Tailwind + Alpine.js, mobile-first)
- Columna `estado_operativo VARCHAR(20) NOT NULL DEFAULT 'desconectado'` en tabla `empleados`
- Modelo `Turno` mínimo (solo lectura desde la vista del empleado; sin UI de gestión en esta fase)
- Hooks en `GestorDashboard` para actualizar estado automáticamente
- Cambio en `blueprints/auth.py`: picker y repartidor redirigen a `/empleado` en lugar de sus apps directas
- Actualización de `monitor_empleados()` para exponer `estado_operativo`

### Excluido

- Gestión de turnos por parte del manager (fase futura)
- Autoasignación de pedidos (sub-proyecto 2)
- Métricas históricas avanzadas (sub-proyecto 3)
- Notificaciones push / SSE
- Página de desempeño detallada (solo stats del día en el hub)

---

## Modelo de datos

### Cambio en tabla `empleados`

```sql
ALTER TABLE empleados
ADD estado_operativo VARCHAR(20) NOT NULL DEFAULT 'desconectado';
```

Valores válidos: `disponible` | `ocupado` | `en_pausa` | `desconectado`

**Regla:** El sistema solo sobreescribe el estado hacia `ocupado` o `disponible`. Nunca sobreescribe `en_pausa` ni `desconectado`.

### Nueva tabla `turnos` (mínima)

```sql
CREATE TABLE turnos (
    id          INT PRIMARY KEY IDENTITY,
    empleado_id INT NOT NULL REFERENCES empleados(EmpleadoID),
    fecha       DATE NOT NULL,
    hora_inicio TIME NOT NULL,
    hora_fin    TIME NOT NULL,
    notas       VARCHAR(255) NULL
);
```

Sin UI de gestión en esta fase. El template muestra el turno si existe, o un placeholder neutral si no.

### Nuevo modelo ORM `Turno` en `models.py`

```python
class Turno(Base):
    __tablename__ = 'turnos'
    id          = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=False)
    fecha       = Column(Date, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fin    = Column(Time, nullable=False)
    notas       = Column(String(255), nullable=True)
    empleado    = relationship('Empleado', back_populates='turnos')
```

Añadir en `Empleado`:
```python
turnos = relationship('Turno', back_populates='empleado', order_by='Turno.fecha')
```

---

## Nuevas rutas — blueprint `empleado`

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| `GET` | `/empleado` | `picker`, `repartidor`, `manager`, `admin` | Renderiza hub (`empleado/index.html`) |
| `GET` | `/empleado/perfil` | mismos roles | JSON con datos del empleado y estado |
| `POST` | `/empleado/estado` | mismos roles | Cambia estado a `en_pausa` o `desconectado` (solo estos dos) |
| `GET` | `/empleado/turno-hoy` | mismos roles | JSON con el turno del día, o `null` |
| `GET` | `/empleado/metricas` | mismos roles | JSON: `{pedidos_completados, tiempo_medio_min, incidencias_hoy}` |

### Payload `POST /empleado/estado`

```json
{ "estado": "en_pausa" }   // o "desconectado"
```

Validación: rechazar si `estado` no es `en_pausa` o `desconectado`. El empleado no puede fijarse como `disponible` u `ocupado` manualmente.

---

## Automatismos de estado en `GestorDashboard`

Añadir una función helper privada en `gestor_dashboard.py`:

```python
def _actualizar_estado_operativo(self, empleado_id: int, nuevo_estado: str) -> None:
    """Actualiza estado_operativo solo si el estado actual no es en_pausa ni desconectado."""
    ESTADOS_PROTEGIDOS = {'en_pausa', 'desconectado'}
    empleado = self.session.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
    if empleado and empleado.estado_operativo not in ESTADOS_PROTEGIDOS:
        empleado.estado_operativo = nuevo_estado
```

Hooks en métodos existentes (sin cambiar su firma ni retorno):

| Método | Momento | Acción |
|---|---|---|
| `asignar_picker(pedido_id, empleado_id)` | Tras `s.commit()` exitoso | `_actualizar_estado_operativo(empleado_id, 'ocupado')` — `empleado_id` viene del argumento del método |
| `completar_picking(picking_id, picker_id)` | Tras `s.commit()` exitoso | Usar `picking.empleado_id` (no el argumento `picker_id`, que puede ser `None`); comprobar si tiene más pickings activos; si no → `_actualizar_estado_operativo(picking.empleado_id, 'disponible')` |
| `asignar_repartidor(pedido_id, empleado_id)` | Tras `s.commit()` exitoso | `_actualizar_estado_operativo(empleado_id, 'ocupado')` — `empleado_id` viene del argumento del método |
| `marcar_entregado(reparto_id)` | Tras `s.commit()` exitoso | Usar `reparto.repartidor_id` (leer del ORM ya cargado); comprobar si tiene más repartos activos; si no → `_actualizar_estado_operativo(reparto.repartidor_id, 'disponible')` |

`reasignar_picker()` **no tiene hook**: el cambio de estado automático solo se dispara en la primera asignación (`asignar_picker`). Una reasignación mantiene el estado del picker original y el nuevo ya estará marcado como `ocupado` por la asignación anterior si corresponde.

---

## Cambios en auth

En `blueprints/auth.py`, función `login()`, actualizar el dict `destinos`:

```python
destinos = {
    'manager':     '/dashboard',
    'admin':       '/dashboard',
    'picker':      '/empleado',   # antes: '/picker'
    'repartidor':  '/empleado',   # antes: '/repartidor'
}
```

---

## Template `empleado/index.html`

Stack: Tailwind CDN + Alpine.js (idéntico a `picker/index.html` y `repartidor/index.html`).

### Secciones en orden vertical

1. **Header** — nombre del empleado, rol, fecha/hora, botón logout
2. **Bloque estado operativo** — badge con color según estado; botones "Pausa" y "Salir" (desactivados si el estado es `ocupado`)
3. **Bloque turno de hoy** — hora inicio/fin y notas si hay turno; placeholder neutral si no hay
4. **CTA principal** — tarjeta grande hacia `/picker` o `/repartidor` según rol; color azul (picker) / naranja (repartidor); muestra conteo de pedidos asignados ahora
5. **Stats del día** — 3 cifras: pedidos completados, tiempo medio, incidencias
6. **Accesos secundarios** — 3 iconos: Desempeño, Turnos, (Cierre para repartidor / Empresa para picker)

### Colores de estado

| Estado | Color |
|---|---|
| `disponible` | `#10b981` (verde) |
| `ocupado` | `#f59e0b` (ámbar) |
| `en_pausa` | `#8b5cf6` (violeta) |
| `desconectado` | `#6b7280` (gris) |

### Comportamiento Alpine

- `init()` carga `/empleado/perfil`, `/empleado/turno-hoy` y `/empleado/metricas` en paralelo
- El Alpine component maneja el estado localmente y sincroniza con `POST /empleado/estado`
- Sin polling automático (la info del hub no es crítica en tiempo real)

---

## Cambios en `monitor_empleados()`

Añadir `estado_operativo` al dict que devuelve cada empleado:

```python
"estado_operativo": e.estado_operativo,
```

El dashboard ya consume este dict; simplemente tendrá el campo nuevo disponible.

---

## Archivos a tocar

| Archivo | Tipo de cambio |
|---|---|
| `models.py` | Añadir columna `estado_operativo` en `Empleado`; añadir modelo `Turno` |
| `blueprints/auth.py` | Cambiar destino de login para picker y repartidor |
| `blueprints/empleado.py` | **NUEVO** — blueprint con 5 rutas |
| `managers/gestor_dashboard.py` | Añadir `_actualizar_estado_operativo()` + 4 hooks |
| `managers/gestor_empleado.py` | **NUEVO** — lógica de perfil, estado, turno, métricas del empleado |
| `templates/empleado/index.html` | **NUEVO** — hub template |
| `main.py` (o donde se registran blueprints) | Registrar `blueprint_empleado` |
| `scripts/migrar_empleado.py` | **NUEVO** — script de migración SQL (ALTER TABLE + CREATE TABLE) |

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Migración ALTER TABLE en producción | Script de migración idempotente; probar en staging primero |
| Estado queda desincronizado si el proceso muere entre asignación y hook | Aceptable: el manager siempre puede reasignar; el estado se corregirá en la siguiente operación |
| Empleado en `en_pausa` recibe asignación desde dashboard | Válido intencionalmente: el manager puede asignar aunque el empleado esté en pausa; el hook no sobreescribe el estado manual |
| El picker accede a `/picker` directamente sin pasar por el hub | Las rutas `/picker` y `/repartidor` siguen requiriendo solo `requiere_rol` activo — no se fuerza el paso por el hub |

---

## Criterios de éxito

- Tras el login, picker y repartidor ven el hub `/empleado` antes de entrar a su app
- El empleado puede marcarse en pausa y el dashboard lo refleja en el siguiente ciclo de polling
- Cuando se le asigna un picking o reparto, el estado cambia a `ocupado` automáticamente
- Cuando completa su último trabajo activo, el estado vuelve a `disponible`
- Si no hay turno registrado, la UI muestra un placeholder sin errores
- Las apps `/picker` y `/repartidor` siguen funcionando exactamente igual que antes
