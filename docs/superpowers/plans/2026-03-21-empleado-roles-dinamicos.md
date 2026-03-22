# Empleado — Roles Dinámicos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir que un empleado con múltiples capacidades (picker + repartidor) elija su rol operativo al iniciar el turno y lo cambie durante el día, con bloqueo duro si tiene tareas activas.

**Architecture:** Nueva tabla `empleado_capacidades` (qué roles puede hacer cada empleado) + columna `rol_activo` en `empleados` (cuál está usando ahora). El login setea `session['rol']` desde `rol_activo` en BD en lugar del FK fijo. Un endpoint `POST /empleado/cambiar-rol` valida el bloqueo y actualiza ambos. Una pantalla de check-in (`/empleado/checkin`) reemplaza el acceso directo al hub cuando el empleado es polivalente y no ha elegido rol hoy.

**Tech Stack:** Flask, SQLAlchemy 2.x, SQL Server (mssql+pyodbc), Alpine.js, Tailwind CSS, pytest + unittest.mock

**Spec:** `docs/superpowers/specs/2026-03-21-modulo-empleado-roles-dinamicos-design.md`

---

## File Map

| Archivo | Acción | Qué hace |
|---|---|---|
| `models.py` | Modificar | Añadir `EmpleadoCapacidad`; `rol_activo` en `Empleado`; `AuditLog.pedido_id` → nullable |
| `managers/gestor_empleado.py` | Modificar | 5 métodos nuevos: `capacidades`, `es_polivalente`, `tiene_rol_activo`, `cambiar_rol`, `carga_operativa` |
| `blueprints/auth.py` | Modificar | Login lee capacidades; nuevo helper `requiere_autenticacion`; logout nula `rol_activo` |
| `blueprints/empleado.py` | Modificar | Index redirige a checkin si procede; 4 endpoints nuevos |
| `templates/empleado/checkin.html` | Crear | Pantalla de selección de rol con carga operativa |
| `templates/empleado/index.html` | Modificar | Alpine carga capacidades, muestra "⇄ Cambiar rol", modal de bloqueo |
| `tests/test_empleado.py` | Modificar | Tests nuevos para cambiar_rol, capacidades, checkin, endpoints |
| `scripts/migrate_capacidades.py` | Crear | Script de migración one-time |

---

## Task 1: Modelo EmpleadoCapacidad + columna rol_activo + AuditLog nullable

**Files:**
- Modify: `models.py`
- Modify: `tests/test_empleado.py`

- [ ] **Step 1: Escribir test que verifica la existencia del modelo y columnas**

Añadir al final de `tests/test_empleado.py`:

```python
class TestModelosNuevos:
    """Verifica que EmpleadoCapacidad y rol_activo existen en models.py."""

    def test_empleado_capacidad_modelo_existe(self):
        import inspect
        import models
        src = inspect.getsource(models)
        assert 'EmpleadoCapacidad' in src
        assert 'empleado_capacidades' in src

    def test_empleado_tiene_rol_activo(self):
        import inspect
        import models
        src = inspect.getsource(models)
        assert 'rol_activo' in src

    def test_auditlog_pedido_id_nullable(self):
        """AuditLog.pedido_id debe ser nullable para eventos sin pedido."""
        from models import AuditLog
        col = AuditLog.__table__.columns['pedido_id']
        assert col.nullable is True, "pedido_id debe ser nullable=True"
```

- [ ] **Step 2: Ejecutar tests para verificar que fallan**

```bash
pytest tests/test_empleado.py::TestModelosNuevos -v
```

Resultado esperado: 3 FAILED (EmpleadoCapacidad no existe, rol_activo no existe, nullable=False)

- [ ] **Step 3: Añadir `EmpleadoCapacidad` a `models.py`**

En `models.py`, después de la clase `Empleado` (línea ~207), añadir:

```python
class EmpleadoCapacidad(Base):
    """Roles operativos que puede desempeñar un empleado (picker, repartidor)."""
    __tablename__ = 'empleado_capacidades'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    empleado_id = Column(Integer, ForeignKey('empleados.EmpleadoID'), nullable=False)
    rol         = Column(String(20), nullable=False)   # 'picker' | 'repartidor'

    empleado = relationship('Empleado', back_populates='capacidades')

    __table_args__ = (
        __import__('sqlalchemy').UniqueConstraint('empleado_id', 'rol', name='uq_empleado_rol'),
    )
```

- [ ] **Step 4: Añadir `rol_activo` y relación `capacidades` a la clase `Empleado`**

En `models.py`, dentro de la clase `Empleado`, tras `estado_operativo` (línea ~197):

```python
    rol_activo = Column(String(20), nullable=True)     # picker | repartidor | NULL
```

Y tras la línea de `turnos = relationship(...)` (última relación de Empleado):

```python
    capacidades = relationship('EmpleadoCapacidad', back_populates='empleado',
                               cascade='all, delete-orphan')
```

- [ ] **Step 5: Hacer `AuditLog.pedido_id` nullable**

En `models.py`, en la clase `AuditLog`, línea ~140, cambiar:

```python
    # Antes:
    pedido_id = Column(Integer, ForeignKey('pedidos.PedidoID'), nullable=False)
    # Después:
    pedido_id = Column(Integer, ForeignKey('pedidos.PedidoID'), nullable=True)
```

- [ ] **Step 6: Ejecutar los tests del modelo**

```bash
pytest tests/test_empleado.py::TestModelosNuevos -v
```

Resultado esperado: 3 PASSED

- [ ] **Step 7: Ejecutar suite completa para verificar que nada se rompió**

```bash
pytest -v --tb=short
```

Resultado esperado: mismo número de PASSED que antes (los 3 TestWebhookMonei conocidos siguen fallando — es normal).

- [ ] **Step 8: Commit**

```bash
git add models.py tests/test_empleado.py
git commit -m "feat: add EmpleadoCapacidad model, rol_activo column, AuditLog nullable pedido_id"
```

---

## Task 2: GestorEmpleado — 5 métodos nuevos

**Files:**
- Modify: `managers/gestor_empleado.py`
- Modify: `tests/test_empleado.py`

- [ ] **Step 1: Escribir tests para `capacidades`, `es_polivalente`, `tiene_rol_activo`**

Añadir a `tests/test_empleado.py`:

```python
class TestGestorEmpleadoCapacidades:
    """capacidades / es_polivalente / tiene_rol_activo."""

    def _make_gestor(self, caps=None, rol_activo=None):
        """caps: lista de strings de roles. Ej: ['picker', 'repartidor']"""
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import MagicMock, PropertyMock, patch
        gestor = GestorEmpleado()

        # mocks de EmpleadoCapacidad
        cap_mocks = []
        for r in (caps or []):
            m = MagicMock()
            m.rol = r
            cap_mocks.append(m)

        empleado_mock = MagicMock()
        empleado_mock.capacidades = cap_mocks
        empleado_mock.rol_activo = rol_activo

        session_mock = MagicMock()
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        return gestor, session_mock, empleado_mock

    def test_capacidades_devuelve_lista(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, _ = self._make_gestor(caps=['picker', 'repartidor'])
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.capacidades(5)
        assert set(result) == {'picker', 'repartidor'}

    def test_capacidades_un_rol(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, _ = self._make_gestor(caps=['picker'])
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.capacidades(1)
        assert result == ['picker']

    def test_es_polivalente_true(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, _ = self._make_gestor(caps=['picker', 'repartidor'])
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            assert gestor.es_polivalente(5) is True

    def test_es_polivalente_false(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, _ = self._make_gestor(caps=['picker'])
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            assert gestor.es_polivalente(1) is False

    def test_tiene_rol_activo_true(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, _ = self._make_gestor(rol_activo='picker')
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            assert gestor.tiene_rol_activo(1) is True

    def test_tiene_rol_activo_false_cuando_none(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, _ = self._make_gestor(rol_activo=None)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            assert gestor.tiene_rol_activo(1) is False
```

- [ ] **Step 2: Ejecutar para verificar que fallan**

```bash
pytest tests/test_empleado.py::TestGestorEmpleadoCapacidades -v
```

Resultado esperado: todos FAILED (métodos no existen aún)

- [ ] **Step 3: Implementar `capacidades`, `es_polivalente`, `tiene_rol_activo` en `managers/gestor_empleado.py`**

Añadir dentro de la clase `GestorEmpleado`, después de `turno_hoy`:

```python
    def capacidades(self, empleado_id: int) -> list[str]:
        """Roles que puede desempeñar el empleado. Ej: ['picker', 'repartidor']"""
        empleado = self.session.query(Empleado).filter_by(
            EmpleadoID=empleado_id, activo=True
        ).first()
        if not empleado:
            return []
        return [c.rol for c in empleado.capacidades]

    def es_polivalente(self, empleado_id: int) -> bool:
        """True si el empleado tiene más de una capacidad operativa."""
        return len(self.capacidades(empleado_id)) > 1

    def tiene_rol_activo(self, empleado_id: int) -> bool:
        """True si empleado.rol_activo no es NULL en BD."""
        empleado = self.session.query(Empleado).filter_by(
            EmpleadoID=empleado_id, activo=True
        ).first()
        return bool(empleado and empleado.rol_activo)
```

También actualizar el import al principio del archivo — añadir `EmpleadoCapacidad` si no está (en realidad no hace falta importarla directamente porque se accede via relación, pero sí hay que asegurarse de que `Empleado` está importado, ya lo está).

- [ ] **Step 4: Ejecutar para verificar que pasan**

```bash
pytest tests/test_empleado.py::TestGestorEmpleadoCapacidades -v
```

Resultado esperado: todos PASSED

- [ ] **Step 5: Escribir tests para `cambiar_rol`**

Añadir a `tests/test_empleado.py`:

```python
class TestGestorEmpleadoCambiarRol:
    """cambiar_rol: bloqueo, éxito, capacidad inválida."""

    def _make_gestor_cambio(self, caps, rol_activo, pickings_activos=0, repartos_activos=0, estado_op='disponible'):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import MagicMock, PropertyMock, patch

        gestor = GestorEmpleado()

        cap_mocks = []
        for r in caps:
            m = MagicMock(); m.rol = r
            cap_mocks.append(m)

        empleado_mock = MagicMock()
        empleado_mock.capacidades = cap_mocks
        empleado_mock.rol_activo = rol_activo
        empleado_mock.EmpleadoID = 1
        empleado_mock.estado_operativo = estado_op

        # Simular pickings activos
        picking_list = [MagicMock() for _ in range(pickings_activos)]
        for p in picking_list:
            p.id = 100; p.estado = 'en_proceso'

        # Simular repartos activos
        reparto_list = [MagicMock() for _ in range(repartos_activos)]
        for r in reparto_list:
            r.id = 200; r.estado = 'en_camino'

        session_mock = MagicMock()

        def query_side_effect(model):
            from models import Empleado, PickingPedido, Reparto
            q = MagicMock()
            if model is Empleado:
                q.filter_by.return_value.first.return_value = empleado_mock
            elif model is PickingPedido:
                q.filter.return_value.all.return_value = picking_list
            elif model is Reparto:
                q.filter.return_value.all.return_value = reparto_list
            return q

        session_mock.query.side_effect = query_side_effect
        return gestor, session_mock, empleado_mock

    def test_cambia_rol_exitoso(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, empleado_mock = self._make_gestor_cambio(
            caps=['picker', 'repartidor'], rol_activo='picker'
        )
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg, bloqueantes = gestor.cambiar_rol(1, 'repartidor')
        assert ok is True
        assert empleado_mock.rol_activo == 'repartidor'

    def test_bloquea_si_hay_picking_activo(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, empleado_mock = self._make_gestor_cambio(
            caps=['picker', 'repartidor'], rol_activo='picker', pickings_activos=1
        )
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg, bloqueantes = gestor.cambiar_rol(1, 'repartidor')
        assert ok is False
        assert len(bloqueantes) > 0

    def test_rechaza_rol_sin_capacidad(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, empleado_mock = self._make_gestor_cambio(
            caps=['picker'], rol_activo='picker'
        )
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, msg, bloqueantes = gestor.cambiar_rol(1, 'repartidor')
        assert ok is False
        assert bloqueantes == []

    def test_setea_disponible_si_venia_de_desconectado(self):
        from managers.gestor_empleado import GestorEmpleado
        from unittest.mock import PropertyMock, patch
        gestor, session_mock, empleado_mock = self._make_gestor_cambio(
            caps=['picker', 'repartidor'], rol_activo=None, estado_op='desconectado'
        )
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            ok, _, _ = gestor.cambiar_rol(1, 'picker')
        assert ok is True
        assert empleado_mock.estado_operativo == 'disponible'
```

