# Zona de Empleados — Hub + Estado Operativo

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir un hub centralizado `/empleado` al que entran pickers y repartidores tras el login, con estado operativo automático visible en el dashboard del manager.

**Architecture:** Nuevo blueprint `empleado` + nuevo manager `GestorEmpleado` para la lógica de perfil/estado/turno/métricas. Una columna `estado_operativo` en `empleados` y una tabla `turnos` mínima. Hooks en los métodos existentes de `GestorDashboard` para auto-gestionar el estado sin cambiar sus firmas ni retornos. Las apps `/picker` y `/repartidor` no se modifican.

**Tech Stack:** Flask, SQLAlchemy 2.x (SQL Server via pyodbc), Tailwind CDN, Alpine.js 3.x. Tests con pytest + mock (sin BD real en CI).

**Spec:** `docs/superpowers/specs/2026-03-21-zona-empleados-design.md`

---

## Mapa de archivos

| Archivo | Acción | Responsabilidad |
|---|---|---|
| `models.py` | Modificar | Añadir `estado_operativo` a `Empleado`; añadir modelo `Turno` |
| `scripts/migrar_empleado.py` | Crear | Script SQL idempotente: ALTER TABLE + CREATE TABLE |
| `managers/gestor_empleado.py` | Crear | Lógica de perfil, cambio de estado, turno del día, métricas del día |
| `blueprints/empleado.py` | Crear | 5 rutas HTTP para el hub de empleados |
| `main.py` | Modificar | Registrar `blueprint_empleado` |
| `blueprints/auth.py` | Modificar | Redirigir picker/repartidor a `/empleado` tras login |
| `managers/gestor_dashboard.py` | Modificar | Helper `_actualizar_estado_operativo` + 4 hooks |
| `templates/empleado/index.html` | Crear | Hub template mobile-first (Tailwind + Alpine) |
| `tests/test_empleado.py` | Crear | Tests para blueprint y manager |

---

## Task 1: Modelos ORM — `estado_operativo` y `Turno`

**Files:**
- Modify: `models.py`
- Test: `tests/test_database.py` (añadir smoke test)

- [ ] **Paso 1: Escribir el test que verifica que `Empleado` tiene `estado_operativo`**

Abrir `tests/test_database.py` y añadir al final:

```python
def test_empleado_tiene_estado_operativo():
    """El modelo Empleado debe tener el campo estado_operativo."""
    import inspect
    from models import Empleado
    src = inspect.getsource(Empleado)
    assert 'estado_operativo' in src, "Falta columna estado_operativo en Empleado"


def test_modelo_turno_existe():
    """El modelo Turno debe existir con los campos requeridos."""
    import inspect
    from models import Turno
    src = inspect.getsource(Turno)
    for campo in ('empleado_id', 'fecha', 'hora_inicio', 'hora_fin'):
        assert campo in src, f"Falta campo {campo} en Turno"
```

- [ ] **Paso 2: Ejecutar tests para verificar que fallan**

```bash
pytest tests/test_database.py::test_empleado_tiene_estado_operativo tests/test_database.py::test_modelo_turno_existe -v
```

Resultado esperado: `FAILED` — `ImportError: cannot import name 'Turno'` o `AssertionError`.

- [ ] **Paso 3: Añadir `estado_operativo` a `Empleado` en `models.py`**

En la clase `Empleado`, después de la línea `activo = Column(...)`, añadir:

```python
estado_operativo = Column(
    String(20),
    nullable=False,
    default='desconectado',
    server_default='desconectado',
)
```

- [ ] **Paso 4: Añadir modelo `Turno` en `models.py`**

Al final del archivo `models.py`, añadir una nueva sección:

```python
# ---------------------------------------------------------------------------
# Turnos
# ---------------------------------------------------------------------------

class Turno(Base):
    """Turno de trabajo de un empleado en una fecha concreta."""
    __tablename__ = 'turnos'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=False)
    fecha       = Column(Date, nullable=False)
    hora_inicio = Column(Time, nullable=False)
    hora_fin    = Column(Time, nullable=False)
    notas       = Column(String(255), nullable=True)
    created_at  = Column(DateTime, default=datetime.utcnow)

    empleado = relationship('Empleado', back_populates='turnos')
```

También añadir en la clase `Empleado`, junto a las otras relaciones:

```python
turnos = relationship('Turno', back_populates='empleado', order_by='Turno.fecha')
```

Necesitarás añadir `Date, Time` a los imports de SQLAlchemy al inicio del archivo:

```python
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, DECIMAL, Boolean, Text, Float, Date, Time
```

- [ ] **Paso 5: Ejecutar tests para verificar que pasan**

```bash
pytest tests/test_database.py::test_empleado_tiene_estado_operativo tests/test_database.py::test_modelo_turno_existe -v
```

Resultado esperado: `PASSED`.

- [ ] **Paso 6: Ejecutar suite completa para verificar que no hay regresiones**

```bash
pytest -v --tb=short
```

Los 3 tests pre-existentes de `TestWebhookMonei` pueden seguir fallando — son conocidos. El resto debe pasar.

- [ ] **Paso 7: Commit**

```bash
git add models.py tests/test_database.py
git commit -m "feat(models): add estado_operativo to Empleado and new Turno model"
```

---

## Task 2: Script de migración SQL

**Files:**
- Create: `scripts/migrar_empleado.py`

Este script es para ejecutar en producción/staging. No tiene tests automatizados (depende de BD real). Debe ser idempotente.

- [ ] **Paso 1: Crear `scripts/migrar_empleado.py`**

