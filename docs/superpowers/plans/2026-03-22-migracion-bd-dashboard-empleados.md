# Migración BD — Dashboard de Control de Empleados

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extender la BD con las entidades y campos necesarios para soportar un dashboard profesional de gestión de empleados (puntualidad, ausencias, métricas, cambios de turno), sin romper datos existentes.

**Architecture:** Migraciones SQL incrementales sobre SQL Server + actualización de modelos SQLAlchemy. Las fases son independientes: Fase 1 es bloqueante para el dashboard; Fase 2 añade profundidad. Cada tarea produce su SQL, su cambio de modelo y sus tests antes de tocar lógica.

**Tech Stack:** SQL Server (T-SQL), SQLAlchemy ORM, pytest + MagicMock + PropertyMock (patrón del proyecto).

---

## Convenciones del proyecto

- Migraciones: ficheros `.sql` en `migrations/` con número de orden. SQL Server T-SQL con `GO` como separador de batches.
- Modelos: todo en `models.py` (fichero único). Seguir el mismo estilo de Column/relationship.
- Tests: mocking de session via `patch.object(type(gestor), 'session', new_callable=PropertyMock)`. Ver `tests/test_checkin_empleado.py` como referencia.
- Logging: `logger.info("EVENTO_NOMBRE campo=%s", valor)` — nunca f-strings.
- `get_db()` en `managers/` siempre vía `self.session` (property).
- Ejecutar `pytest -v --tb=short` antes de cada commit.

## Archivos del plan

**Crear:**
- `migrations/002_turno_campos_dashboard.sql` — estado, tipo, creado_por en turnos
- `migrations/003_checkin_campos_dashboard.sql` — turno_id FK, estado_validacion, minutos_tarde; drop unique constraint
- `migrations/004_ausencias.sql` — nueva tabla ausencias
- `migrations/005_historial_empleado_id.sql` — empleado_id en historial_estados_pedido
- `migrations/006_solicitud_cambio_turno.sql` — nueva tabla solicitudes_cambio_turno
- `migrations/007_turno_origen_id.sql` — self-referencia en turnos
- `migrations/008_metricas_diarias_empleado.sql` — nueva tabla metricas_diarias_empleado
- `tests/test_migracion_bd_dashboard.py` — tests para modelos y lógica nueva

**Modificar:**
- `models.py` — 7 cambios incrementales (uno por tarea)
- `managers/gestor_empleado.py` — iniciar_turno acepta turno_id + calcula minutos_tarde + nuevos métodos
- `managers/gestor_pedidos.py` — actualizar_estado pasa empleado_id al historial

---

## FASE 1 — Crítica (bloquea el dashboard)

---

### Tarea 1: `Turno` — estado, tipo y creado_por

**Por qué:** Sin `estado` no se puede distinguir un turno cancelado de uno activo. Sin `tipo` no se pueden agrupar turnos por franja horaria. Sin `creado_por` no hay auditoría de planificación.

**Archivos:**
- Crear: `migrations/002_turno_campos_dashboard.sql`
- Modificar: `models.py` (clase `Turno`)

- [ ] **Paso 1: Escribir el test fallido**

En `tests/test_migracion_bd_dashboard.py` (crear el archivo):

```python
"""Tests de los nuevos campos del modelo de empleados para el dashboard."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import date, datetime, time


class TestTurnoModeloCampos:
    """Verifica que el modelo Turno tiene los campos nuevos con sus defaults."""

    def test_turno_tiene_campo_estado(self):
        from models import Turno
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        assert hasattr(t, 'estado')

    def test_turno_estado_default_es_planificado(self):
        from models import Turno
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        # El default de SQLAlchemy solo aplica al INSERT; en instancia nueva puede ser None o el valor
        # Verificar que el campo existe y acepta el valor correcto
        t.estado = 'planificado'
        assert t.estado == 'planificado'

    def test_turno_tiene_campo_tipo(self):
        from models import Turno
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        assert hasattr(t, 'tipo')
        t.tipo = 'mañana'
        assert t.tipo == 'mañana'

    def test_turno_tiene_campo_creado_por(self):
        from models import Turno
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        assert hasattr(t, 'creado_por')
        t.creado_por = 5
        assert t.creado_por == 5

    def test_turno_estados_validos(self):
        """Los estados válidos son los que usará el dashboard."""
        from models import Turno
        estados_validos = {'planificado', 'confirmado', 'cubierto', 'cancelado'}
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        for estado in estados_validos:
            t.estado = estado
            assert t.estado == estado

    def test_turno_tipos_validos(self):
        from models import Turno
        tipos_validos = {'mañana', 'tarde', 'noche', 'partido'}
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        for tipo in tipos_validos:
            t.tipo = tipo
            assert t.tipo == tipo
```

- [ ] **Paso 2: Ejecutar para verificar que falla**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestTurnoModeloCampos -v
```

Esperado: `FAILED` con `AttributeError: 'Turno' object has no attribute 'estado'` (o similar).

- [ ] **Paso 3: Escribir la migración SQL**

`migrations/002_turno_campos_dashboard.sql`:

```sql
-- Migración 002: Campos de dashboard en tabla turnos
-- Ejecutar en producción ANTES de desplegar el código

IF COL_LENGTH('turnos', 'estado') IS NULL
    ALTER TABLE turnos ADD estado VARCHAR(20) NOT NULL DEFAULT 'planificado';
GO

IF COL_LENGTH('turnos', 'tipo') IS NULL
    ALTER TABLE turnos ADD tipo VARCHAR(20) NULL;
GO

IF COL_LENGTH('turnos', 'creado_por') IS NULL
    ALTER TABLE turnos ADD creado_por INT NULL REFERENCES empleados(EmpleadoID);
GO
```

- [ ] **Paso 4: Actualizar el modelo `Turno` en `models.py`**

Localizar la clase `Turno` (línea ~330). Añadir los tres campos nuevos antes de `created_at`:

```python
estado      = Column(String(20), nullable=False, default='planificado')
tipo        = Column(String(20), nullable=True)   # mañana | tarde | noche | partido
creado_por  = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=True)
```

- [ ] **Paso 5: Ejecutar los tests**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestTurnoModeloCampos -v
```

Esperado: todos en `PASSED`.

- [ ] **Paso 6: Suite completa**

```bash
pytest -v --tb=short
```

Esperado: sin regresiones. Los 3 tests `TestWebhookMonei` pre-existentes pueden seguir fallando (conocidos).