- [ ] **Step 6: Ejecutar para verificar que fallan**

```bash
pytest tests/test_empleado.py::TestGestorEmpleadoCambiarRol -v
```

Resultado esperado: todos FAILED

- [ ] **Step 7: Implementar `cambiar_rol` en `managers/gestor_empleado.py`**

Añadir a la clase `GestorEmpleado`, después de `tiene_rol_activo`. Necesita importar `EmpleadoCapacidad`, `PickingPedido`, `Reparto`, `AuditLog`, `json`, `SQLAlchemyError`:

```python
    def cambiar_rol(self, empleado_id: int, nuevo_rol: str) -> tuple[bool, str, list]:
        """
        Intenta cambiar el rol activo del empleado.
        Returns: (ok, mensaje, pedidos_bloqueantes)
        pedidos_bloqueantes: lista de dicts {id, tipo, estado} si hay bloqueo
        """
        import json as _json
        from models import EmpleadoCapacidad, PickingPedido, Reparto, AuditLog
        from states import EstadoPicking, EstadoReparto
        s = self.session

        empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id, activo=True).first()
        if not empleado:
            return False, 'Empleado no encontrado', []

        caps = [c.rol for c in empleado.capacidades]
        if nuevo_rol not in caps:
            return False, f"El empleado no tiene la capacidad '{nuevo_rol}'", []

        rol_anterior = empleado.rol_activo or ''

        # Verificar tareas activas con el rol actual
        bloqueantes = []
        if rol_anterior == 'picker':
            activos = s.query(PickingPedido).filter(
                PickingPedido.empleado_id == empleado_id,
                PickingPedido.estado == EstadoPicking.EN_PROCESO.value,
            ).all()
            bloqueantes = [{'id': p.id, 'tipo': 'picking', 'estado': p.estado} for p in activos]
        elif rol_anterior == 'repartidor':
            activos = s.query(Reparto).filter(
                Reparto.repartidor_id == empleado_id,
                Reparto.estado.in_([EstadoReparto.ASIGNADO.value, EstadoReparto.EN_CAMINO.value]),
            ).all()
            bloqueantes = [{'id': r.id, 'tipo': 'reparto', 'estado': r.estado} for r in activos]

        if bloqueantes:
            try:
                s.add(AuditLog(
                    pedido_id=None, empleado_id=empleado_id,
                    accion='cambio_rol_bloqueado',
                    detalles=_json.dumps({'rol_destino': nuevo_rol, 'pedidos_activos': bloqueantes}),
                ))
                s.commit()
            except SQLAlchemyError:
                s.rollback()
            return False, f'Tienes tareas activas como {rol_anterior}', bloqueantes

        try:
            empleado.rol_activo = nuevo_rol
            if empleado.estado_operativo in ('desconectado', 'en_pausa'):
                empleado.estado_operativo = 'disponible'
            s.add(AuditLog(
                pedido_id=None, empleado_id=empleado_id,
                accion='cambio_rol',
                detalles=_json.dumps({'de': rol_anterior, 'a': nuevo_rol}),
            ))
            s.commit()
            logger.info("CAMBIO_ROL empleado_id=%s de=%s a=%s", empleado_id, rol_anterior, nuevo_rol)
            return True, f"Rol cambiado a '{nuevo_rol}'", []
        except SQLAlchemyError as e:
            s.rollback()
            logger.error("Error cambiando rol empleado %s: %s", empleado_id, e)
            return False, 'Error de base de datos', []
```

Asegurarse de que `SQLAlchemyError` está importado al principio del archivo (ya lo está) y añadir al bloque de imports del módulo si falta:

```python
from sqlalchemy.exc import SQLAlchemyError
```

- [ ] **Step 8: Implementar `carga_operativa` en `managers/gestor_empleado.py`**

```python
    def carga_operativa(self) -> dict:
        """Nº de pedidos en cada cola para la pantalla de check-in."""
        from models import PickingPedido, Reparto
        from states import EstadoPicking, EstadoReparto
        from sqlalchemy import func
        s = self.session
        try:
            pickings_pendientes = s.query(func.count(PickingPedido.id)).filter(
                PickingPedido.estado == EstadoPicking.PENDIENTE.value
            ).scalar() or 0
            pickings_en_proceso = s.query(func.count(PickingPedido.id)).filter(
                PickingPedido.estado == EstadoPicking.EN_PROCESO.value
            ).scalar() or 0
            repartos_listos = s.query(func.count(Reparto.id)).filter(
                Reparto.estado == EstadoReparto.PENDIENTE.value
            ).scalar() or 0
            repartos_en_camino = s.query(func.count(Reparto.id)).filter(
                Reparto.estado == EstadoReparto.EN_CAMINO.value
            ).scalar() or 0
            return {
                'picker':      {'pendientes': pickings_pendientes, 'en_proceso': pickings_en_proceso},
                'repartidor':  {'listos_para_entregar': repartos_listos, 'en_camino': repartos_en_camino},
            }
        except SQLAlchemyError:
            return {'picker': {'pendientes': 0, 'en_proceso': 0},
                    'repartidor': {'listos_para_entregar': 0, 'en_camino': 0}}
```

- [ ] **Step 9: Ejecutar tests de cambiar_rol**

```bash
pytest tests/test_empleado.py::TestGestorEmpleadoCambiarRol -v
```

Resultado esperado: todos PASSED

- [ ] **Step 10: Ejecutar suite completa**

```bash
pytest -v --tb=short
```

Resultado esperado: todos los tests previos siguen pasando.

- [ ] **Step 11: Commit**

```bash
git add managers/gestor_empleado.py tests/test_empleado.py
git commit -m "feat: add capacidades/es_polivalente/tiene_rol_activo/cambiar_rol/carga_operativa to GestorEmpleado"
```

---

## Task 3: Auth — login actualizado + requiere_autenticacion + logout

**Files:**
- Modify: `blueprints/auth.py`
- Modify: `tests/test_empleado.py`

- [ ] **Step 1: Escribir tests para el login con polivalente**

Añadir a `tests/test_empleado.py`:

```python
class TestAuthPolivalente:
    """Login con empleado polivalente redirige a /empleado/checkin."""

    def _empleado_polivalente(self, rol_activo=None):
        from unittest.mock import MagicMock
        from werkzeug.security import generate_password_hash
        emp = MagicMock()
        emp.EmpleadoID = 10
        emp.Nombre = 'Ana'
        emp.password_hash = generate_password_hash('secret')
        emp.rol = MagicMock(); emp.rol.nombre = 'picker'
        emp.rol_activo = rol_activo

        cap1 = MagicMock(); cap1.rol = 'picker'
        cap2 = MagicMock(); cap2.rol = 'repartidor'
        emp.capacidades = [cap1, cap2]
        return emp

    def test_polivalente_sin_rol_activo_va_a_checkin(self, client, app):
        with app.app_context():
            with patch('blueprints.auth._get_empleado_by_email',
                       return_value=self._empleado_polivalente(rol_activo=None)):
                resp = client.post('/auth/login',
                                   json={'email': 'ana@test.com', 'password': 'secret'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['redirect'] == '/empleado/checkin'

    def test_polivalente_con_rol_activo_va_a_empleado(self, client, app):
        with app.app_context():
            with patch('blueprints.auth._get_empleado_by_email',
                       return_value=self._empleado_polivalente(rol_activo='picker')):
                resp = client.post('/auth/login',
                                   json={'email': 'ana@test.com', 'password': 'secret'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['redirect'] == '/empleado'

    def test_monorol_sigue_funcionando(self, client, app):
        """Empleado con un solo rol va directo a /empleado sin cambios."""
        from werkzeug.security import generate_password_hash
        emp = MagicMock()
        emp.EmpleadoID = 5; emp.Nombre = 'Carlos'
        emp.password_hash = generate_password_hash('secret')
        emp.rol = MagicMock(); emp.rol.nombre = 'picker'
        emp.rol_activo = None
        cap = MagicMock(); cap.rol = 'picker'
        emp.capacidades = [cap]

        with app.app_context():
            with patch('blueprints.auth._get_empleado_by_email', return_value=emp):
                resp = client.post('/auth/login',
                                   json={'email': 'carlos@test.com', 'password': 'secret'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['redirect'] == '/empleado'
```

Añadir `from unittest.mock import patch, MagicMock` al inicio de `test_empleado.py` si aún no están (ya están como imports locales en algunos tests — moverlos al top para limpieza):

El archivo ya los importa localmente. Dejarlo como está para no refactorizar.

- [ ] **Step 2: Ejecutar para verificar que fallan**

```bash
pytest tests/test_empleado.py::TestAuthPolivalente -v
```

Resultado esperado: FAILED (login sigue usando rol.nombre fijo, no lee capacidades)

- [ ] **Step 3: Actualizar el login en `blueprints/auth.py`**

En `blueprints/auth.py`, reemplazar el bloque donde se setea la sesión tras la verificación de contraseña (líneas ~53-69):

```python
    # Leer capacidades operativas del empleado
    capacidades = [c.rol for c in empleado.capacidades] if hasattr(empleado, 'capacidades') else []

    # Determinar session['rol']
    if not capacidades:
        # Manager/admin o empleado sin capacidades asignadas — usar rol_id como antes
        rol_nombre = empleado.rol.nombre if empleado.rol else None
    elif len(capacidades) == 1:
        rol_nombre = capacidades[0]
    elif empleado.rol_activo and empleado.rol_activo in capacidades:
        rol_nombre = empleado.rol_activo  # restaurar último usado
    else:
        rol_nombre = capacidades[0]  # primer rol disponible; redirigir a checkin

    session.clear()
    session['empleado_id'] = empleado.EmpleadoID
    session['empleado_nombre'] = empleado.Nombre
    session['rol'] = rol_nombre
    session.permanent = True

    logger.info("AUTH_OK empleado_id=%s rol=%s", empleado.EmpleadoID, rol_nombre)

    destinos = {
        'manager':    '/dashboard',
        'admin':      '/dashboard',
        'picker':     '/empleado',
        'repartidor': '/empleado',
    }
    destino = destinos.get(rol_nombre, '/empleado')

    # Polivalente sin rol_activo previo → check-in
    if len(capacidades) > 1 and not empleado.rol_activo:
        destino = '/empleado/checkin'
```

- [ ] **Step 4: Añadir `requiere_autenticacion` al final de `blueprints/auth.py`**

```python
def requiere_autenticacion(f):
    """Decorator que solo verifica que hay sesión activa, sin chequear rol.
    Usar en rutas como /empleado/checkin donde el empleado puede tener
    rol temporal o estar en proceso de selección.
    """
    from functools import wraps
    @wraps(f)
    def wrapped(*args, **kwargs):
        if 'empleado_id' not in session:
            if request.method == 'GET' and not request.is_json:
                return redirect(url_for('auth.login'))
            return jsonify({'error': 'No autenticado'}), 401
        return f(*args, **kwargs)
    return wrapped
```

- [ ] **Step 5: Actualizar `logout` para nular `rol_activo` en BD**

En `blueprints/auth.py`, en la función `logout`:

```python
@blueprint_auth.route('/auth/logout', methods=['POST'])
def logout():
    empleado_id = session.get('empleado_id')
    # Nular rol_activo en BD para forzar check-in en el próximo turno
    if empleado_id:
        try:
            from database import get_db
            from models import Empleado as _Empleado
            emp = get_db().query(_Empleado).filter_by(EmpleadoID=empleado_id).first()
            if emp:
                emp.rol_activo = None
                get_db().commit()
        except Exception:
            pass  # No bloquear el logout por un error de BD
    session.clear()
    logger.info("AUTH_LOGOUT empleado_id=%s", empleado_id)
    return redirect(url_for('auth.login'))
```

- [ ] **Step 6: Ejecutar tests de auth polivalente**

```bash
pytest tests/test_empleado.py::TestAuthPolivalente -v
```

Resultado esperado: todos PASSED

- [ ] **Step 7: Verificar que los tests de auth existentes siguen pasando**

```bash
pytest tests/test_empleado.py::TestAuthRedireccionEmpleado -v
pytest tests/test_empleado.py::TestBlueprintEmpleadoAuth -v
```

Resultado esperado: todos PASSED

- [ ] **Step 8: Suite completa**

```bash
pytest -v --tb=short
```

- [ ] **Step 9: Commit**

```bash
git add blueprints/auth.py tests/test_empleado.py
git commit -m "feat: update login for multi-role employees, add requiere_autenticacion, null rol_activo on logout"
```

---

## Task 4: Blueprint empleado — redirect en hub + 4 endpoints nuevos