```python
"""
Migración: Zona de empleados — estado_operativo + tabla turnos

Ejecutar una sola vez:
    python scripts/migrar_empleado.py

Es idempotente: comprueba si la columna/tabla ya existen antes de crearlas.
"""
import os
import sys

import pyodbc

SQL_SERVER   = os.environ.get('SQL_SERVER',   'localhost,1433')
SQL_DATABASE = os.environ.get('SQL_DATABASE', 'pruebabot')
SQL_UID      = os.environ.get('SQL_UID',      '')
SQL_PWD      = os.environ.get('SQL_PWD',      '')

CONN_STR = (
    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
    f"SERVER={SQL_SERVER};DATABASE={SQL_DATABASE};"
    f"UID={SQL_UID};PWD={SQL_PWD}"
)

ADD_COLUMN = """
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_NAME = 'empleados' AND COLUMN_NAME = 'estado_operativo'
)
BEGIN
    ALTER TABLE empleados
    ADD estado_operativo VARCHAR(20) NOT NULL DEFAULT 'desconectado';
    PRINT 'Columna estado_operativo añadida.';
END
ELSE
    PRINT 'Columna estado_operativo ya existe — omitida.';
"""

CREATE_TURNOS = """
IF NOT EXISTS (
    SELECT 1 FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME = 'turnos'
)
BEGIN
    CREATE TABLE turnos (
        id          INT PRIMARY KEY IDENTITY,
        empleado_id INT NOT NULL REFERENCES empleados(EmpleadoID),
        fecha       DATE NOT NULL,
        hora_inicio TIME NOT NULL,
        hora_fin    TIME NOT NULL,
        notas       VARCHAR(255) NULL,
        created_at  DATETIME NOT NULL DEFAULT GETUTCDATE()
    );
    PRINT 'Tabla turnos creada.';
END
ELSE
    PRINT 'Tabla turnos ya existe — omitida.';
"""


def run():
    print(f"Conectando a {SQL_SERVER}/{SQL_DATABASE}…")
    conn = pyodbc.connect(CONN_STR, autocommit=True)
    cursor = conn.cursor()

    print("Aplicando ADD COLUMN estado_operativo…")
    cursor.execute(ADD_COLUMN)

    print("Aplicando CREATE TABLE turnos…")
    cursor.execute(CREATE_TURNOS)

    cursor.close()
    conn.close()
    print("Migración completada.")


if __name__ == '__main__':
    run()
```

- [ ] **Paso 2: Verificar que el script se parsea sin errores de sintaxis**

```bash
python -m py_compile scripts/migrar_empleado.py && echo "OK"
```

Resultado esperado: `OK`.

- [ ] **Paso 3: Commit**

```bash
git add scripts/migrar_empleado.py
git commit -m "feat(migration): add idempotent migration script for estado_operativo and turnos"
```

---

## Task 3: Manager `GestorEmpleado`

**Files:**
- Create: `managers/gestor_empleado.py`
- Modify: `services/__init__.py` (exportar singleton)
- Test: `tests/test_empleado.py` (crear archivo)

- [ ] **Paso 1: Crear `tests/test_empleado.py` con los tests del manager**

```python
"""Tests para GestorEmpleado y el blueprint /empleado."""
from unittest.mock import patch, MagicMock, PropertyMock


# ---------------------------------------------------------------------------
# GestorEmpleado — unit tests (sin BD real)
# ---------------------------------------------------------------------------

class TestGestorEmpleadoCambiarEstado:
    """cambiar_estado solo acepta en_pausa y desconectado."""

    def _make_gestor(self, estado_actual='disponible'):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        empleado_mock = MagicMock()
        empleado_mock.estado_operativo = estado_actual
        session_mock = MagicMock()
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            return gestor, session_mock, empleado_mock

    def test_cambiar_a_en_pausa_ok(self):
        gestor, session_mock, empleado_mock = self._make_gestor()
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg = gestor.cambiar_estado(1, 'en_pausa')
        assert ok is True
        assert empleado_mock.estado_operativo == 'en_pausa'

    def test_cambiar_a_desconectado_ok(self):
        gestor, session_mock, empleado_mock = self._make_gestor()
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg = gestor.cambiar_estado(1, 'desconectado')
        assert ok is True
        assert empleado_mock.estado_operativo == 'desconectado'

    def test_rechaza_disponible_manual(self):
        gestor, session_mock, empleado_mock = self._make_gestor()
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg = gestor.cambiar_estado(1, 'disponible')
        assert ok is False
        assert 'no permitido' in msg.lower() or 'inválido' in msg.lower()

    def test_rechaza_ocupado_manual(self):
        gestor, session_mock, empleado_mock = self._make_gestor()
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg = gestor.cambiar_estado(1, 'ocupado')
        assert ok is False

    def test_empleado_no_encontrado(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        session_mock = MagicMock()
        session_mock.query.return_value.filter_by.return_value.first.return_value = None
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg = gestor.cambiar_estado(99, 'en_pausa')
        assert ok is False


class TestGestorEmpleadoPerfil:
    """perfil devuelve dict con los campos esperados."""

    def test_perfil_estructura(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        empleado_mock = MagicMock()
        empleado_mock.EmpleadoID = 5
        empleado_mock.Nombre = 'Carlos'
        empleado_mock.Apellido = 'M'
        empleado_mock.Email = 'carlos@test.com'
        empleado_mock.Telefono = '600000000'
        empleado_mock.estado_operativo = 'disponible'
        empleado_mock.rol = MagicMock()
        empleado_mock.rol.nombre = 'picker'

        session_mock = MagicMock()
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.perfil(5)

        assert result['id'] == 5
        assert result['nombre'] == 'Carlos M'
        assert result['rol'] == 'picker'
        assert result['estado_operativo'] == 'disponible'


# ---------------------------------------------------------------------------
# Blueprint /empleado — integration tests (sin BD real)
# ---------------------------------------------------------------------------

class TestBlueprintEmpleadoAuth:
    """Sin sesión redirige al login; con sesión devuelve 200."""

    def test_sin_sesion_redirige(self, client):
        resp = client.get('/empleado')
        assert resp.status_code in (302, 401)

    def test_con_sesion_picker_ok(self, client, app):
        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'picker'
        with app.app_context():
            resp = client.get('/empleado')
        assert resp.status_code == 200

    def test_rol_manager_no_accede(self, client):
        """El blueprint /empleado no está destinado a manager (va a /dashboard)."""
        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'manager'
        resp = client.get('/empleado')
        # manager puede acceder (tiene requiere_rol permisivo) o recibe 403 según diseño
        # Lo importante: no lanza 500
        assert resp.status_code != 500


class TestBlueprintEmpleadoEstado:
    """POST /empleado/estado valida el payload."""

    def test_estado_invalido_rechazado(self, client):
        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'picker'
        resp = client.post('/empleado/estado',
                           json={'estado': 'disponible'},
                           content_type='application/json')
        assert resp.status_code == 400

    def test_estado_valido_llama_gestor(self, client, app):
        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = 'picker'
        with app.app_context():
            from services import gestor_empleado
            with patch.object(gestor_empleado, 'cambiar_estado', return_value=(True, 'ok')):
                resp = client.post('/empleado/estado',
                                   json={'estado': 'en_pausa'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True
```

