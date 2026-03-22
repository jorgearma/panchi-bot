# Check-in y registro de tiempo de empleados — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir fichaje de entrada/salida con desglose automático por rol (picker/repartidor) visible en `/empleado`.

**Architecture:** Dos tablas nuevas (`check_ins`, `tramos_turno`) completamente independientes del resto del modelo. Hooks en `cambiar_rol` y `cambiar_estado` de `GestorEmpleado` generan tramos automáticamente. El frontend Alpine.js llama a 3 endpoints nuevos y muestra un resumen al empleado.

**Tech Stack:** Flask, SQLAlchemy, SQL Server, Alpine.js, Tailwind CSS, pytest + MagicMock.

---

## Aviso importante: rutas existentes

`/empleado/checkin` (GET) ya existe — renderiza la pantalla de selección de rol para empleados polivalentes. Los nuevos endpoints de fichaje usan el prefijo `/empleado/fichaje` para no colisionar.

---

## Archivos a modificar/crear

| Archivo | Acción |
|---------|--------|
| `models.py` | Añadir clases `CheckIn` y `TramoTurno` |
| `migrations/add_check_ins.sql` | Script SQL para crear tablas en producción |
| `managers/gestor_empleado.py` | Añadir `iniciar_turno`, `cerrar_turno`, `checkin_hoy`, `_cerrar_tramo_activo`, `_abrir_tramo`. Hooks en `cambiar_estado` y `cambiar_rol` |
| `blueprints/empleado.py` | Añadir rutas `POST /empleado/fichaje`, `POST /empleado/fichaje/cerrar`, `GET /empleado/fichaje/hoy` |
| `templates/empleado/index.html` | Modificar bloque "Mi estado", añadir sección "Mi turno de hoy" |
| `tests/test_checkin_empleado.py` | Tests unitarios de los métodos del gestor |

---

## Task 1: Modelos ORM y script de migración

**Files:**
- Modify: `models.py`
- Create: `migrations/add_check_ins.sql`

- [ ] **Step 1: Añadir `CheckIn` y `TramoTurno` a `models.py`**

Al final de `models.py`, tras la clase `Turno`, añadir:

```python
# ---------------------------------------------------------------------------
# Fichaje / Check-in
# ---------------------------------------------------------------------------

class CheckIn(Base):
    """Turno real fichado por el empleado. Uno por empleado por día."""
    __tablename__ = 'check_ins'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=False)
    fecha       = Column(Date, nullable=False)
    inicio      = Column(DateTime, nullable=False)
    fin         = Column(DateTime, nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    empleado = relationship('Empleado', back_populates='check_ins')
    tramos   = relationship('TramoTurno', back_populates='check_in',
                            cascade='all, delete-orphan', order_by='TramoTurno.inicio')

    __table_args__ = (
        UniqueConstraint('empleado_id', 'fecha', name='uq_checkin_empleado_fecha'),
    )


class TramoTurno(Base):
    """Segmento de tiempo trabajado en un rol concreto dentro de un check-in."""
    __tablename__ = 'tramos_turno'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    check_in_id = Column(Integer, ForeignKey('check_ins.id'), nullable=False)
    rol         = Column(String(20), nullable=False)   # picker | repartidor
    inicio      = Column(DateTime, nullable=False)
    fin         = Column(DateTime, nullable=True)

    check_in = relationship('CheckIn', back_populates='tramos')
```

- [ ] **Step 2: Añadir relación `check_ins` en `Empleado`**

En la clase `Empleado`, añadir tras `turnos = relationship(...)`:

```python
check_ins = relationship('CheckIn', back_populates='empleado',
                         order_by='CheckIn.fecha')
```

- [ ] **Step 3: Crear `migrations/add_check_ins.sql`**