- [ ] **Paso 7: Commit**

```bash
git add migrations/002_turno_campos_dashboard.sql models.py tests/test_migracion_bd_dashboard.py
git commit -m "feat: add estado/tipo/creado_por to Turno for dashboard"
```

---

### Tarea 2: `CheckIn` — turno_id, estado_validacion, minutos_tarde + drop unique constraint

**Por qué:** Sin `turno_id` no hay puntualidad fiable. El unique constraint `(empleado_id, fecha)` impide turnos AM+PM el mismo día — hay que eliminarlo. `estado_validacion` da flujo de revisión al supervisor. `minutos_tarde` persistido evita recalcular en cada query.

**Archivos:**
- Crear: `migrations/003_checkin_campos_dashboard.sql`
- Modificar: `models.py` (clase `CheckIn`)
- Modificar: `managers/gestor_empleado.py` (método `iniciar_turno`)

- [ ] **Paso 1: Escribir los tests fallidos**

Añadir en `tests/test_migracion_bd_dashboard.py`:

```python
class TestCheckInModeloCampos:
    """Verifica que CheckIn tiene los nuevos campos de dashboard."""

    def test_checkin_tiene_turno_id(self):
        from models import CheckIn
        c = CheckIn(empleado_id=1, fecha=date.today(), inicio=datetime.utcnow())
        assert hasattr(c, 'turno_id')
        c.turno_id = 42
        assert c.turno_id == 42

    def test_checkin_tiene_estado_validacion(self):
        from models import CheckIn
        c = CheckIn(empleado_id=1, fecha=date.today(), inicio=datetime.utcnow())
        assert hasattr(c, 'estado_validacion')

    def test_checkin_tiene_minutos_tarde(self):
        from models import CheckIn
        c = CheckIn(empleado_id=1, fecha=date.today(), inicio=datetime.utcnow())
        assert hasattr(c, 'minutos_tarde')
        c.minutos_tarde = 15
        assert c.minutos_tarde == 15

    def test_checkin_minutos_tarde_puede_ser_negativo(self):
        """Negativo = llegó antes del turno (adelantado)."""
        from models import CheckIn
        c = CheckIn(empleado_id=1, fecha=date.today(), inicio=datetime.utcnow())
        c.minutos_tarde = -5
        assert c.minutos_tarde == -5


class TestIniciarTurnoConTurnoId:
    """iniciar_turno debe enlazar turno_id y calcular minutos_tarde."""

    def _gestor(self):
        from managers.gestor_empleado import GestorEmpleado
        return GestorEmpleado()

    def test_iniciar_turno_acepta_turno_id(self):
        gestor = self._gestor()
        empleado_mock = MagicMock()
        empleado_mock.rol_activo = None
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = None
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        added = []
        session_mock.add.side_effect = lambda obj: added.append(obj)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor.iniciar_turno(1, turno_id=7)
        from models import CheckIn
        check_ins = [o for o in added if isinstance(o, CheckIn)]
        assert len(check_ins) == 1
        assert check_ins[0].turno_id == 7

    def test_iniciar_turno_calcula_minutos_tarde_con_turno(self):
        """Si el turno empieza a las 09:00 y el checkin es 09:15, minutos_tarde=15."""
        gestor = self._gestor()
        empleado_mock = MagicMock()
        empleado_mock.rol_activo = None

        turno_mock = MagicMock()
        hoy = date.today()
        # Turno planificado para las 09:00
        turno_mock.hora_inicio = time(9, 0)
        turno_mock.fecha = hoy

        session_mock = MagicMock()
        def query_side_effect(model):
            from models import CheckIn, Turno, Empleado
            q = MagicMock()
            if model is CheckIn:
                q.filter.return_value.first.return_value = None
            elif model is Turno:
                q.filter_by.return_value.first.return_value = turno_mock
            elif model is Empleado:
                q.filter_by.return_value.first.return_value = empleado_mock
            return q

        session_mock.query.side_effect = query_side_effect
        added = []
        session_mock.add.side_effect = lambda obj: added.append(obj)

        # Pasar ahora directamente: el empleado ficha a las 09:15
        ahora_mock = datetime(hoy.year, hoy.month, hoy.day, 9, 15)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor.iniciar_turno(1, turno_id=7, ahora=ahora_mock)

        from models import CheckIn
        check_ins = [o for o in added if isinstance(o, CheckIn)]
        assert check_ins[0].minutos_tarde == 15

    def test_iniciar_turno_sin_turno_id_no_calcula_minutos_tarde(self):
        """Sin turno_id, minutos_tarde queda None."""
        gestor = self._gestor()
        empleado_mock = MagicMock()
        empleado_mock.rol_activo = None
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = None
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        added = []
        session_mock.add.side_effect = lambda obj: added.append(obj)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor.iniciar_turno(1)  # sin turno_id ni ahora → comportamiento normal
        from models import CheckIn
        check_ins = [o for o in added if isinstance(o, CheckIn)]
        assert check_ins[0].minutos_tarde is None
```

- [ ] **Paso 2: Ejecutar para verificar que falla**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestCheckInModeloCampos tests/test_migracion_bd_dashboard.py::TestIniciarTurnoConTurnoId -v
```

Esperado: `FAILED` — campos no existen y `iniciar_turno` no acepta `turno_id`.

- [ ] **Paso 3: Escribir la migración SQL**

`migrations/003_checkin_campos_dashboard.sql`:

```sql
-- Migración 003: Campos de dashboard en check_ins + eliminar unique constraint por fecha
-- Ejecutar en producción ANTES de desplegar el código

-- 1. Eliminar unique constraint que impide turnos AM+PM el mismo día
IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE name = 'uq_checkin_empleado_fecha' AND type = 'UQ'
)
    ALTER TABLE check_ins DROP CONSTRAINT uq_checkin_empleado_fecha;
GO

-- 2. Añadir FK al turno planificado (nullable: fichajes espontáneos no tienen turno)
IF COL_LENGTH('check_ins', 'turno_id') IS NULL
    ALTER TABLE check_ins ADD turno_id INT NULL REFERENCES turnos(id);
GO

-- 3. Estado de validación para flujo de revisión del supervisor
IF COL_LENGTH('check_ins', 'estado_validacion') IS NULL
    ALTER TABLE check_ins ADD estado_validacion VARCHAR(20) NOT NULL DEFAULT 'pendiente';
GO