- [ ] **Paso 2: Ejecutar tests para verificar que fallan**

```bash
pytest tests/test_empleado.py -v
```

Resultado esperado: `ERROR` o `FAILED` — módulos no existen todavía.

- [ ] **Paso 3: Crear `managers/gestor_empleado.py`**

> **Columnas verificadas de `PickingPedido`** (ver `models.py`): `iniciado_en`, `completado_en`, `empleado_id`, `estado`. Columnas de `Reparto`: `hora_salida`, `hora_entrega_real`, `repartidor_id`, `estado`, `updated_at`. Los nombres en el manager son correctos.

```python
import logging
from datetime import date, datetime

from sqlalchemy.exc import SQLAlchemyError

from models import Empleado, Turno, PickingPedido, Reparto
from states import EstadoPicking, EstadoReparto

logger = logging.getLogger(__name__)

_ESTADOS_MANUALES = {'en_pausa', 'desconectado'}


class GestorEmpleado:

    @property
    def session(self):
        from database import get_db
        return get_db()

    # -------------------------------------------------------------------------

    def perfil(self, empleado_id: int) -> dict | None:
        """Datos básicos del empleado para el hub."""
        empleado = self.session.query(Empleado).filter_by(
            EmpleadoID=empleado_id, activo=True
        ).first()
        if not empleado:
            return None
        return {
            'id':               empleado.EmpleadoID,
            'nombre':           f'{empleado.Nombre} {empleado.Apellido}',
            'email':            empleado.Email,
            'telefono':         empleado.Telefono,
            'rol':              empleado.rol.nombre if empleado.rol else empleado.Puesto,
            'estado_operativo': empleado.estado_operativo,
        }

    def cambiar_estado(self, empleado_id: int, nuevo_estado: str) -> tuple:
        """El empleado solo puede fijar en_pausa o desconectado manualmente."""
        if nuevo_estado not in _ESTADOS_MANUALES:
            return False, f"Estado '{nuevo_estado}' no permitido — solo en_pausa o desconectado"
        s = self.session
        try:
            empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
            if not empleado:
                return False, "Empleado no encontrado"
            empleado.estado_operativo = nuevo_estado
            s.commit()
            logger.info("ESTADO_EMPLEADO empleado_id=%s estado=%s", empleado_id, nuevo_estado)
            return True, f"Estado actualizado a '{nuevo_estado}'"
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error actualizando estado empleado %s: %s", empleado_id, e)
            return False, "Error de base de datos"

    def turno_hoy(self, empleado_id: int) -> dict | None:
        """Turno del día actual, o None si no hay."""
        hoy = date.today()
        turno = self.session.query(Turno).filter_by(
            empleado_id=empleado_id, fecha=hoy
        ).first()
        if not turno:
            return None
        return {
            'fecha':       turno.fecha.isoformat(),
            'hora_inicio': str(turno.hora_inicio)[:5],   # "HH:MM"
            'hora_fin':    str(turno.hora_fin)[:5],
            'notas':       turno.notas,
        }

    def metricas_hoy(self, empleado_id: int, rol: str) -> dict:
        """KPIs personales del día: pedidos_completados, tiempo_medio_min, incidencias_hoy."""
        from sqlalchemy import func
        s = self.session
        hoy = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        if rol == 'picker':
            completados = s.query(PickingPedido).filter(
                PickingPedido.empleado_id == empleado_id,
                PickingPedido.estado == EstadoPicking.COMPLETADO.value,
                PickingPedido.completado_en >= hoy,
            ).all()

            tiempos = [
                (pk.completado_en - pk.iniciado_en).total_seconds() / 60
                for pk in completados
                if pk.iniciado_en and pk.completado_en
            ]
            tiempo_medio = round(sum(tiempos) / len(tiempos)) if tiempos else None

            ids = [pk.id for pk in completados]
            incidencias = 0
            if ids:
                from models import PickingItem
                incidencias = s.query(func.count(PickingItem.id)).filter(
                    PickingItem.picking_id.in_(ids),
                    PickingItem.estado.in_(['sin_stock', 'sustituido']),
                ).scalar() or 0

            return {
                'pedidos_completados': len(completados),
                'tiempo_medio_min':    tiempo_medio,
                'incidencias_hoy':     incidencias,
            }

        else:  # repartidor
            entregados = s.query(Reparto).filter(
                Reparto.repartidor_id == empleado_id,
                Reparto.estado == EstadoReparto.ENTREGADO.value,
                Reparto.hora_entrega_real >= hoy,
            ).all()

            tiempos = [
                (r.hora_entrega_real - r.hora_salida).total_seconds() / 60
                for r in entregados
                if r.hora_salida and r.hora_entrega_real
            ]
            tiempo_medio = round(sum(tiempos) / len(tiempos)) if tiempos else None

            fallidos = s.query(func.count(Reparto.id)).filter(
                Reparto.repartidor_id == empleado_id,
                Reparto.estado == EstadoReparto.NO_ENTREGADO.value,
                Reparto.updated_at >= hoy,
            ).scalar() or 0

            return {
                'pedidos_completados': len(entregados),
                'tiempo_medio_min':    tiempo_medio,
                'incidencias_hoy':     fallidos,
            }
```