```sql
-- Ejecutar en producción ANTES de desplegar el código
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

- [ ] **Step 4: Verificar que el import de `UniqueConstraint` ya existe en `models.py`**

La línea 2 de `models.py` ya importa `UniqueConstraint` — no hace falta añadirlo.

- [ ] **Step 5: Commit**

```bash
git add models.py migrations/add_check_ins.sql
git commit -m "feat: add CheckIn and TramoTurno models"
```

---

## Task 2: Lógica de negocio en GestorEmpleado

**Files:**
- Modify: `managers/gestor_empleado.py`
- Create: `tests/test_checkin_empleado.py`

- [ ] **Step 1: Escribir los tests primero**

Crear `tests/test_checkin_empleado.py`:

```python
"""Tests para la lógica de fichaje en GestorEmpleado."""
from datetime import datetime, date
from unittest.mock import patch, MagicMock, PropertyMock


def _make_gestor(check_in_mock=None, empleado_mock=None):
    from managers.gestor_empleado import GestorEmpleado
    gestor = GestorEmpleado()
    session_mock = MagicMock()
    if empleado_mock is None:
        empleado_mock = MagicMock()
        empleado_mock.EmpleadoID = 1
        empleado_mock.rol_activo = 'picker'
    session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
    session_mock.query.return_value.filter.return_value.first.return_value = check_in_mock
    return gestor, session_mock, empleado_mock