**Files:**
- Modify: `blueprints/empleado.py`
- Modify: `tests/test_empleado.py`

- [ ] **Step 1: Escribir tests para los nuevos endpoints**

Añadir a `tests/test_empleado.py`:

```python
class TestBlueprintEmpleadoNuevos:
    """Nuevos endpoints: /empleado/capacidades, /empleado/carga-operativa, /empleado/cambiar-rol, /empleado/checkin."""

    def _set_session(self, client, rol='picker'):
        with client.session_transaction() as sess:
            sess['empleado_id'] = 1
            sess['rol'] = rol

    def test_capacidades_sin_sesion_rechazado(self, client):
        resp = client.get('/empleado/capacidades')
        assert resp.status_code in (302, 401)

    def test_capacidades_con_sesion_devuelve_json(self, client, app):
        self._set_session(client)
        with app.app_context():
            from services import gestor_empleado
            with patch.object(gestor_empleado, 'capacidades', return_value=['picker']), \
                 patch.object(gestor_empleado, 'tiene_rol_activo', return_value=True):
                # acceder a perfil para obtener rol_activo — mocked via perfil
                emp_mock = MagicMock(); emp_mock.rol_activo = 'picker'
                with patch('blueprints.empleado.gestor_empleado') as ge_mock:
                    ge_mock.capacidades.return_value = ['picker']
                    # Necesitamos que el endpoint lea rol_activo del empleado
                    # El endpoint llama a gestor_empleado.capacidades y también necesita rol_activo
                    # Lo manejamos via mock directo
                    resp = client.get('/empleado/capacidades')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'capacidades' in data

    def test_carga_operativa_devuelve_estructura(self, client, app):
        self._set_session(client)
        with app.app_context():
            from services import gestor_empleado
            mock_carga = {
                'picker': {'pendientes': 3, 'en_proceso': 1},
                'repartidor': {'listos_para_entregar': 2, 'en_camino': 0},
            }
            with patch.object(gestor_empleado, 'carga_operativa', return_value=mock_carga):
                resp = client.get('/empleado/carga-operativa')
        assert resp.status_code == 200
        data = resp.get_json()
        assert 'picker' in data
        assert 'repartidor' in data

    def test_cambiar_rol_sin_sesion_rechazado(self, client):
        resp = client.post('/empleado/cambiar-rol', json={'rol': 'picker'})
        assert resp.status_code in (302, 401)

    def test_cambiar_rol_exitoso(self, client, app):
        self._set_session(client, rol='picker')
        with app.app_context():
            from services import gestor_empleado
            with patch.object(gestor_empleado, 'cambiar_rol', return_value=(True, 'ok', [])):
                resp = client.post('/empleado/cambiar-rol',
                                   json={'rol': 'repartidor'},
                                   content_type='application/json')
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True

    def test_cambiar_rol_bloqueado_devuelve_409(self, client, app):
        self._set_session(client, rol='picker')
        with app.app_context():
            from services import gestor_empleado
            bloqueantes = [{'id': 1, 'tipo': 'picking', 'estado': 'en_proceso'}]
            with patch.object(gestor_empleado, 'cambiar_rol',
                               return_value=(False, 'Tienes tareas activas', bloqueantes)):
                resp = client.post('/empleado/cambiar-rol',
                                   json={'rol': 'repartidor'},
                                   content_type='application/json')
        assert resp.status_code == 409
        data = resp.get_json()
        assert 'pedidos_activos' in data

    def test_checkin_sin_sesion_redirige(self, client):
        resp = client.get('/empleado/checkin')
        assert resp.status_code in (302, 401)

    def test_checkin_con_sesion_ok(self, client, app):
        self._set_session(client)
        with app.app_context():
            from services import gestor_empleado
            mock_carga = {'picker': {'pendientes': 0, 'en_proceso': 0},
                          'repartidor': {'listos_para_entregar': 0, 'en_camino': 0}}
            with patch.object(gestor_empleado, 'capacidades', return_value=['picker', 'repartidor']), \
                 patch.object(gestor_empleado, 'carga_operativa', return_value=mock_carga), \
                 patch.object(gestor_empleado, 'turno_hoy', return_value=None):
                resp = client.get('/empleado/checkin')
        assert resp.status_code == 200
```

Nota: el test `test_capacidades_con_sesion_devuelve_json` tiene un mock un poco redundante — la implementación real simplificará esto. Lo importante es que 200 y `capacidades` en el JSON.

- [ ] **Step 2: Ejecutar para verificar que fallan**

```bash
pytest tests/test_empleado.py::TestBlueprintEmpleadoNuevos -v
```

Resultado esperado: FAILED (endpoints no existen aún)

- [ ] **Step 3: Actualizar `blueprints/empleado.py` — ruta index con redirect a checkin**

En `blueprints/empleado.py`, actualizar el import y la función `index`:

```python
from flask import Blueprint, jsonify, redirect, render_template, request, session
from blueprints.auth import requiere_autenticacion, requiere_rol
from services import gestor_empleado

# ...

@blueprint_empleado.route('/empleado', strict_slashes=False)
@requiere_rol(*_ROLES_HUB)
def index():
    empleado_id = session.get('empleado_id')
    rol = session.get('rol')
    # Redirigir a check-in si polivalente y sin rol_activo en BD
    try:
        if gestor_empleado.es_polivalente(empleado_id) and not gestor_empleado.tiene_rol_activo(empleado_id):
            return redirect('/empleado/checkin')
    except Exception:
        pass  # Si falla la BD, mostrar el hub igualmente
    return render_template('empleado/index.html', empleado_id=empleado_id, rol=rol)
```

- [ ] **Step 4: Añadir los 4 endpoints nuevos a `blueprints/empleado.py`**