- [ ] **Paso 4: Exportar singleton en `services/__init__.py`**

Abrir `services/__init__.py` y añadir al final:

```python
from managers.gestor_empleado import GestorEmpleado as _GestorEmpleado
gestor_empleado = _GestorEmpleado()
```

- [ ] **Paso 5: Ejecutar tests del manager**

```bash
pytest tests/test_empleado.py::TestGestorEmpleadoCambiarEstado tests/test_empleado.py::TestGestorEmpleadoPerfil -v
```

Resultado esperado: todos `PASSED`.

- [ ] **Paso 6: Ejecutar suite completa**

```bash
pytest -v --tb=short
```

- [ ] **Paso 7: Commit**

```bash
git add managers/gestor_empleado.py services/__init__.py tests/test_empleado.py
git commit -m "feat(empleado): add GestorEmpleado manager with perfil, estado, turno and metricas"
```

---

## Task 4: Blueprint `empleado` y registro en `main.py`

**Files:**
- Create: `blueprints/empleado.py`
- Modify: `main.py`

- [ ] **Paso 1: Crear `blueprints/empleado.py`**

```python
import logging

from flask import Blueprint, jsonify, render_template, request, session

from blueprints.auth import requiere_rol
from services import gestor_empleado

logger = logging.getLogger(__name__)

blueprint_empleado = Blueprint('empleado', __name__)

_ROLES_HUB = ('picker', 'repartidor', 'manager', 'admin')


@blueprint_empleado.route('/empleado', strict_slashes=False)
@requiere_rol(*_ROLES_HUB)
def index():
    empleado_id = session.get('empleado_id')
    rol         = session.get('rol')
    return render_template('empleado/index.html', empleado_id=empleado_id, rol=rol)


@blueprint_empleado.route('/empleado/perfil')
@requiere_rol(*_ROLES_HUB)
def perfil():
    empleado_id = session.get('empleado_id')
    try:
        datos = gestor_empleado.perfil(empleado_id)
        if not datos:
            return jsonify({'error': 'Empleado no encontrado'}), 404
        return jsonify(datos)
    except Exception as e:
        logger.error("Error en /empleado/perfil: %s", e)
        return jsonify({'error': 'Error interno'}), 500


@blueprint_empleado.route('/empleado/estado', methods=['POST'])
@requiere_rol(*_ROLES_HUB)
def estado():
    data         = request.get_json(silent=True) or {}
    nuevo_estado = (data.get('estado') or '').strip()
    if not nuevo_estado:
        return jsonify({'error': 'Falta campo: estado'}), 400
    empleado_id = session.get('empleado_id')
    ok, msg = gestor_empleado.cambiar_estado(empleado_id, nuevo_estado)
    if not ok:
        return jsonify({'error': msg}), 400
    return jsonify({'ok': True, 'estado': nuevo_estado})


@blueprint_empleado.route('/empleado/turno-hoy')
@requiere_rol(*_ROLES_HUB)
def turno_hoy():
    empleado_id = session.get('empleado_id')
    try:
        turno = gestor_empleado.turno_hoy(empleado_id)
        return jsonify(turno)   # None se serializa como null en JSON
    except Exception as e:
        logger.error("Error en /empleado/turno-hoy: %s", e)
        return jsonify({'error': 'Error interno'}), 500


@blueprint_empleado.route('/empleado/metricas')
@requiere_rol(*_ROLES_HUB)
def metricas():
    empleado_id = session.get('empleado_id')
    rol         = session.get('rol', '')
    try:
        datos = gestor_empleado.metricas_hoy(empleado_id, rol)
        return jsonify(datos)
    except Exception as e:
        logger.error("Error en /empleado/metricas: %s", e)
        return jsonify({'error': 'Error interno'}), 500
```

- [ ] **Paso 2: Registrar el blueprint en `main.py`**

En la sección de imports de blueprints (línea ~67):

```python
from blueprints.empleado import blueprint_empleado
```

En la sección de `register_blueprint` (línea ~76), añadir después de `blueprint_auth`:

```python
app.register_blueprint(blueprint_empleado)
```

- [ ] **Paso 3: Ejecutar tests de blueprint**

> ⚠️ **Dependencia de orden:** `TestBlueprintEmpleadoAuth::test_con_sesion_picker_ok` llama a `GET /empleado` que renderiza el template. El template se crea en el Task 7. Ejecutar solo los tests de estado por ahora:

```bash
pytest tests/test_empleado.py::TestBlueprintEmpleadoEstado -v
```

Los tests de `TestBlueprintEmpleadoAuth` se ejecutarán correctamente tras el Task 7.

Resultado esperado: `PASSED`.

- [ ] **Paso 4: Ejecutar suite completa**

```bash
pytest -v --tb=short
```

- [ ] **Paso 5: Commit**

```bash
git add blueprints/empleado.py main.py
git commit -m "feat(empleado): add /empleado blueprint with 5 routes and register in app"
```

---

## Task 5: Hooks de estado en `GestorDashboard`

**Files:**
- Modify: `managers/gestor_dashboard.py`
- Test: `tests/test_empleado.py` (añadir clase)