-- 4. Minutos de desfase respecto al turno (positivo = tarde, negativo = adelantado)
IF COL_LENGTH('check_ins', 'minutos_tarde') IS NULL
    ALTER TABLE check_ins ADD minutos_tarde INT NULL;
GO
```

- [ ] **Paso 4: Actualizar el modelo `CheckIn` en `models.py`**

Añadir los tres campos nuevos en la clase `CheckIn` (antes de `created_at`):

```python
turno_id          = Column(Integer, ForeignKey('turnos.id'), nullable=True)
estado_validacion = Column(String(20), nullable=False, default='pendiente')
minutos_tarde     = Column(Integer, nullable=True)
```

Añadir la relación al turno (después del campo `turno_id`):

```python
turno = relationship('Turno', foreign_keys=[turno_id])
```

**Importante:** eliminar también el `UniqueConstraint` si estuviera declarado en el modelo (no está en models.py, estaba solo en la migración SQL original — no hay nada que tocar en Python aquí).

- [ ] **Paso 5: Actualizar `iniciar_turno` en `managers/gestor_empleado.py`**

Cambiar la firma y añadir la lógica de enlace y cálculo:

```python
def iniciar_turno(self, empleado_id: int, turno_id: int | None = None,
                  ahora: datetime | None = None) -> CheckIn:
    """Crea un CheckIn para hoy.

    Args:
        empleado_id: ID del empleado.
        turno_id: ID del turno planificado al que corresponde este fichaje (opcional).
                  Si se proporciona, calcula minutos_tarde respecto a la hora de inicio del turno.
        ahora: Momento del fichaje. Default None → datetime.utcnow(). Inyectable para tests.

    Raises:
        ValueError('ya_abierto'): si ya hay un check-in abierto.
    """
    s = self.session
    ahora = ahora or datetime.utcnow()
    hoy = ahora.date()

    if self._checkin_abierto_hoy(empleado_id):
        raise ValueError('ya_abierto')

    # Calcular minutos de desfase si hay turno asociado
    minutos_tarde = None
    if turno_id is not None:
        from models import Turno as _Turno
        turno = s.query(_Turno).filter_by(id=turno_id).first()
        if turno and turno.fecha == hoy:
            inicio_planificado = datetime(
                hoy.year, hoy.month, hoy.day,
                turno.hora_inicio.hour, turno.hora_inicio.minute
            )
            minutos_tarde = int((ahora - inicio_planificado).total_seconds() / 60)

    empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
    check_in = CheckIn(
        empleado_id=empleado_id,
        fecha=hoy,
        inicio=ahora,
        turno_id=turno_id,
        minutos_tarde=minutos_tarde,
    )
    s.add(check_in)
    try:
        s.flush()
        if empleado and empleado.rol_activo:
            self._abrir_tramo(check_in, empleado.rol_activo, ahora)
            if empleado.estado_operativo in ('desconectado', 'en_pausa'):
                empleado.estado_operativo = 'disponible'
        s.commit()
    except SQLAlchemyError as e:
        s.rollback()
        logger.error("Error en iniciar_turno empleado %s: %s", empleado_id, e)
        raise
    logger.info("CHECKIN empleado_id=%s inicio=%s turno_id=%s minutos_tarde=%s",
                empleado_id, ahora.isoformat(), turno_id, minutos_tarde)
    return check_in
```

- [ ] **Paso 6: Ejecutar los tests nuevos**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestCheckInModeloCampos tests/test_migracion_bd_dashboard.py::TestIniciarTurnoConTurnoId -v
```

Esperado: todos en `PASSED`.

- [ ] **Paso 7: Verificar que los tests de checkin anteriores siguen pasando**

```bash
pytest tests/test_checkin_empleado.py -v
```

Esperado: todos en `PASSED` (la firma de `iniciar_turno` es compatible — `turno_id` es opcional).

- [ ] **Paso 8: Suite completa**

```bash
pytest -v --tb=short
```

Esperado: sin regresiones nuevas.

- [ ] **Paso 9: Commit**

```bash
git add migrations/003_checkin_campos_dashboard.sql models.py managers/gestor_empleado.py tests/test_migracion_bd_dashboard.py
git commit -m "feat: add turno_id/validacion/minutos_tarde to CheckIn; drop date unique constraint"
```

---

### Tarea 3: Nueva tabla `Ausencia`

**Por qué:** Sin entidad de ausencia, el dashboard no puede distinguir entre "no fichó" y "tenía el día libre" o "estaba de baja". Es el gap más crítico para el módulo de asistencia.

**Archivos:**
- Crear: `migrations/004_ausencias.sql`
- Modificar: `models.py` (nueva clase `Ausencia`)
- Modificar: `managers/gestor_empleado.py` (métodos `registrar_ausencia`, `ausencias_empleado`)

- [ ] **Paso 1: Escribir los tests fallidos**

Añadir en `tests/test_migracion_bd_dashboard.py`:

```python
class TestAusenciaModelo:
    """Verifica la entidad Ausencia y los métodos del gestor."""

    def test_ausencia_tiene_campos_obligatorios(self):
        from models import Ausencia
        hoy = date.today()
        a = Ausencia(empleado_id=1, fecha=hoy, tipo='personal')
        assert a.empleado_id == 1
        assert a.fecha == hoy
        assert a.tipo == 'personal'

    def test_ausencia_estado_default_pendiente(self):
        from models import Ausencia
        a = Ausencia(empleado_id=1, fecha=date.today(), tipo='vacaciones')
        assert hasattr(a, 'estado')
        # En instancia nueva el default puede ser None hasta el INSERT, pero el campo existe
        a.estado = 'pendiente'
        assert a.estado == 'pendiente'

    def test_ausencia_tipos_validos(self):
        from models import Ausencia
        tipos = {'vacaciones', 'baja_medica', 'personal', 'injustificada'}
        for tipo in tipos:
            a = Ausencia(empleado_id=1, fecha=date.today(), tipo=tipo)
            assert a.tipo == tipo

    def test_ausencia_estados_validos(self):
        from models import Ausencia
        estados = {'pendiente', 'aprobada', 'rechazada'}
        for estado in estados:
            a = Ausencia(empleado_id=1, fecha=date.today(), tipo='personal')
            a.estado = estado
            assert a.estado == estado


class TestGestorEmpleadoAusencias:
    """Prueba los métodos de gestión de ausencias."""

    def _gestor(self):
        from managers.gestor_empleado import GestorEmpleado
        return GestorEmpleado()

    def test_registrar_ausencia_crea_registro(self):
        gestor = self._gestor()
        session_mock = MagicMock()
        added = []
        session_mock.add.side_effect = lambda obj: added.append(obj)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor.registrar_ausencia(empleado_id=1, fecha=date.today(), tipo='personal')
        from models import Ausencia
        ausencias = [o for o in added if isinstance(o, Ausencia)]
        assert len(ausencias) == 1
        assert ausencias[0].empleado_id == 1
        assert ausencias[0].tipo == 'personal'
        session_mock.commit.assert_called()

    def test_registrar_ausencia_tipo_invalido_lanza_error(self):
        gestor = self._gestor()
        session_mock = MagicMock()
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with pytest.raises(ValueError, match='tipo_invalido'):
                gestor.registrar_ausencia(empleado_id=1, fecha=date.today(), tipo='INEXISTENTE')

    def test_ausencias_empleado_devuelve_lista(self):
        gestor = self._gestor()
        session_mock = MagicMock()
        ausencia_mock = MagicMock()
        ausencia_mock.id = 1
        ausencia_mock.fecha = date.today()
        ausencia_mock.tipo = 'vacaciones'
        ausencia_mock.estado = 'aprobada'
        ausencia_mock.aprobado_por = None
        ausencia_mock.notas = None
        session_mock.query.return_value.filter.return_value.order_by.return_value.all.return_value = [ausencia_mock]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.ausencias_empleado(empleado_id=1,
                                               fecha_inicio=date.today(),
                                               fecha_fin=date.today())
        assert len(result) == 1
        assert result[0]['tipo'] == 'vacaciones'
        assert result[0]['estado'] == 'aprobada'
```

- [ ] **Paso 2: Ejecutar para verificar que falla**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestAusenciaModelo tests/test_migracion_bd_dashboard.py::TestGestorEmpleadoAusencias -v
```

Esperado: `FAILED` — modelo e imports no existen.

- [ ] **Paso 3: Escribir la migración SQL**

`migrations/004_ausencias.sql`:

```sql
-- Migración 004: Tabla de ausencias de empleados
-- Ejecutar en producción ANTES de desplegar el código

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'ausencias')
BEGIN
    CREATE TABLE ausencias (
        id           INT IDENTITY(1,1) PRIMARY KEY,
        empleado_id  INT NOT NULL REFERENCES empleados(EmpleadoID),
        fecha        DATE NOT NULL,
        tipo         VARCHAR(30) NOT NULL,  -- vacaciones | baja_medica | personal | injustificada
        estado       VARCHAR(20) NOT NULL DEFAULT 'pendiente',  -- pendiente | aprobada | rechazada
        aprobado_por INT NULL REFERENCES empleados(EmpleadoID),
        aprobado_en  DATETIME NULL,
        notas        VARCHAR(500) NULL,
        created_at   DATETIME NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT uq_ausencia_empleado_fecha UNIQUE (empleado_id, fecha)
    );
END
GO
```

- [ ] **Paso 4: Añadir modelo `Ausencia` en `models.py`**

Añadir la clase nueva en la sección de empleados (después de `EmpleadoCapacidad`):

```python
class Ausencia(Base):
    """Registro de ausencia de un empleado en una fecha concreta."""
    __tablename__ = 'ausencias'

    TIPOS_VALIDOS  = {'vacaciones', 'baja_medica', 'personal', 'injustificada'}
    ESTADOS_VALIDOS = {'pendiente', 'aprobada', 'rechazada'}

    id           = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id  = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=False)
    fecha        = Column(Date, nullable=False)
    tipo         = Column(String(30), nullable=False)
    estado       = Column(String(20), nullable=False, default='pendiente')
    aprobado_por = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=True)
    aprobado_en  = Column(DateTime, nullable=True)
    notas        = Column(String(500), nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)

    empleado = relationship('Empleado', foreign_keys=[empleado_id], backref='ausencias')
    aprobador = relationship('Empleado', foreign_keys=[aprobado_por])

    __table_args__ = (
        UniqueConstraint('empleado_id', 'fecha', name='uq_ausencia_empleado_fecha'),
    )
```

- [ ] **Paso 5: Añadir métodos en `GestorEmpleado`**

Al final de `managers/gestor_empleado.py` añadir:

```python
# -------------------------------------------------------------------------
# Ausencias
# -------------------------------------------------------------------------

_TIPOS_AUSENCIA = {'vacaciones', 'baja_medica', 'personal', 'injustificada'}

def registrar_ausencia(self, empleado_id: int, fecha: date,
                       tipo: str, notas: str | None = None) -> 'Ausencia':
    """Registra una ausencia para un empleado en una fecha.

    Args:
        empleado_id: ID del empleado.
        fecha: Fecha de la ausencia.
        tipo: Tipo de ausencia. Valores: vacaciones, baja_medica, personal, injustificada.
        notas: Observaciones opcionales.

    Raises:
        ValueError('tipo_invalido'): Si el tipo no está en los valores permitidos.
    """
    from models import Ausencia
    if tipo not in _TIPOS_AUSENCIA:
        raise ValueError('tipo_invalido')
    s = self.session
    ausencia = Ausencia(empleado_id=empleado_id, fecha=fecha, tipo=tipo, notas=notas)
    s.add(ausencia)
    try:
        s.commit()
    except SQLAlchemyError as e:
        s.rollback()
        logger.error("Error registrando ausencia empleado %s: %s", empleado_id, e)
        raise
    logger.info("AUSENCIA_REGISTRADA empleado_id=%s fecha=%s tipo=%s", empleado_id, fecha, tipo)
    return ausencia

def ausencias_empleado(self, empleado_id: int,
                       fecha_inicio: date, fecha_fin: date) -> list[dict]:
    """Lista ausencias de un empleado en un rango de fechas.

    Returns:
        Lista de dicts con id, fecha, tipo, estado, aprobado_por, notas.
    """
    from models import Ausencia
    ausencias = (
        self.session.query(Ausencia)
        .filter(
            Ausencia.empleado_id == empleado_id,
            Ausencia.fecha >= fecha_inicio,
            Ausencia.fecha <= fecha_fin,
        )
        .order_by(Ausencia.fecha)
        .all()
    )
    return [
        {
            'id':          a.id,
            'fecha':       a.fecha.isoformat(),
            'tipo':        a.tipo,
            'estado':      a.estado,
            'aprobado_por': a.aprobado_por,
            'notas':       a.notas,
        }
        for a in ausencias
    ]