```python
@blueprint_empleado.route('/empleado/capacidades')
@requiere_rol(*_ROLES_HUB)
def capacidades():
    empleado_id = session.get('empleado_id')
    try:
        from database import get_db
        from models import Empleado as _Empleado
        caps = gestor_empleado.capacidades(empleado_id)
        emp = get_db().query(_Empleado).filter_by(EmpleadoID=empleado_id).first()
        rol_activo = emp.rol_activo if emp else None
        return jsonify({'capacidades': caps, 'rol_activo': rol_activo})
    except Exception as e:
        logger.error("Error en /empleado/capacidades: %s", e)
        return jsonify({'capacidades': [], 'rol_activo': None})


@blueprint_empleado.route('/empleado/carga-operativa')
@requiere_rol(*_ROLES_HUB)
def carga_operativa():
    try:
        return jsonify(gestor_empleado.carga_operativa())
    except Exception as e:
        logger.error("Error en /empleado/carga-operativa: %s", e)
        return jsonify({'picker': {'pendientes': 0, 'en_proceso': 0},
                        'repartidor': {'listos_para_entregar': 0, 'en_camino': 0}})


@blueprint_empleado.route('/empleado/cambiar-rol', methods=['POST'])
@requiere_rol(*_ROLES_HUB)
def cambiar_rol():
    data = request.get_json(silent=True) or {}
    nuevo_rol = (data.get('rol') or '').strip()
    if not nuevo_rol:
        return jsonify({'error': 'Falta campo: rol'}), 400

    empleado_id = session.get('empleado_id')
    ok, msg, bloqueantes = gestor_empleado.cambiar_rol(empleado_id, nuevo_rol)

    if not ok:
        if bloqueantes:
            return jsonify({'error': msg, 'pedidos_activos': bloqueantes}), 409
        return jsonify({'error': msg}), 403

    session['rol'] = nuevo_rol
    return jsonify({'ok': True, 'rol': nuevo_rol})


@blueprint_empleado.route('/empleado/checkin')
@requiere_autenticacion
def checkin():
    empleado_id = session.get('empleado_id')
    try:
        caps = gestor_empleado.capacidades(empleado_id)
        # Si tiene exactamente 1 capacidad, no necesita elegir
        if len(caps) == 1:
            return redirect('/empleado')
        carga = gestor_empleado.carga_operativa()
        turno = gestor_empleado.turno_hoy(empleado_id)
        return render_template('empleado/checkin.html',
                                capacidades=caps,
                                carga=carga,
                                turno=turno,
                                empleado_id=empleado_id)
    except Exception as e:
        logger.error("Error en /empleado/checkin: %s", e)
        return redirect('/empleado')
```

- [ ] **Step 5: Ejecutar los tests nuevos**

```bash
pytest tests/test_empleado.py::TestBlueprintEmpleadoNuevos -v
```

Resultado esperado: casi todos PASSED (el de checkin puede fallar si el template no existe aún — es esperado)

- [ ] **Step 6: Suite completa**

```bash
pytest -v --tb=short
```

- [ ] **Step 7: Commit**

```bash
git add blueprints/empleado.py tests/test_empleado.py
git commit -m "feat: add /empleado/checkin, /empleado/cambiar-rol, /empleado/capacidades, /empleado/carga-operativa endpoints"
```

---

## Task 5: Template checkin.html

**Files:**
- Create: `templates/empleado/checkin.html`
- Modify: `tests/test_empleado.py` (smoke test)

- [ ] **Step 1: Escribir smoke test para el template**

Ya incluido en `TestBlueprintEmpleadoNuevos::test_checkin_con_sesion_ok`. Verificar que ese test pasa una vez creado el template.

- [ ] **Step 2: Crear `templates/empleado/checkin.html`**

```html
<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0" />
  <title>Panchi — ¿Cómo entras hoy?</title>
  <meta name="theme-color" content="#111827">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <style>[x-cloak] { display: none !important; } button { -webkit-tap-highlight-color: transparent; }</style>
</head>
<body class="bg-gray-900 min-h-screen"
      x-data="checkinHub({{ empleado_id or 'null' }})"
      x-init="init()">

  <!-- HEADER -->
  <header class="bg-gray-900 border-b border-gray-800 px-4 py-3 sticky top-0 z-30">
    <p class="text-xs text-gray-500" x-text="fechaHoy"></p>
    <p class="text-white font-bold text-base leading-tight" x-text="saludo"></p>
  </header>

  <main class="max-w-md mx-auto px-4 py-6 space-y-4">

    <!-- Turno del día -->
    <template x-if="turno">
      <div class="bg-blue-950 rounded-xl p-3 border border-blue-900">
        <p class="text-xs text-blue-300 uppercase tracking-wide">Turno hoy</p>
        <p class="text-white font-semibold text-sm mt-1"
           x-text="turno.hora_inicio + ' – ' + turno.hora_fin"></p>
      </div>
    </template>

    <!-- Título -->
    <div class="text-center py-2">
      <p class="text-white font-bold text-xl">¿Cómo entras hoy?</p>
      <p class="text-gray-500 text-sm mt-1">Elige tu rol para este turno</p>
    </div>

    <!-- Cards de rol -->
    <div class="grid grid-cols-2 gap-3">

      <!-- Picker -->
      <button @click="seleccionarRol('picker')"
              :disabled="cargando"
              class="bg-gradient-to-br from-blue-900 to-blue-700 rounded-2xl p-5 text-center
                     active:opacity-90 transition border-2 border-transparent
                     hover:border-blue-400 disabled:opacity-50">
        <p class="text-4xl">🛒</p>
        <p class="text-white font-bold text-base mt-3">Picker</p>
        <div class="mt-3 bg-black/30 rounded-lg px-2 py-1.5">
          <p class="text-blue-300 font-semibold text-sm"
             x-text="(carga.picker?.pendientes ?? '—') + ' pedidos'"></p>
          <p class="text-gray-400 text-xs mt-0.5">esperando prep.</p>
        </div>
      </button>

      <!-- Repartidor -->
      <button @click="seleccionarRol('repartidor')"
              :disabled="cargando"
              class="bg-gradient-to-br from-orange-900 to-orange-700 rounded-2xl p-5 text-center
                     active:opacity-90 transition border-2 border-transparent
                     hover:border-orange-400 disabled:opacity-50">
        <p class="text-4xl">🛵</p>
        <p class="text-white font-bold text-base mt-3">Repartidor</p>
        <div class="mt-3 bg-black/30 rounded-lg px-2 py-1.5">
          <p class="text-orange-300 font-semibold text-sm"
             x-text="(carga.repartidor?.listos_para_entregar ?? '—') + ' listos'"></p>
          <p class="text-gray-400 text-xs mt-0.5">para entregar</p>
        </div>
      </button>

    </div>

    <!-- Loading state -->
    <div x-show="cargando" x-cloak class="text-center py-4">
      <p class="text-gray-400 text-sm">Entrando...</p>
    </div>

    <!-- Error -->
    <div x-show="error" x-cloak class="bg-red-950 border border-red-800 rounded-xl p-3 text-center">
      <p class="text-red-400 text-sm" x-text="error"></p>
    </div>

    <p class="text-center text-gray-600 text-xs pt-2">Podrás cambiarlo más tarde si hace falta</p>

  </main>

  <script>
  function checkinHub(empleadoId) {
    return {
      empleadoId,
      carga: { picker: {}, repartidor: {} },
      turno: null,
      cargando: false,
      error: '',

      get saludo() {
        const h = new Date().getHours();
        if (h < 13) return 'Buenos días ☀️';
        if (h < 20) return 'Buenas tardes 🌤️';
        return 'Buenas noches 🌙';
      },
      get fechaHoy() {
        return new Date().toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' });
      },

      async init() {
        await Promise.all([this.cargarCarga(), this.cargarTurno()]);
      },

      async cargarCarga() {
        try {
          const r = await fetch('/empleado/carga-operativa');
          if (r.ok) this.carga = await r.json();
        } catch (_) {}
      },

      async cargarTurno() {
        try {
          const r = await fetch('/empleado/turno-hoy');
          if (r.ok) this.turno = await r.json();
        } catch (_) {}
      },

      async seleccionarRol(rol) {
        if (this.cargando) return;
        this.cargando = true;
        this.error = '';
        try {
          const r = await fetch('/empleado/cambiar-rol', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rol }),
          });
          if (r.ok) {
            sessionStorage.setItem('checkin_date', new Date().toDateString());
            window.location.href = '/empleado';
          } else {
            const d = await r.json();
            this.error = d.error || 'Error al cambiar rol';
            this.cargando = false;
          }
        } catch (_) {
          this.error = 'Error de conexión. Inténtalo de nuevo.';
          this.cargando = false;
        }
      },
    };
  }
  </script>

</body>
</html>
```