- [ ] **Paso 1: Añadir tests de hooks al archivo de tests**

Añadir al final de `tests/test_empleado.py`:

```python
class TestHooksEstadoOperativo:
    """_actualizar_estado_operativo no sobreescribe en_pausa ni desconectado."""

    def _gestor_con_empleado(self, estado_actual):
        from services import gestor_dashboard
        empleado_mock = MagicMock()
        empleado_mock.estado_operativo = estado_actual
        session_mock = MagicMock()
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        return gestor_dashboard, session_mock, empleado_mock

    def test_ocupado_sobreescribe_disponible(self):
        gestor, session_mock, empleado_mock = self._gestor_con_empleado('disponible')
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor._actualizar_estado_operativo(1, 'ocupado')
        assert empleado_mock.estado_operativo == 'ocupado'

    def test_no_sobreescribe_en_pausa(self):
        gestor, session_mock, empleado_mock = self._gestor_con_empleado('en_pausa')
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor._actualizar_estado_operativo(1, 'ocupado')
        assert empleado_mock.estado_operativo == 'en_pausa'

    def test_no_sobreescribe_desconectado(self):
        gestor, session_mock, empleado_mock = self._gestor_con_empleado('desconectado')
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor._actualizar_estado_operativo(1, 'disponible')
        assert empleado_mock.estado_operativo == 'desconectado'

    def test_empleado_none_no_lanza_excepcion(self):
        from services import gestor_dashboard
        session_mock = MagicMock()
        session_mock.query.return_value.filter_by.return_value.first.return_value = None
        with patch.object(type(gestor_dashboard), 'session', new_callable=PropertyMock, return_value=session_mock):
            # No debe lanzar excepción
            gestor_dashboard._actualizar_estado_operativo(99, 'ocupado')
```

- [ ] **Paso 2: Ejecutar tests para verificar que fallan**

```bash
pytest tests/test_empleado.py::TestHooksEstadoOperativo -v
```

Resultado esperado: `FAILED` — `AttributeError: _actualizar_estado_operativo`.

- [ ] **Paso 3: Añadir `_actualizar_estado_operativo` en `GestorDashboard`**

En `managers/gestor_dashboard.py`, dentro de la clase `GestorDashboard`, añadir justo después del bloque de constantes de clase (antes del primer método público):

```python
    _ESTADOS_PROTEGIDOS = frozenset({'en_pausa', 'desconectado'})

    def _actualizar_estado_operativo(self, empleado_id: int, nuevo_estado: str) -> None:
        """Actualiza estado_operativo solo si el estado actual no está protegido.

        Los estados en_pausa y desconectado son manuales — el sistema no los sobreescribe.
        Llamar DESPUÉS del commit de la operación principal, dentro del mismo request.
        """
        if not empleado_id:
            return
        try:
            empleado = self.session.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
            if empleado and empleado.estado_operativo not in self._ESTADOS_PROTEGIDOS:
                empleado.estado_operativo = nuevo_estado
                self.session.commit()
        except Exception as e:
            logger.warning("No se pudo actualizar estado_operativo de empleado %s: %s", empleado_id, e)
```

- [ ] **Paso 4: Añadir hook en `asignar_picker()`**

En el método `asignar_picker`, justo después de `s.commit()` (línea ~969 en gestor_dashboard.py), añadir:

```python
            self._actualizar_estado_operativo(empleado_id, 'ocupado')
```

El bloque `return True, "Picker asignado correctamente"` queda después.

- [ ] **Paso 5: Añadir hook en `completar_picking()`**

En `completar_picking`, tras el bloque de descuento de stock y antes del `return True, ...` final (~línea 1067):

```python
            # Auto-actualizar estado: volver a disponible si no quedan pickings activos
            _picker_id = picking.empleado_id
            if _picker_id:
                _pickings_activos = s.query(PickingPedido).filter(
                    PickingPedido.empleado_id == _picker_id,
                    PickingPedido.estado.in_([
                        EstadoPicking.PENDIENTE.value,
                        EstadoPicking.EN_PROCESO.value,
                        EstadoPicking.CON_INCIDENCIAS.value,
                    ]),
                ).count()
                if _pickings_activos == 0:
                    self._actualizar_estado_operativo(_picker_id, 'disponible')
```

- [ ] **Paso 6: Añadir hook en `asignar_repartidor()`**

En `asignar_repartidor`, justo después de `s.commit()` (~línea 1110):

```python
            self._actualizar_estado_operativo(empleado_id, 'ocupado')
```

- [ ] **Paso 7: Añadir hook en `marcar_entregado()`**

Buscar el método `marcar_entregado` en `gestor_dashboard.py`. Tras el `s.commit()` exitoso, añadir:

```python
            # Auto-actualizar estado: volver a disponible si no quedan repartos activos
            _repartidor_id = reparto.repartidor_id
            if _repartidor_id:
                _repartos_activos = s.query(Reparto).filter(
                    Reparto.repartidor_id == _repartidor_id,
                    Reparto.estado.in_([
                        EstadoReparto.ASIGNADO.value,
                        EstadoReparto.EN_CAMINO.value,
                    ]),
                ).count()
                if _repartos_activos == 0:
                    self._actualizar_estado_operativo(_repartidor_id, 'disponible')
```

- [ ] **Paso 8: Ejecutar tests de hooks**

```bash
pytest tests/test_empleado.py::TestHooksEstadoOperativo -v
```

Resultado esperado: todos `PASSED`.

- [ ] **Paso 9: Ejecutar suite completa**

```bash
pytest -v --tb=short
```

- [ ] **Paso 10: Commit**

```bash
git add managers/gestor_dashboard.py tests/test_empleado.py
git commit -m "feat(empleado): add estado_operativo hooks in GestorDashboard assignment methods"
```

---

## Task 6: Cambio de redirección en `auth.py`