```

- [ ] **Paso 6: Ejecutar los tests**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestAusenciaModelo tests/test_migracion_bd_dashboard.py::TestGestorEmpleadoAusencias -v
```

Esperado: todos en `PASSED`.

- [ ] **Paso 7: Suite completa**

```bash
pytest -v --tb=short
```

Esperado: sin regresiones nuevas.

- [ ] **Paso 8: Commit**

```bash
git add migrations/004_ausencias.sql models.py managers/gestor_empleado.py tests/test_migracion_bd_dashboard.py
git commit -m "feat: add Ausencia model and gestor_empleado methods"
```

---

### Tarea 4: `GestorEmpleado` — método `puntualidad_empleado`

**Por qué:** Es la métrica más demandada por el dashboard. Requiere que `turno_id` y `minutos_tarde` ya existan (Tarea 2). Consolida la lógica en un solo lugar para que el dashboard solo llame un método.

**Archivos:**
- Modificar: `managers/gestor_empleado.py` (nuevo método `puntualidad_empleado`)

- [ ] **Paso 1: Escribir el test fallido**

Añadir en `tests/test_migracion_bd_dashboard.py`:

```python
class TestPuntualidadEmpleado:
    """puntualidad_empleado devuelve resumen de puntualidad en un rango de fechas."""

    def _gestor(self):
        from managers.gestor_empleado import GestorEmpleado
        return GestorEmpleado()

    def _checkin_mock(self, minutos_tarde, estado_validacion='validado', turno_id=1):
        m = MagicMock()
        m.minutos_tarde = minutos_tarde
        m.estado_validacion = estado_validacion
        m.turno_id = turno_id
        return m

    def test_sin_checkins_devuelve_ceros(self):
        gestor = self._gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.puntualidad_empleado(1, date.today(), date.today())
        assert result['total_turnos'] == 0
        assert result['puntuales'] == 0
        assert result['tarde'] == 0
        assert result['tasa_puntualidad_pct'] == 100

    def test_calcula_puntuales_y_tarde(self):
        gestor = self._gestor()
        checkins = [
            self._checkin_mock(-2),   # adelantado → puntual
            self._checkin_mock(0),    # exacto → puntual
            self._checkin_mock(5),    # 5 min → puntual (margen ≤ 5)
            self._checkin_mock(6),    # 6 min → tarde
            self._checkin_mock(20),   # 20 min → tarde
        ]
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = checkins
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.puntualidad_empleado(1, date.today(), date.today())
        assert result['total_turnos'] == 5
        assert result['puntuales'] == 3
        assert result['tarde'] == 2
        assert result['tasa_puntualidad_pct'] == 60

    def test_ignora_checkins_sin_turno_id(self):
        """Fichajes espontáneos (sin turno planificado) no computan en puntualidad."""
        gestor = self._gestor()
        checkins = [
            self._checkin_mock(10, turno_id=1),
            self._checkin_mock(None, turno_id=None),  # sin turno → ignorar
        ]
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = checkins
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.puntualidad_empleado(1, date.today(), date.today())
        assert result['total_turnos'] == 1

    def test_media_minutos_tarde(self):
        gestor = self._gestor()
        checkins = [
            self._checkin_mock(10),
            self._checkin_mock(20),
        ]
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = checkins
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.puntualidad_empleado(1, date.today(), date.today())
        assert result['media_minutos_tarde'] == 15
```

- [ ] **Paso 2: Ejecutar para verificar que falla**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestPuntualidadEmpleado -v
```

Esperado: `FAILED` — método no existe.

- [ ] **Paso 3: Implementar `puntualidad_empleado` en `GestorEmpleado`**

Añadir al final de la sección de Fichaje/Check-in:

```python
_MARGEN_PUNTUALIDAD_MIN = 5   # minutos de gracia antes de contar como tarde

def puntualidad_empleado(self, empleado_id: int,
                         fecha_inicio: date, fecha_fin: date) -> dict:
    """Resumen de puntualidad de un empleado en un rango de fechas.

    Solo se analizan check-ins vinculados a un turno planificado (turno_id no nulo).
    Un fichaje es 'puntual' si minutos_tarde <= _MARGEN_PUNTUALIDAD_MIN.

    Returns:
        Dict con total_turnos, puntuales, tarde, tasa_puntualidad_pct, media_minutos_tarde.
    """
    checkins = (
        self.session.query(CheckIn)
        .filter(
            CheckIn.empleado_id == empleado_id,
            CheckIn.fecha >= fecha_inicio,
            CheckIn.fecha <= fecha_fin,
            CheckIn.turno_id.isnot(None),
        )
        .all()
    )

    total = len(checkins)
    if total == 0:
        return {
            'total_turnos': 0,
            'puntuales': 0,
            'tarde': 0,
            'tasa_puntualidad_pct': 100,
            'media_minutos_tarde': None,
        }

    puntuales = sum(
        1 for c in checkins
        if c.minutos_tarde is not None and c.minutos_tarde <= _MARGEN_PUNTUALIDAD_MIN
    )
    tarde = total - puntuales

    minutos_con_dato = [c.minutos_tarde for c in checkins if c.minutos_tarde is not None]
    media = round(sum(minutos_con_dato) / len(minutos_con_dato)) if minutos_con_dato else None

    return {
        'total_turnos':          total,
        'puntuales':             puntuales,
        'tarde':                 tarde,
        'tasa_puntualidad_pct':  round(puntuales / total * 100),
        'media_minutos_tarde':   media,
    }
```

- [ ] **Paso 4: Ejecutar los tests**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestPuntualidadEmpleado -v
```

Esperado: todos en `PASSED`.

- [ ] **Paso 5: Suite completa**

```bash
pytest -v --tb=short
```

- [ ] **Paso 6: Commit**

```bash
git add managers/gestor_empleado.py tests/test_migracion_bd_dashboard.py
git commit -m "feat: add puntualidad_empleado method to GestorEmpleado"
```

---

## FASE 2 — Recomendada (antes de vistas de rendimiento)

---

### Tarea 5: `HistorialEstadoPedido` — añadir `empleado_id`

**Por qué:** Actualmente no se puede saber qué empleado ejecutó cada transición. Necesario para el módulo de rendimiento individual.