class TestIniciarTurno:

    def test_crea_checkin_sin_rol_activo(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        empleado_mock = MagicMock()
        empleado_mock.rol_activo = None
        session_mock = MagicMock()
        # No hay check-in previo
        session_mock.query.return_value.filter.return_value.first.return_value = None
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.iniciar_turno(1)
        session_mock.add.assert_called()
        session_mock.commit.assert_called()

    def test_lanza_error_si_ya_hay_checkin_abierto(self):
        import pytest
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        check_in_existente = MagicMock()
        check_in_existente.fin = None  # abierto
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = check_in_existente
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with pytest.raises(ValueError, match='ya_abierto'):
                gestor.iniciar_turno(1)

    def test_crea_tramo_si_tiene_rol_activo(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        empleado_mock = MagicMock()
        empleado_mock.rol_activo = 'picker'
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = None
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        added = []
        session_mock.add.side_effect = lambda obj: added.append(obj)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor.iniciar_turno(1)
        from models import TramoTurno
        tramos = [o for o in added if isinstance(o, TramoTurno)]
        assert len(tramos) == 1
        assert tramos[0].rol == 'picker'


class TestCerrarTurno:

    def test_lanza_error_si_no_hay_checkin(self):
        import pytest
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = None
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with pytest.raises(ValueError, match='no_abierto'):
                gestor.cerrar_turno(1)

    def test_cierra_checkin_y_devuelve_resumen(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        ahora = datetime.utcnow()
        tramo_mock = MagicMock()
        tramo_mock.rol = 'picker'
        tramo_mock.inicio = ahora.replace(hour=9, minute=0)
        tramo_mock.fin = ahora.replace(hour=11, minute=0)
        check_in_mock = MagicMock()
        check_in_mock.fin = None
        check_in_mock.inicio = ahora.replace(hour=9, minute=0)
        check_in_mock.tramos = [tramo_mock]
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = check_in_mock
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.cerrar_turno(1)
        assert check_in_mock.fin is not None
        assert 'tramos' in result


class TestCheckinHoy:

    def test_devuelve_falso_si_no_hay_checkin(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = None
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.checkin_hoy(1)
        assert result['activo'] is False

    def test_devuelve_resumen_con_checkin_activo(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        ahora = datetime.utcnow()
        tramo_mock = MagicMock()
        tramo_mock.rol = 'picker'
        tramo_mock.inicio = ahora.replace(hour=9, minute=0)
        tramo_mock.fin = ahora.replace(hour=10, minute=0)
        check_in_mock = MagicMock()
        check_in_mock.fin = None
        check_in_mock.inicio = ahora.replace(hour=9, minute=0)
        check_in_mock.tramos = [tramo_mock]
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = check_in_mock
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.checkin_hoy(1)
        assert result['activo'] is True
        assert len(result['tramos']) == 1
        assert result['tramos'][0]['rol'] == 'picker'
```

- [ ] **Step 2: Ejecutar tests — deben fallar**

```bash
cd /home/siemprearmando/proyectos/panchi-bot
pytest tests/test_checkin_empleado.py -v --tb=short
```
Esperado: ImportError o AttributeError — los métodos no existen aún.

- [ ] **Step 3: Añadir import de `CheckIn` y `TramoTurno` en `gestor_empleado.py`**

Cambiar línea 6:
```python
from models import Empleado, Turno, PickingPedido, Reparto, CheckIn, TramoTurno
```

- [ ] **Step 4: Añadir helpers privados y métodos principales**

En `GestorEmpleado`, añadir tras el método `cambiar_rol` (después de la línea `return False, 'Error de base de datos', []`):

```python
    # -------------------------------------------------------------------------
    # Fichaje / Check-in
    # -------------------------------------------------------------------------

    def _checkin_abierto_hoy(self, empleado_id: int):
        """Devuelve el CheckIn abierto de hoy o None."""
        hoy = datetime.utcnow().date()
        return self.session.query(CheckIn).filter(
            CheckIn.empleado_id == empleado_id,
            CheckIn.fecha == hoy,
            CheckIn.fin == None,
        ).first()

    def _cerrar_tramo_activo(self, check_in, ahora: datetime):
        """Cierra el TramoTurno sin fin de este check-in. Safe si no hay ninguno."""
        tramo = self.session.query(TramoTurno).filter(
            TramoTurno.check_in_id == check_in.id,
            TramoTurno.fin == None,
        ).first()
        if tramo:
            tramo.fin = ahora

    def _abrir_tramo(self, check_in, rol: str, ahora: datetime):
        """Crea un nuevo TramoTurno abierto."""
        tramo = TramoTurno(check_in_id=check_in.id, rol=rol, inicio=ahora)
        self.session.add(tramo)

    def iniciar_turno(self, empleado_id: int) -> CheckIn:
        """Crea un CheckIn para hoy. Lanza ValueError('ya_abierto') si ya existe uno."""
        s = self.session
        ahora = datetime.utcnow()
        hoy = ahora.date()

        existente = s.query(CheckIn).filter(
            CheckIn.empleado_id == empleado_id,
            CheckIn.fecha == hoy,
            CheckIn.fin == None,
        ).first()
        if existente:
            raise ValueError('ya_abierto')

        empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
        check_in = CheckIn(empleado_id=empleado_id, fecha=hoy, inicio=ahora)
        s.add(check_in)
        s.flush()  # necesario para obtener check_in.id antes de crear el tramo

        if empleado and empleado.rol_activo:
            self._abrir_tramo(check_in, empleado.rol_activo, ahora)
            if empleado.estado_operativo in ('desconectado', 'en_pausa'):
                empleado.estado_operativo = 'disponible'

        s.commit()
        logger.info("CHECKIN empleado_id=%s inicio=%s", empleado_id, ahora.isoformat())
        return check_in

    def cerrar_turno(self, empleado_id: int) -> dict:
        """Cierra el CheckIn activo de hoy. Lanza ValueError('no_abierto') si no hay ninguno."""
        s = self.session
        ahora = datetime.utcnow()

        check_in = self._checkin_abierto_hoy(empleado_id)
        if not check_in:
            raise ValueError('no_abierto')

        self._cerrar_tramo_activo(check_in, ahora)
        check_in.fin = ahora
        s.commit()
        logger.info("CHECKOUT empleado_id=%s fin=%s", empleado_id, ahora.isoformat())
        return self._resumen_checkin(check_in, ahora)

    def checkin_hoy(self, empleado_id: int) -> dict:
        """Estado del check-in de hoy (abierto o cerrado). Nunca lanza."""
        hoy = datetime.utcnow().date()
        check_in = self.session.query(CheckIn).filter(
            CheckIn.empleado_id == empleado_id,
            CheckIn.fecha == hoy,
        ).first()
        if not check_in:
            return {'activo': False}
        ahora = datetime.utcnow()
        return self._resumen_checkin(check_in, ahora)

    def _resumen_checkin(self, check_in, ahora: datetime) -> dict:
        """Calcula duración total y por rol. Tramos abiertos usan ahora como fin provisional."""
        fin_efectivo = check_in.fin or ahora
        total_min = int((fin_efectivo - check_in.inicio).total_seconds() / 60)

        tramos_resumen = []
        for t in check_in.tramos:
            t_fin = t.fin or ahora
            minutos = int((t_fin - t.inicio).total_seconds() / 60)
            tramos_resumen.append({'rol': t.rol, 'minutos': minutos})

        return {
            'activo':            check_in.fin is None,
            'inicio':            check_in.inicio.isoformat(),
            'fin':               check_in.fin.isoformat() if check_in.fin else None,
            'duracion_total_min': total_min,
            'tramos':            tramos_resumen,
        }
```

- [ ] **Step 5: Añadir hooks en `cambiar_estado`**

En el método `cambiar_estado`, justo antes de `s.commit()` (tras `empleado.estado_operativo = nuevo_estado`):

```python
            # Hook fichaje: pausar cierra tramo activo
            if nuevo_estado == 'en_pausa':
                check_in = self._checkin_abierto_hoy(empleado_id)
                if check_in:
                    self._cerrar_tramo_activo(check_in, datetime.utcnow())
            # Hook fichaje: desconectarse cierra tramo y check-in
            elif nuevo_estado == 'desconectado':
                check_in = self._checkin_abierto_hoy(empleado_id)
                if check_in:
                    ahora = datetime.utcnow()
                    self._cerrar_tramo_activo(check_in, ahora)
                    check_in.fin = ahora
```

- [ ] **Step 6: Añadir hook en `cambiar_rol`**

En el método `cambiar_rol`, justo antes de `s.commit()` (tras `empleado.estado_operativo = 'disponible'`):

```python
            # Hook fichaje: cierra tramo anterior y abre uno nuevo
            check_in = self._checkin_abierto_hoy(empleado_id)
            if check_in:
                ahora = datetime.utcnow()
                self._cerrar_tramo_activo(check_in, ahora)
                self._abrir_tramo(check_in, nuevo_rol, ahora)
```

- [ ] **Step 7: Ejecutar tests — deben pasar**

```bash
pytest tests/test_checkin_empleado.py -v --tb=short
```
Esperado: todos PASS.

- [ ] **Step 8: Ejecutar suite completa para verificar no hay regresiones**

```bash
pytest -v --tb=short
```
Esperado: los 3 tests pre-existentes de `TestWebhookMonei` siguen fallando (conocido), el resto PASS.

- [ ] **Step 9: Commit**

```bash
git add managers/gestor_empleado.py tests/test_checkin_empleado.py
git commit -m "feat: add iniciar_turno, cerrar_turno, checkin_hoy and role/state hooks"
```

---

## Task 3: Endpoints en el blueprint

**Files:**
- Modify: `blueprints/empleado.py`

- [ ] **Step 1: Añadir los tres endpoints al final de `blueprints/empleado.py`**

```python
@blueprint_empleado.route('/empleado/fichaje', methods=['POST'])
@requiere_rol(*_ROLES_HUB)
def fichaje_iniciar():
    empleado_id = session.get('empleado_id')
    try:
        check_in = gestor_empleado.iniciar_turno(empleado_id)
        return jsonify({'ok': True, 'check_in_id': check_in.id,
                        'inicio': check_in.inicio.isoformat()})
    except ValueError as e:
        if str(e) == 'ya_abierto':
            return jsonify({'error': 'Ya tienes un turno abierto hoy'}), 409
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error("Error en /empleado/fichaje: %s", e)
        return jsonify({'error': 'Error interno'}), 500


@blueprint_empleado.route('/empleado/fichaje/cerrar', methods=['POST'])
@requiere_rol(*_ROLES_HUB)
def fichaje_cerrar():
    empleado_id = session.get('empleado_id')
    try:
        resumen = gestor_empleado.cerrar_turno(empleado_id)
        return jsonify({'ok': True, **resumen})
    except ValueError as e:
        if str(e) == 'no_abierto':
            return jsonify({'error': 'No tienes un turno abierto'}), 400
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        logger.error("Error en /empleado/fichaje/cerrar: %s", e)
        return jsonify({'error': 'Error interno'}), 500


@blueprint_empleado.route('/empleado/fichaje/hoy')
@requiere_rol(*_ROLES_HUB)
def fichaje_hoy():
    empleado_id = session.get('empleado_id')
    try:
        return jsonify(gestor_empleado.checkin_hoy(empleado_id))
    except Exception as e:
        logger.error("Error en /empleado/fichaje/hoy: %s", e)
        return jsonify({'activo': False})
```

- [ ] **Step 2: Ejecutar suite de tests**

```bash
pytest -v --tb=short
```
Esperado: sin regresiones nuevas.

- [ ] **Step 3: Commit**

```bash
git add blueprints/empleado.py
git commit -m "feat: add /empleado/fichaje endpoints"
```

---

## Task 4: Frontend en `/empleado`

**Files:**
- Modify: `templates/empleado/index.html`

### Contexto del HTML existente

- Alpine.js con `x-data="empleadoHub(...)"` y `x-init="init()"`
- Estado actual en la variable Alpine `perfil.estado_operativo`
- `init()` llama a `cargarPerfil()`, `cargarTurno()`, `cargarMetricas()`, `cargarCapacidades()`
- El bloque "Mi estado" (línea ~48) muestra botones ⏸ y ⏹

### Cambios necesarios

- [ ] **Step 1: Añadir `fichajeActivo`, `fichajeResumen` al estado Alpine y `cargarFichaje()` a `init()`**

En el estado Alpine (buscar `tabActiva:` o `pedidosAsignados:`), añadir:
```javascript
fichajeActivo: false,
fichajeInicio: null,
fichajeResumen: null,
```

En `init()`, añadir `this.cargarFichaje()` junto a las otras llamadas de carga.

- [ ] **Step 2: Añadir método `cargarFichaje()` en el bloque `<script>`**

```javascript
async cargarFichaje() {
  try {
    const r = await fetch('/empleado/fichaje/hoy');
    if (r.ok) {
      const d = await r.json();
      this.fichajeActivo = d.activo || false;
      this.fichajeInicio = d.inicio || null;
      this.fichajeResumen = d;
    }
  } catch (_) {}
},

async iniciarTurno() {
  try {
    const r = await fetch('/empleado/fichaje', { method: 'POST' });
    if (r.ok) {
      await this.cargarFichaje();
    } else {
      const d = await r.json();
      alert(d.error || 'Error al iniciar turno');
    }
  } catch (_) { alert('Error de conexión'); }
},

async cerrarTurno() {
  if (!confirm('¿Cerrar el turno ahora?')) return;
  try {
    const r = await fetch('/empleado/fichaje/cerrar', { method: 'POST' });
    if (r.ok) {
      await this.cargarFichaje();
    } else {
      const d = await r.json();
      alert(d.error || 'Error al cerrar turno');
    }
  } catch (_) { alert('Error de conexión'); }
},

formatMinutos(min) {
  if (!min) return '0 min';
  const h = Math.floor(min / 60);
  const m = min % 60;
  if (h === 0) return m + ' min';
  if (m === 0) return h + 'h';
  return h + 'h ' + m + 'min';
},

formatHoraISO(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
},
```

- [ ] **Step 3: Modificar bloque "Mi estado"**

Reemplazar el bloque actual (desde `<!-- Estado operativo -->` hasta el cierre `</div>` del bloque):

```html
<!-- Estado operativo + fichaje -->
<div :class="estadoBg" class="rounded-xl p-3 border">
  <div class="flex items-center justify-between">
    <div>
      <p class="text-xs text-gray-400 uppercase tracking-wide">Mi estado</p>
      <p class="font-bold text-sm mt-0.5" :class="estadoColor">
        <span>● </span><span x-text="estadoLabel"></span>
        <span x-show="fichajeActivo && fichajeInicio" x-cloak
              class="font-normal text-gray-400 ml-1"
              x-text="'desde las ' + formatHoraISO(fichajeInicio)"></span>
      </p>
      <p x-show="perfil.estado_operativo === 'ocupado'"
         class="text-xs text-gray-500 mt-0.5" x-cloak>Asignado por el sistema</p>
    </div>
    <div class="flex gap-2">
      <!-- Sin turno abierto: botón iniciar -->
      <button x-show="!fichajeActivo"
              @click="iniciarTurno()"
              class="bg-green-600 text-white text-xs px-3 py-1.5 rounded-lg transition active:bg-green-700 font-semibold">
        ▶ Iniciar turno
      </button>
      <!-- Con turno abierto: pausa + cerrar -->
      <template x-if="fichajeActivo">
        <div class="flex gap-2">
          <button @click="cambiarEstado('en_pausa')"
                  :disabled="perfil.estado_operativo === 'ocupado'"
                  :class="perfil.estado_operativo === 'ocupado' ? 'opacity-40 cursor-not-allowed' : 'active:bg-gray-600'"
                  class="bg-gray-700 text-gray-300 text-xs px-3 py-1.5 rounded-lg transition">
            ⏸ Pausa
          </button>
          <button @click="cerrarTurno()"
                  :disabled="perfil.estado_operativo === 'ocupado'"
                  :class="perfil.estado_operativo === 'ocupado' ? 'opacity-40 cursor-not-allowed' : 'active:bg-gray-600'"
                  class="bg-gray-700 text-red-400 text-xs px-3 py-1.5 rounded-lg transition">
            ⏹ Cerrar turno
          </button>
        </div>
      </template>
    </div>
  </div>
</div>
```

- [ ] **Step 4: Añadir sección "Mi turno de hoy"**

Buscar el comentario `<!-- Colas globales -->` y añadir justo ANTES:

```html
<!-- Mi turno de hoy -->
<div x-show="fichajeResumen && (fichajeResumen.activo || fichajeResumen.fin)" x-cloak>
  <p class="text-xs text-gray-500 uppercase tracking-wide mb-2">Mi turno de hoy</p>
  <div class="bg-gray-800 rounded-xl p-3 space-y-2">
    <!-- Cabecera: horas y duración total -->
    <div class="flex items-center justify-between">
      <p class="text-sm font-semibold text-white"
         x-text="formatHoraISO(fichajeResumen?.inicio) + (fichajeResumen?.fin ? ' → ' + formatHoraISO(fichajeResumen.fin) : ' → ahora')"></p>
      <span class="text-xs text-gray-400"
            x-text="formatMinutos(fichajeResumen?.duracion_total_min)"></span>
    </div>
    <!-- Tramos por rol -->
    <template x-for="t in (fichajeResumen?.tramos || [])" :key="t.rol">
      <div class="flex items-center justify-between text-xs">
        <span class="text-gray-300">
          <span x-text="t.rol === 'picker' ? '📦 Picker' : '🛵 Repartidor'"></span>
        </span>
        <span class="text-gray-400" x-text="formatMinutos(t.minutos)"></span>
      </div>
    </template>
    <!-- Indicador turno activo -->
    <div x-show="fichajeResumen?.activo"
         class="text-[11px] text-green-400 font-medium">● En curso</div>
  </div>
</div>
```

- [ ] **Step 5: Verificar visualmente**

Arrancar el servidor y abrir `/empleado`:
```bash
python main.py
```
- Sin check-in: aparece botón "▶ Iniciar turno", sección turno oculta
- Al pulsar "Iniciar turno": botón cambia a "⏸ Pausa" + "⏹ Cerrar turno", hora aparece en el estado
- Sección "Mi turno de hoy" aparece con "● En curso"
- Al pulsar "⏹ Cerrar turno": confirmación, se cierra y la sección muestra el resumen sin "● En curso"

- [ ] **Step 6: Commit**

```bash
git add templates/empleado/index.html
git commit -m "feat: add check-in UI to /empleado — iniciar/cerrar turno and daily summary"
```

---

## Verificación final

- [ ] Ejecutar suite completa:

```bash
pytest -v --tb=short
```
Solo deben fallar los 3 tests pre-existentes de `TestWebhookMonei`.

- [ ] Verificar migración SQL lista para producción:

```bash
cat migrations/add_check_ins.sql
```

> **Recuerda:** ejecutar `migrations/add_check_ins.sql` en la base de datos de producción ANTES de desplegar.