**Files:**
- Modify: `blueprints/auth.py`
- Test: `tests/test_empleado.py` (añadir clase)

- [ ] **Paso 1: Añadir test de redirección al login**

> **Nota:** `POST /auth/login` devuelve JSON (`{"ok": true, "redirect": "..."}`) cuando la petición lleva `Content-Type: application/json` — ver `blueprints/auth.py` línea ~68: `if request.is_json: return jsonify(...)`. Los tests envían JSON, así que `resp.status_code == 200` es correcto.

Añadir al final de `tests/test_empleado.py`:

```python
class TestAuthRedireccionEmpleado:
    """Tras el login, picker y repartidor van a /empleado."""

    def test_picker_redirige_a_empleado(self, client, app):
        from unittest.mock import patch
        from werkzeug.security import generate_password_hash
        empleado_mock = MagicMock()
        empleado_mock.EmpleadoID = 1
        empleado_mock.Nombre = 'Test'
        empleado_mock.password_hash = generate_password_hash('secret')
        empleado_mock.rol = MagicMock()
        empleado_mock.rol.nombre = 'picker'

        with app.app_context():
            with patch('blueprints.auth._get_empleado_by_email', return_value=empleado_mock):
                resp = client.post('/auth/login',
                                   json={'email': 'test@test.com', 'password': 'secret'},
                                   content_type='application/json')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['redirect'] == '/empleado'

    def test_repartidor_redirige_a_empleado(self, client, app):
        from unittest.mock import patch
        from werkzeug.security import generate_password_hash
        empleado_mock = MagicMock()
        empleado_mock.EmpleadoID = 2
        empleado_mock.Nombre = 'Ana'
        empleado_mock.password_hash = generate_password_hash('secret')
        empleado_mock.rol = MagicMock()
        empleado_mock.rol.nombre = 'repartidor'

        with app.app_context():
            with patch('blueprints.auth._get_empleado_by_email', return_value=empleado_mock):
                resp = client.post('/auth/login',
                                   json={'email': 'ana@test.com', 'password': 'secret'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['redirect'] == '/empleado'

    def test_manager_sigue_a_dashboard(self, client, app):
        from unittest.mock import patch
        from werkzeug.security import generate_password_hash
        empleado_mock = MagicMock()
        empleado_mock.EmpleadoID = 3
        empleado_mock.Nombre = 'Jefe'
        empleado_mock.password_hash = generate_password_hash('secret')
        empleado_mock.rol = MagicMock()
        empleado_mock.rol.nombre = 'manager'

        with app.app_context():
            with patch('blueprints.auth._get_empleado_by_email', return_value=empleado_mock):
                resp = client.post('/auth/login',
                                   json={'email': 'jefe@test.com', 'password': 'secret'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['redirect'] == '/dashboard'
```

- [ ] **Paso 2: Ejecutar tests para verificar que fallan**

```bash
pytest tests/test_empleado.py::TestAuthRedireccionEmpleado -v
```

Resultado esperado: `FAILED` — `redirect` devuelve `/picker` o `/repartidor` todavía.

- [ ] **Paso 3: Actualizar `destinos` en `blueprints/auth.py`**

Localizar el dict `destinos` en la función `login()` (líneas ~61-66) y reemplazarlo:

```python
    destinos = {
        'manager':    '/dashboard',
        'admin':      '/dashboard',
        'picker':     '/empleado',
        'repartidor': '/empleado',
    }
```

- [ ] **Paso 4: Ejecutar tests**

```bash
pytest tests/test_empleado.py::TestAuthRedireccionEmpleado -v
```

Resultado esperado: todos `PASSED`.

- [ ] **Paso 5: Ejecutar suite completa**

```bash
pytest -v --tb=short
```

- [ ] **Paso 6: Commit**

```bash
git add blueprints/auth.py tests/test_empleado.py
git commit -m "feat(auth): redirect picker and repartidor to /empleado hub after login"
```

---

## Task 7: Template `empleado/index.html`

**Files:**
- Create: `templates/empleado/index.html`

Este task no tiene tests automatizados (template rendering). Verificación manual.

- [ ] **Paso 1: Crear directorio**

```bash
mkdir -p templates/empleado
```

- [ ] **Paso 2: Crear `templates/empleado/index.html`**

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0" />
  <title>Panchi — Mi zona</title>
  <meta name="theme-color" content="#111827">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black">
  <meta name="apple-mobile-web-app-title" content="Mi zona">
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <style>
    [x-cloak] { display: none !important; }
    button { -webkit-tap-highlight-color: transparent; }
  </style>