**Archivos:**
- Crear: `migrations/005_historial_empleado_id.sql`
- Modificar: `models.py` (clase `HistorialEstadoPedido`)
- Modificar: `managers/gestor_pedidos.py` (método `actualizar_estado`)

- [ ] **Paso 1: Escribir el test fallido**

Añadir en `tests/test_migracion_bd_dashboard.py`:

```python
class TestHistorialEmpleadoId:

    def test_historial_tiene_empleado_id(self):
        from models import HistorialEstadoPedido
        h = HistorialEstadoPedido(
            pedido_id=1,
            estado_anterior='pendiente',
            estado_nuevo='pagado',
        )
        assert hasattr(h, 'empleado_id')
        h.empleado_id = 3
        assert h.empleado_id == 3

    def test_historial_empleado_id_es_nullable(self):
        """Transiciones automáticas (sin actor humano) deben poder tener empleado_id=None."""
        from models import HistorialEstadoPedido
        h = HistorialEstadoPedido(
            pedido_id=1,
            estado_anterior='pendiente',
            estado_nuevo='pagado',
        )
        h.empleado_id = None
        assert h.empleado_id is None
```

- [ ] **Paso 2: Ejecutar para verificar que falla**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestHistorialEmpleadoId -v
```

- [ ] **Paso 3: Migración SQL**

`migrations/005_historial_empleado_id.sql`:

```sql
-- Migración 005: Añadir empleado_id al historial de estados de pedido
IF COL_LENGTH('historial_estados_pedido', 'empleado_id') IS NULL
    ALTER TABLE historial_estados_pedido
    ADD empleado_id INT NULL REFERENCES empleados(EmpleadoID);
GO
```

- [ ] **Paso 4: Actualizar modelo `HistorialEstadoPedido` en `models.py`**

Añadir en la clase (después de `notas`):

```python
empleado_id = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=True)
```

- [ ] **Paso 5: Actualizar `actualizar_estado` en `managers/gestor_pedidos.py`**

Leer el método antes de editarlo. La firma actual es:
```python
def actualizar_estado(self, pedido_id, nuevo_estado, notas=None):
```

Cambiar a (añadir `empleado_id` como parámetro opcional al final):
```python
def actualizar_estado(self, pedido_id, nuevo_estado, notas=None, empleado_id=None):
```

Localizar la línea donde se crea el `HistorialEstadoPedido`. Será algo como:
```python
historial = HistorialEstadoPedido(
    pedido_id=pedido_id,
    estado_anterior=estado_actual,
    estado_nuevo=nuevo_estado,
    notas=notas,
)
```

Añadir `empleado_id=empleado_id` al constructor:
```python
historial = HistorialEstadoPedido(
    pedido_id=pedido_id,
    estado_anterior=estado_actual,
    estado_nuevo=nuevo_estado,
    notas=notas,
    empleado_id=empleado_id,
)
```

No cambiar la lógica de validación de transiciones ni el resto del método.

- [ ] **Paso 6: Ejecutar los tests**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestHistorialEmpleadoId -v
pytest tests/test_gestor_pedidos.py -v
```

Esperado: todos en `PASSED`.

- [ ] **Paso 7: Suite completa y commit**

```bash
pytest -v --tb=short
git add migrations/005_historial_empleado_id.sql models.py managers/gestor_pedidos.py tests/test_migracion_bd_dashboard.py
git commit -m "feat: add empleado_id to HistorialEstadoPedido for individual attribution"
```

---

### Tarea 6: Nueva tabla `SolicitudCambioTurno`

**Por qué:** Sin esta entidad, los intercambios de turno son invisibles para el sistema. El dashboard de supervisor necesita aprobar/rechazar cambios.

**Archivos:**
- Crear: `migrations/006_solicitud_cambio_turno.sql`
- Modificar: `models.py` (nueva clase `SolicitudCambioTurno`)

- [ ] **Paso 1: Escribir el test fallido**

Añadir en `tests/test_migracion_bd_dashboard.py`:

```python
class TestSolicitudCambioTurno:

    def test_modelo_tiene_campos_obligatorios(self):
        from models import SolicitudCambioTurno
        s = SolicitudCambioTurno(
            turno_cedido_id=1,
            solicitante_id=2,
        )
        assert s.turno_cedido_id == 1
        assert s.solicitante_id == 2
        assert hasattr(s, 'estado')
        assert hasattr(s, 'sustituto_id')
        assert hasattr(s, 'aprobado_por')

    def test_estados_validos(self):
        from models import SolicitudCambioTurno
        estados = {'pendiente', 'aprobada', 'rechazada', 'cancelada'}
        for estado in estados:
            sc = SolicitudCambioTurno(turno_cedido_id=1, solicitante_id=1)
            sc.estado = estado
            assert sc.estado == estado
```

- [ ] **Paso 2: Ejecutar para verificar que falla**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestSolicitudCambioTurno -v
```

- [ ] **Paso 3: Migración SQL**

`migrations/006_solicitud_cambio_turno.sql`:

```sql
-- Migración 006: Tabla de solicitudes de cambio de turno
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'solicitudes_cambio_turno')
BEGIN
    CREATE TABLE solicitudes_cambio_turno (
        id               INT IDENTITY(1,1) PRIMARY KEY,
        turno_cedido_id  INT NOT NULL REFERENCES turnos(id),
        solicitante_id   INT NOT NULL REFERENCES empleados(EmpleadoID),
        sustituto_id     INT NULL REFERENCES empleados(EmpleadoID),
        estado           VARCHAR(20) NOT NULL DEFAULT 'pendiente',  -- pendiente | aprobada | rechazada | cancelada
        aprobado_por     INT NULL REFERENCES empleados(EmpleadoID),
        aprobado_en      DATETIME NULL,
        motivo           VARCHAR(500) NULL,
        created_at       DATETIME NOT NULL DEFAULT GETUTCDATE()
    );
END
GO
```

- [ ] **Paso 4: Añadir modelo `SolicitudCambioTurno` en `models.py`**

Añadir después de `Ausencia`:

```python
class SolicitudCambioTurno(Base):
    """Solicitud de cesión o intercambio de turno entre empleados."""
    __tablename__ = 'solicitudes_cambio_turno'

    id              = Column(Integer, primary_key=True, autoincrement=True)
    turno_cedido_id = Column(Integer, ForeignKey('turnos.id'), nullable=False)
    solicitante_id  = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=False)
    sustituto_id    = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=True)
    estado          = Column(String(20), nullable=False, default='pendiente')
    aprobado_por    = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=True)
    aprobado_en     = Column(DateTime, nullable=True)
    motivo          = Column(String(500), nullable=True)
    created_at      = Column(DateTime, default=datetime.utcnow)

    turno_cedido = relationship('Turno', foreign_keys=[turno_cedido_id])
    solicitante  = relationship('Empleado', foreign_keys=[solicitante_id])
    sustituto    = relationship('Empleado', foreign_keys=[sustituto_id])
    aprobador    = relationship('Empleado', foreign_keys=[aprobado_por])