- [ ] **Step 3: Ejecutar smoke test del checkin**

```bash
pytest tests/test_empleado.py::TestBlueprintEmpleadoNuevos::test_checkin_con_sesion_ok -v
```

Resultado esperado: PASSED

- [ ] **Step 4: Suite completa**

```bash
pytest -v --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add templates/empleado/checkin.html
git commit -m "feat: add /empleado/checkin template with role selection and operational load"
```

---

## Task 6: Hub actualizado — capacidades + cambiar rol + modal de bloqueo

**Files:**
- Modify: `templates/empleado/index.html`

- [ ] **Step 1: Actualizar el Alpine component en `templates/empleado/index.html`**

Localizar el bloque `<script>` con `function empleadoHub(...)` y hacer los siguientes cambios:

**a) Añadir `capacidades: []` a las propiedades del componente** (después de `pedidosAsignados: 0`):

```javascript
      capacidades:     [],
      mostrarModalBloqueo: false,
      pedidosBloqueantes:  [],
```

**b) Añadir computed `rolOpuesto`** (después de `get metricaLabel3()`):

```javascript
      get rolOpuesto() {
        // Asume exactamente 2 capacidades (picker/repartidor)
        // Si en el futuro hay más roles, reemplazar por un selector
        return this.rol === 'picker' ? 'Repartidor' : 'Picker';
      },
      get rolOpuestoSlug() {
        return this.rol === 'picker' ? 'repartidor' : 'picker';
      },
```

**c) Añadir llamada a `cargarCapacidades()` en `init()`**:

```javascript
      async init() {
        await Promise.all([
          this.cargarPerfil(),
          this.cargarTurno(),
          this.cargarMetricas(),
          this.cargarCapacidades(),
        ]);
      },
```

**d) Añadir método `cargarCapacidades`** (después de `cargarMetricas`):

```javascript
      async cargarCapacidades() {
        try {
          const r = await fetch('/empleado/capacidades');
          if (r.ok) {
            const d = await r.json();
            this.capacidades = d.capacidades || [];
          }
        } catch (_) {}
      },
```

**e) Añadir método `cambiarRol`**:

```javascript
      async cambiarRol() {
        const nuevoRol = this.rolOpuestoSlug;
        try {
          const r = await fetch('/empleado/cambiar-rol', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rol: nuevoRol }),
          });
          if (r.ok) {
            window.location.reload();
          } else if (r.status === 409) {
            const d = await r.json();
            this.pedidosBloqueantes = d.pedidos_activos || [];
            this.mostrarModalBloqueo = true;
          } else {
            const d = await r.json();
            alert(d.error || 'Error al cambiar rol');
          }
        } catch (_) {
          alert('Error de conexión');
        }
      },
```

- [ ] **Step 2: Añadir el botón "⇄ Cambiar rol" dentro del CTA en `templates/empleado/index.html`**

Localizar el bloque `<a :href="appUrl" ...>` (el CTA principal, líneas ~91-103). Justo antes del `</a>` de cierre, añadir:

```html
    <!-- Cambiar rol — solo visible si polivalente -->
    <template x-if="capacidades.length > 1">
      <div class="border-t border-white/10 mt-3 pt-3 text-center">
        <button @click.prevent="cambiarRol()"
                class="text-xs active:opacity-70 transition"
                :class="rol === 'repartidor' ? 'text-orange-200' : 'text-blue-200'">
          ⇄ Cambiar a <span x-text="rolOpuesto"></span>
          <!-- rolOpuesto asume exactamente 2 capacidades (picker/repartidor) -->
        </button>
      </div>
    </template>
```

Nota: el CTA es `<a>`, no `<button>`, así que hay que cambiar la estructura para que el botón interno no siga el href. Usar `@click.prevent` en el botón interno resuelve esto.

- [ ] **Step 3: Añadir el modal de bloqueo al final de `<main>`, antes del cierre `</main>`**