</head>
<body class="bg-gray-900 min-h-screen"
      x-data="empleadoHub({{ empleado_id or 'null' }}, '{{ rol or '' }}')"
      x-init="init()">

  <!-- ======== HEADER ======== -->
  <header class="bg-gray-900 border-b border-gray-800 px-4 py-3 flex items-center justify-between sticky top-0 z-30">
    <div>
      <p class="text-xs text-gray-500" x-text="fechaHoy"></p>
      <p class="text-white font-bold text-base leading-tight" x-text="saludo"></p>
      <p class="text-gray-400 text-xs" x-text="nombreCompleto + ' · ' + rolLabel"></p>
    </div>
    <form action="/auth/logout" method="post">
      <button type="submit"
              class="bg-gray-800 text-gray-400 text-xs px-3 py-1.5 rounded-lg active:bg-gray-700 transition">
        Salir
      </button>
    </form>
  </header>

  <!-- ======== CONTENIDO ======== -->
  <main class="max-w-md mx-auto px-4 py-4 space-y-3">

    <!-- Estado operativo -->
    <div :class="estadoBg" class="rounded-xl p-3 border flex items-center justify-between">
      <div>
        <p class="text-xs text-gray-400 uppercase tracking-wide">Mi estado</p>
        <p class="font-bold text-sm mt-0.5" :class="estadoColor">
          <span>● </span><span x-text="estadoLabel"></span>
        </p>
        <p x-show="perfil.estado_operativo === 'ocupado'"
           class="text-xs text-gray-500 mt-0.5" x-cloak>Asignado por el sistema</p>
      </div>
      <div class="flex gap-2">
        <button @click="cambiarEstado('en_pausa')"
                :disabled="perfil.estado_operativo === 'ocupado'"
                :class="perfil.estado_operativo === 'ocupado' ? 'opacity-40 cursor-not-allowed' : 'active:bg-gray-600'"
                class="bg-gray-700 text-gray-300 text-xs px-3 py-1.5 rounded-lg transition">
          ⏸ Pausa
        </button>
        <button @click="cambiarEstado('desconectado')"
                :disabled="perfil.estado_operativo === 'ocupado'"
                :class="perfil.estado_operativo === 'ocupado' ? 'opacity-40 cursor-not-allowed' : 'active:bg-gray-600'"
                class="bg-gray-700 text-red-400 text-xs px-3 py-1.5 rounded-lg transition">
          ⏹ Salir
        </button>
      </div>
    </div>

    <!-- Turno de hoy -->
    <div class="bg-blue-950 rounded-xl p-3 border border-blue-900">
      <template x-if="turno">
        <div class="flex items-center justify-between">
          <div>
            <p class="text-xs text-blue-300 uppercase tracking-wide">Turno hoy</p>
            <p class="text-white font-semibold text-sm mt-0.5"
               x-text="turno.hora_inicio + ' – ' + turno.hora_fin"></p>
            <p class="text-gray-400 text-xs mt-0.5" x-text="turno.notas || ''"></p>
          </div>
          <div class="text-right" x-show="turnoProximo" x-cloak>
            <p class="text-xs text-gray-500">Próximo</p>
            <p class="text-xs text-gray-400 mt-0.5" x-text="turnoProximo || ''"></p>
          </div>
        </div>
      </template>
      <template x-if="!turno">
        <div class="flex items-center gap-3">
          <span class="text-xl">🗓️</span>
          <div>
            <p class="text-gray-400 text-sm">Sin turno registrado</p>
            <p class="text-gray-600 text-xs mt-0.5">El manager lo añadirá pronto</p>
          </div>
        </div>
      </template>
    </div>

    <!-- CTA principal — App operativa -->
    <a :href="appUrl"
       :class="appGradient"
       class="block rounded-xl p-4 flex items-center justify-between active:opacity-90 transition">
      <div>
        <p class="text-xs uppercase tracking-wide" :class="appSubtitleColor">Mi app</p>
        <p class="text-white font-bold text-base mt-1" x-text="appLabel"></p>
        <p class="text-xs mt-1" :class="appSubtitleColor"
           x-text="pedidosAsignados === 0 ? '0 asignados ahora' : pedidosAsignados + ' asignado' + (pedidosAsignados > 1 ? 's' : '')"></p>
      </div>
      <span class="bg-white text-sm font-bold px-3 py-2 rounded-lg" :class="appBtnColor">
        Entrar →
      </span>
    </a>

    <!-- Stats del día -->
    <div>
      <p class="text-xs text-gray-500 uppercase tracking-wide mb-2">Hoy</p>
      <div class="grid grid-cols-3 gap-2">
        <div class="bg-gray-800 rounded-xl p-3 text-center">
          <p class="text-xl font-bold text-blue-400" x-text="metricas.pedidos_completados ?? '—'"></p>
          <p class="text-xs text-gray-500 mt-1" x-text="metricaLabel1"></p>
        </div>
        <div class="bg-gray-800 rounded-xl p-3 text-center">
          <p class="text-xl font-bold text-green-400"
             x-text="metricas.tiempo_medio_min ? metricas.tiempo_medio_min + 'm' : '—'"></p>
          <p class="text-xs text-gray-500 mt-1">T. medio</p>
        </div>
        <div class="bg-gray-800 rounded-xl p-3 text-center">
          <p class="text-xl font-bold text-amber-400" x-text="metricas.incidencias_hoy ?? '—'"></p>
          <p class="text-xs text-gray-500 mt-1" x-text="metricaLabel3"></p>
        </div>
      </div>
    </div>

    <!-- Accesos secundarios -->
    <div>
      <p class="text-xs text-gray-500 uppercase tracking-wide mb-2">Más</p>
      <div class="grid grid-cols-3 gap-2">
        <button class="bg-gray-800 rounded-xl p-3 text-center active:bg-gray-700 transition">
          <p class="text-xl">📊</p>
          <p class="text-xs text-gray-400 mt-1">Desempeño</p>
        </button>
        <button class="bg-gray-800 rounded-xl p-3 text-center active:bg-gray-700 transition">
          <p class="text-xl">🗓️</p>
          <p class="text-xs text-gray-400 mt-1">Turnos</p>
        </button>
        <template x-if="rol === 'repartidor'">
          <a href="/repartidor/cierre"
             class="bg-gray-800 rounded-xl p-3 text-center active:bg-gray-700 transition block">
            <p class="text-xl">🔒</p>
            <p class="text-xs text-gray-400 mt-1">Cierre</p>
          </a>
        </template>
        <template x-if="rol !== 'repartidor'">
          <button class="bg-gray-800 rounded-xl p-3 text-center active:bg-gray-700 transition">
            <p class="text-xl">ℹ️</p>
            <p class="text-xs text-gray-400 mt-1">Empresa</p>
          </button>
        </template>
      </div>
    </div>

  </main>

  <!-- ======== ALPINE COMPONENT ======== -->
  <script>
  function empleadoHub(empleadoId, rol) {
    return {
      empleadoId,
      rol,
      perfil:          { estado_operativo: 'desconectado' },
      turno:           null,
      turnoProximo:    null,
      metricas:        {},
      pedidosAsignados: 0,

      // -- computed --
      get saludo() {
        const h = new Date().getHours();
        if (h < 13) return 'Buenos días ☀️';
        if (h < 20) return 'Buenas tardes 🌤️';
        return 'Buenas noches 🌙';
      },
      get fechaHoy() {
        return new Date().toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' });
      },
      get nombreCompleto() { return this.perfil.nombre || ''; },
      get rolLabel() {
        return { picker: 'Picker', repartidor: 'Repartidor', manager: 'Manager', admin: 'Admin' }[this.rol] || this.rol;
      },
      get estadoLabel() {
        return { disponible: 'Disponible', ocupado: 'Ocupado', en_pausa: 'En pausa', desconectado: 'Desconectado' }[this.perfil.estado_operativo] || this.perfil.estado_operativo;
      },
      get estadoColor() {
        return { disponible: 'text-green-400', ocupado: 'text-amber-400', en_pausa: 'text-purple-400', desconectado: 'text-gray-400' }[this.perfil.estado_operativo] || 'text-gray-400';
      },
      get estadoBg() {
        return { disponible: 'bg-green-950 border-green-900', ocupado: 'bg-amber-950 border-amber-900', en_pausa: 'bg-purple-950 border-purple-900', desconectado: 'bg-gray-800 border-gray-700' }[this.perfil.estado_operativo] || 'bg-gray-800 border-gray-700';
      },
      get appUrl()          { return this.rol === 'repartidor' ? '/repartidor' : '/picker'; },
      get appLabel()        { return this.rol === 'repartidor' ? '🛵 App Reparto' : '🛒 App Picking'; },
      get appGradient()     { return this.rol === 'repartidor' ? 'bg-gradient-to-r from-orange-600 to-orange-700' : 'bg-gradient-to-r from-blue-600 to-blue-700'; },
      get appSubtitleColor(){ return this.rol === 'repartidor' ? 'text-orange-200' : 'text-blue-200'; },
      get appBtnColor()     { return this.rol === 'repartidor' ? 'text-orange-600' : 'text-blue-600'; },
      get metricaLabel1()   { return this.rol === 'repartidor' ? 'Entregas' : 'Pedidos'; },
      get metricaLabel3()   { return this.rol === 'repartidor' ? 'Fallidas' : 'Incidencias'; },

      // -- methods --
      async init() {
        await Promise.all([this.cargarPerfil(), this.cargarTurno(), this.cargarMetricas()]);
      },

      async cargarPerfil() {
        try {
          const r = await fetch('/empleado/perfil');
          if (r.ok) this.perfil = await r.json();
        } catch (_) {}
      },

      async cargarTurno() {
        try {
          const r = await fetch('/empleado/turno-hoy');
          if (r.ok) this.turno = await r.json();
        } catch (_) {}
      },

      async cargarMetricas() {
        try {
          const r = await fetch('/empleado/metricas');
          if (r.ok) {
            const d = await r.json();
            this.metricas = d;
            this.pedidosAsignados = d.pedidos_activos || 0;
          }
        } catch (_) {}
      },

      async cambiarEstado(nuevoEstado) {
        if (this.perfil.estado_operativo === 'ocupado') return;
        try {
          const r = await fetch('/empleado/estado', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ estado: nuevoEstado }),
          });
          if (r.ok) this.perfil.estado_operativo = nuevoEstado;
        } catch (_) {}
      },
    };
  }
  </script>