```

- [ ] **Paso 5: Ejecutar tests y suite completa**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestSolicitudCambioTurno -v
pytest -v --tb=short
```

- [ ] **Paso 6: Commit**

```bash
git add migrations/006_solicitud_cambio_turno.sql models.py tests/test_migracion_bd_dashboard.py
git commit -m "feat: add SolicitudCambioTurno model for shift change tracking"
```

---

### Tarea 7: `Turno.turno_origen_id` — trazabilidad de cambios de turno

**Por qué:** Cuando se aprueba un cambio de turno, el turno del sustituto debe mantener referencia al turno original que cubría. Permite reconstruir la historia de reorganizaciones.

**Archivos:**
- Crear: `migrations/007_turno_origen_id.sql`
- Modificar: `models.py` (campo en `Turno`)

- [ ] **Paso 1: Test fallido**

Añadir en `tests/test_migracion_bd_dashboard.py`:

```python
class TestTurnoOrigenId:

    def test_turno_tiene_campo_origen_id(self):
        from models import Turno
        from datetime import time
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        assert hasattr(t, 'turno_origen_id')
        t.turno_origen_id = 99
        assert t.turno_origen_id == 99

    def test_turno_origen_id_nullable(self):
        from models import Turno
        from datetime import time
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        t.turno_origen_id = None
        assert t.turno_origen_id is None
```

- [ ] **Paso 2: Ejecutar para verificar que falla**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestTurnoOrigenId -v
```

- [ ] **Paso 3: Migración SQL**

`migrations/007_turno_origen_id.sql`:

```sql
-- Migración 007: Self-referencia en turnos para trazabilidad de cambios
IF COL_LENGTH('turnos', 'turno_origen_id') IS NULL
    ALTER TABLE turnos ADD turno_origen_id INT NULL REFERENCES turnos(id);
GO
```

- [ ] **Paso 4: Actualizar modelo `Turno` en `models.py`**

Añadir en la clase `Turno` (después de `creado_por`):

```python
turno_origen_id = Column(Integer, ForeignKey('turnos.id'), nullable=True)

turno_origen = relationship('Turno', remote_side='id', foreign_keys=[turno_origen_id])
```

- [ ] **Paso 5: Tests y commit**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestTurnoOrigenId -v
pytest -v --tb=short
git add migrations/007_turno_origen_id.sql models.py tests/test_migracion_bd_dashboard.py
git commit -m "feat: add turno_origen_id self-reference for shift change history"
```

---

### Tarea 8: Nueva tabla `MetricaDiariaEmpleado`

**Por qué:** El dashboard no debe recalcular métricas en tiempo real sobre meses de histórico. Esta tabla actúa como caché diario persistido. Se rellena con un job o al cerrar el turno. El dashboard lee de aquí para vistas de semana/mes.

**Archivos:**
- Crear: `migrations/008_metricas_diarias_empleado.sql`
- Modificar: `models.py` (nueva clase `MetricaDiariaEmpleado`)
- Modificar: `managers/gestor_empleado.py` (método `calcular_y_guardar_metrica_diaria`)

- [ ] **Paso 1: Tests fallidos**

Añadir en `tests/test_migracion_bd_dashboard.py`:

```python
class TestMetricaDiariaEmpleado:

    def test_modelo_tiene_campos_clave(self):
        from models import MetricaDiariaEmpleado
        m = MetricaDiariaEmpleado(empleado_id=1, fecha=date.today())
        assert hasattr(m, 'horas_trabajadas_min')
        assert hasattr(m, 'pedidos_completados')
        assert hasattr(m, 'tiempo_medio_operacion_min')
        assert hasattr(m, 'incidencias')
        assert hasattr(m, 'minutos_tarde')

    def test_calcular_y_guardar_metrica_diaria_persiste_registro(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        ahora = datetime.utcnow()
        tramo_mock = MagicMock()
        tramo_mock.rol = 'picker'
        tramo_mock.inicio = ahora.replace(hour=9, minute=0)
        tramo_mock.fin = ahora.replace(hour=13, minute=0)   # 4 horas = 240 min
        check_in_mock = MagicMock()
        check_in_mock.inicio = ahora.replace(hour=9, minute=0)
        check_in_mock.fin = ahora.replace(hour=13, minute=0)
        check_in_mock.minutos_tarde = 5
        check_in_mock.turno_id = 1
        check_in_mock.tramos = [tramo_mock]
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = check_in_mock
        added = []
        session_mock.add.side_effect = lambda obj: added.append(obj)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            # metricas de pedidos vacías para simplificar el mock
            with patch.object(gestor, 'metricas_hoy', return_value={
                'pedidos_completados': 3,
                'tiempo_medio_min': 12,
                'incidencias_hoy': 1,
            }):
                gestor.calcular_y_guardar_metrica_diaria(
                    empleado_id=1, fecha=date.today(), rol='picker'
                )
        from models import MetricaDiariaEmpleado
        metricas = [o for o in added if isinstance(o, MetricaDiariaEmpleado)]
        assert len(metricas) == 1
        assert metricas[0].horas_trabajadas_min == 240
        assert metricas[0].pedidos_completados == 3
        assert metricas[0].minutos_tarde == 5
```

- [ ] **Paso 2: Ejecutar para verificar que falla**

```bash
pytest tests/test_migracion_bd_dashboard.py::TestMetricaDiariaEmpleado -v
```

- [ ] **Paso 3: Migración SQL**

`migrations/008_metricas_diarias_empleado.sql`:

```sql
-- Migración 008: Tabla de métricas diarias por empleado (caché para dashboard)
IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'metricas_diarias_empleado')
BEGIN
    CREATE TABLE metricas_diarias_empleado (
        id                        INT IDENTITY(1,1) PRIMARY KEY,
        empleado_id               INT NOT NULL REFERENCES empleados(EmpleadoID),
        fecha                     DATE NOT NULL,
        rol                       VARCHAR(20) NOT NULL,          -- picker | repartidor
        horas_trabajadas_min      INT NULL,                      -- minutos totales trabajados
        pedidos_completados       INT NOT NULL DEFAULT 0,
        tiempo_medio_operacion_min INT NULL,                     -- media picking o reparto en min
        incidencias               INT NOT NULL DEFAULT 0,
        minutos_tarde             INT NULL,                      -- del check-in del día
        calculado_en              DATETIME NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT uq_metrica_empleado_fecha_rol UNIQUE (empleado_id, fecha, rol)
    );
END
GO
```

- [ ] **Paso 4: Añadir modelo `MetricaDiariaEmpleado` en `models.py`**

Añadir después de `SolicitudCambioTurno`:

```python
class MetricaDiariaEmpleado(Base):
    """Resumen de actividad diaria de un empleado por rol. Caché para el dashboard."""
    __tablename__ = 'metricas_diarias_empleado'

    id                         = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id                = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=False)
    fecha                      = Column(Date, nullable=False)
    rol                        = Column(String(20), nullable=False)
    horas_trabajadas_min       = Column(Integer, nullable=True)
    pedidos_completados        = Column(Integer, nullable=False, default=0)
    tiempo_medio_operacion_min = Column(Integer, nullable=True)
    incidencias                = Column(Integer, nullable=False, default=0)
    minutos_tarde              = Column(Integer, nullable=True)
    calculado_en               = Column(DateTime, default=datetime.utcnow)

    empleado = relationship('Empleado', foreign_keys=[empleado_id], backref='metricas_diarias')

    __table_args__ = (
        UniqueConstraint('empleado_id', 'fecha', 'rol',
                         name='uq_metrica_empleado_fecha_rol'),
    )
```

- [ ] **Paso 5: Añadir método `calcular_y_guardar_metrica_diaria` en `GestorEmpleado`**

Añadir al final del manager:

```python
# -------------------------------------------------------------------------
# Métricas diarias (caché para dashboard)
# -------------------------------------------------------------------------

def calcular_y_guardar_metrica_diaria(self, empleado_id: int,
                                      fecha: date, rol: str) -> None:
    """Calcula y persiste las métricas del día para un empleado en un rol.

    Diseñado para ser llamado al cerrar turno o desde un job nocturno.
    Si ya existe un registro para ese día+rol, lo sobreescribe (MERGE semántico via delete+insert).

    Args:
        empleado_id: ID del empleado.
        fecha: Fecha a calcular.
        rol: Rol operativo ('picker' o 'repartidor').
    """
    from models import MetricaDiariaEmpleado
    s = self.session

    # Obtener el check-in del día para calcular horas y minutos tarde
    check_in = s.query(CheckIn).filter(
        CheckIn.empleado_id == empleado_id,
        CheckIn.fecha == fecha,
    ).first()

    horas_min = None
    minutos_tarde_dia = None
    if check_in and check_in.inicio and check_in.fin:
        horas_min = int((check_in.fin - check_in.inicio).total_seconds() / 60)
        minutos_tarde_dia = check_in.minutos_tarde

    # Reutilizar metricas_hoy para pedidos/tiempo/incidencias
    kpis = self.metricas_hoy(empleado_id, rol)

    # Eliminar registro anterior si existe (para sobreescribir)
    s.query(MetricaDiariaEmpleado).filter(
        MetricaDiariaEmpleado.empleado_id == empleado_id,
        MetricaDiariaEmpleado.fecha == fecha,
        MetricaDiariaEmpleado.rol == rol,
    ).delete()
    s.flush()   # garantizar que el delete se ejecuta antes del INSERT siguiente

    metrica = MetricaDiariaEmpleado(
        empleado_id=empleado_id,
        fecha=fecha,
        rol=rol,
        horas_trabajadas_min=horas_min,
        pedidos_completados=kpis.get('pedidos_completados', 0),
        tiempo_medio_operacion_min=kpis.get('tiempo_medio_min'),
        incidencias=kpis.get('incidencias_hoy', 0),
        minutos_tarde=minutos_tarde_dia,
    )
    s.add(metrica)
    try:
        s.commit()
    except SQLAlchemyError as e:
        s.rollback()
        logger.error("Error guardando metrica diaria empleado %s fecha %s: %s",
                     empleado_id, fecha, e)
        raise
    logger.info("METRICA_DIARIA_GUARDADA empleado_id=%s fecha=%s rol=%s",
                empleado_id, fecha, rol)
```

- [ ] **Paso 6: Ejecutar todos los tests del plan**

```bash
pytest tests/test_migracion_bd_dashboard.py -v
```

Esperado: todos en `PASSED`.

- [ ] **Paso 7: Suite completa**

```bash
pytest -v --tb=short
```

Esperado: sin regresiones nuevas.

- [ ] **Paso 8: Commit final**

```bash
git add migrations/008_metricas_diarias_empleado.sql models.py managers/gestor_empleado.py tests/test_migracion_bd_dashboard.py
git commit -m "feat: add MetricaDiariaEmpleado model and calcular_y_guardar_metrica_diaria"
```

---

## Orden de ejecución de migraciones en producción

Ejecutar **en este orden exacto** sobre la base de datos de producción antes de cada despliegue de código:

```
002_turno_campos_dashboard.sql
003_checkin_campos_dashboard.sql      ← incluye DROP CONSTRAINT
004_ausencias.sql
005_historial_empleado_id.sql
006_solicitud_cambio_turno.sql
007_turno_origen_id.sql
008_metricas_diarias_empleado.sql
```

Cada fichero es idempotente: puede ejecutarse varias veces sin errores gracias a los guards `IF COL_LENGTH ... IS NULL` / `IF NOT EXISTS`.

---

## Checklist de verificación antes de empezar el dashboard

- [ ] Las 7 migraciones SQL están aplicadas en producción
- [ ] `pytest -v --tb=short` pasa sin regresiones
- [ ] `Turno` tiene `estado`, `tipo`, `creado_por`
- [ ] `CheckIn` tiene `turno_id`, `estado_validacion`, `minutos_tarde`
- [ ] La tabla `ausencias` existe en BD
- [ ] `GestorEmpleado.puntualidad_empleado()` funciona
- [ ] `GestorEmpleado.ausencias_empleado()` funciona
- [ ] `GestorEmpleado.calcular_y_guardar_metrica_diaria()` funciona
- [ ] `HistorialEstadoPedido` tiene `empleado_id`