```html
    <!-- Modal bloqueo de cambio de rol -->
    <div x-show="mostrarModalBloqueo" x-cloak
         class="fixed inset-0 bg-black/70 z-50 flex items-end justify-center p-4">
      <div class="bg-gray-900 rounded-2xl w-full max-w-md p-5 border border-red-900">
        <p class="text-red-400 font-bold text-sm mb-2">🔒 No puedes cambiar de rol ahora</p>
        <p class="text-gray-400 text-xs mb-3">
          Tienes tareas activas. Termínalas primero:
        </p>
        <div class="space-y-2 mb-4">
          <template x-for="p in pedidosBloqueantes" :key="p.id">
            <div class="bg-gray-800 rounded-lg px-3 py-2 flex justify-between">
              <span class="text-sm text-red-300 font-medium" x-text="p.tipo + ' #' + p.id"></span>
              <span class="text-xs text-gray-500" x-text="p.estado"></span>
            </div>
          </template>
        </div>
        <div class="grid grid-cols-2 gap-2">
          <a :href="appUrl"
             class="bg-blue-700 text-white text-sm font-semibold rounded-xl py-2.5 text-center active:opacity-90">
            Ir a terminarlos
          </a>
          <button @click="mostrarModalBloqueo = false"
                  class="bg-gray-700 text-gray-300 text-sm rounded-xl py-2.5 active:bg-gray-600">
            Cancelar
          </button>
        </div>
        <p class="text-center text-gray-600 text-xs mt-3">El manager puede transferir los pedidos desde el dashboard</p>
      </div>
    </div>
```

- [ ] **Step 4: Verificar render sin errores**

```bash
pytest tests/test_empleado.py::TestBlueprintEmpleadoAuth::test_con_sesion_picker_ok -v
```

Resultado esperado: PASSED (el hub renderiza sin 500)

- [ ] **Step 5: Suite completa**

```bash
pytest -v --tb=short
```

- [ ] **Step 6: Commit**

```bash
git add templates/empleado/index.html
git commit -m "feat: update empleado hub with role switcher, capacidades load, and blocked-role modal"
```

---

## Task 7: Script de migración de datos

**Files:**
- Create: `scripts/migrate_capacidades.py`

> Este script se ejecuta una sola vez al desplegar. No hay tests automáticos (requiere BD real).

- [ ] **Step 1: Crear `scripts/migrate_capacidades.py`**

```python
"""
Migración: poblar empleado_capacidades desde rol_id actual.

Ejecutar UNA vez al desplegar:
    python scripts/migrate_capacidades.py

Hace:
1. Para cada empleado con rol picker/repartidor → añade una fila en empleado_capacidades
2. Para empleados conectados → pre-pobla rol_activo con su rol actual
3. Nada para manager/admin (no tienen capacidades operativas)

Es idempotente: verifica antes de insertar duplicados.
"""
import sys
import os

# Añadir el directorio raíz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from main import create_app
    from database import get_db
    from models import Empleado, EmpleadoCapacidad, Rol

    app = create_app()
    with app.app_context():
        db = get_db()

        empleados_op = (
            db.query(Empleado)
            .join(Rol)
            .filter(Rol.nombre.in_(['picker', 'repartidor']))
            .all()
        )

        creadas = 0
        actualizados = 0

        for emp in empleados_op:
            rol = emp.rol.nombre

            # Verificar si ya existe la capacidad
            existe = db.query(EmpleadoCapacidad).filter_by(
                empleado_id=emp.EmpleadoID, rol=rol
            ).first()

            if not existe:
                db.add(EmpleadoCapacidad(empleado_id=emp.EmpleadoID, rol=rol))
                creadas += 1
                print(f"  + {emp.Nombre} {emp.Apellido} → capacidad '{rol}'")

            # Pre-poblar rol_activo para empleados activos
            if emp.rol_activo is None and emp.estado_operativo != 'desconectado':
                emp.rol_activo = rol
                actualizados += 1
                print(f"  ~ {emp.Nombre} {emp.Apellido} → rol_activo='{rol}' (estaba activo)")

        db.commit()
        print(f"\nMigración completada: {creadas} capacidades creadas, {actualizados} rol_activo actualizados.")

        # También ejecutar el ALTER TABLE si es necesario
        # (solo si la columna aún no existe — SQLAlchemy create_all no añade columnas)
        print("\nNota: ejecutar manualmente en SQL Server si las columnas no existen:")
        print("  ALTER TABLE empleados ADD rol_activo VARCHAR(20) NULL;")
        print("  ALTER TABLE audit_log ALTER COLUMN pedido_id INT NULL;")
        print("  CREATE TABLE empleado_capacidades (id INT PRIMARY KEY IDENTITY(1,1), empleado_id INT NOT NULL REFERENCES empleados(EmpleadoID), rol VARCHAR(20) NOT NULL, UNIQUE(empleado_id, rol));")


if __name__ == '__main__':
    main()
```

- [ ] **Step 2: Verificar que el script se importa sin errores**

```bash
python -c "import scripts.migrate_capacidades; print('OK')"
```

Resultado esperado: `OK` (o error de BD — normal, no hay SQL Server en dev)

- [ ] **Step 3: Commit final**

```bash
git add scripts/migrate_capacidades.py
git commit -m "feat: add migration script for empleado_capacidades and rol_activo"
```

---

## Task 8: Verificación final

- [ ] **Step 1: Ejecutar suite completa**

```bash
pytest -v --tb=short
```

Resultado esperado: todos los tests previos pasan + los nuevos tests de empleado.

- [ ] **Step 2: Verificar que los tests conocidos de Monei siguen siendo los únicos fallos**

Los 3 tests en `TestWebhookMonei` son pre-existentes y conocidos — no cuentan.

- [ ] **Step 3: Commit de cierre (si hay cambios pendientes)**

```bash
git add -p  # revisar antes
git commit -m "chore: finalize dynamic roles MVP"
```

---

## Checklist de despliegue (manual)

Ejecutar en este orden en el servidor:

1. `ALTER TABLE empleados ADD rol_activo VARCHAR(20) NULL;`
2. `ALTER TABLE audit_log ALTER COLUMN pedido_id INT NULL;`
3. `CREATE TABLE empleado_capacidades (...);` (ver script)
4. `python scripts/migrate_capacidades.py`
5. Reiniciar la app Flask

---

## Notas para el implementador

- **`_ESTADOS_MANUALES`** en `gestor_empleado.py` solo acepta `en_pausa` y `desconectado`. En `cambiar_rol`, setear `estado_operativo = 'disponible'` **directamente en el ORM** (`empleado.estado_operativo = 'disponible'`), nunca llamar a `cambiar_estado()` para eso.
- **`EstadoPicking.EN_PROCESO`** — verificar en `states.py` el valor exacto del enum antes de usarlo en `cambiar_rol`.
- **El template `checkin.html`** solo muestra picker y repartidor. Si se añaden más roles en el futuro, generalizar el loop con `x-for`.
- **`requiere_autenticacion`** debe ser exportado desde `blueprints/auth.py` o accesible via import directo. Verificar que el import en `blueprints/empleado.py` lo recoge correctamente.