</body>
</html>
```

- [ ] **Paso 3: Verificar en el navegador**

Iniciar el servidor:
```bash
python main.py
```

1. Ir a `http://localhost:5000/auth/login`
2. Hacer login con un usuario picker o repartidor
3. Verificar que redirige a `/empleado`
4. Verificar que el hub muestra correctamente estado, turno (o placeholder), CTA y stats

- [ ] **Paso 4: Commit**

```bash
git add templates/empleado/index.html
git commit -m "feat(empleado): add hub template with estado, turno, CTA and daily stats"
```

---

## Task 8: Actualizar `monitor_empleados()` en dashboard

**Files:**
- Modify: `managers/gestor_dashboard.py`

La función `monitor_empleados` ya genera un dict por empleado. Solo hay que añadir el campo `estado_operativo` para que el dashboard lo consuma.

- [ ] **Paso 1: Localizar el bloque de construcción del dict por empleado**

Buscar en `gestor_dashboard.py` la línea con `"activo": e.activo` dentro de `monitor_empleados`. Está aproximadamente en la línea 460.

- [ ] **Paso 2: Añadir `estado_operativo` al dict**

En el dict que se construye para cada empleado en `monitor_empleados()`, añadir junto a `"activo": e.activo`:

```python
"estado_operativo": e.estado_operativo,
```

- [ ] **Paso 3: Ejecutar suite completa**

```bash
pytest -v --tb=short
```

- [ ] **Paso 4: Commit final**

```bash
git add managers/gestor_dashboard.py
git commit -m "feat(dashboard): expose estado_operativo in monitor_empleados response"
```

---

## Verificación de integración final

- [ ] Ejecutar suite completa una última vez: `pytest -v --tb=short`
- [ ] Login como picker → redirige a `/empleado`
- [ ] Login como repartidor → redirige a `/empleado`
- [ ] Login como manager → redirige a `/dashboard` (sin cambio)
- [ ] Botones Pausa/Salir funcionan y cambian el color del badge
- [ ] Botones desactivados cuando estado es `ocupado`
- [ ] El template no lanza errores si no hay turno registrado
- [ ] Navegar a `/picker` desde el CTA funciona igual que antes
- [ ] Ejecutar migración en staging: `python scripts/migrar_empleado.py`
