# Refactor `gestor_dashboard.py` God Object — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Descomponer el god object `managers/gestor_dashboard.py` (121 KB, 2869 líneas) en submódulos por dominio usando el patrón mixin, sin romper ningún caller existente.

**Architecture:** Se crea el paquete `managers/dashboard/` con un mixin por dominio. La clase `GestorDashboard` hereda de todos los mixins (MRO estándar de Python). Los callers (`services/__init__.py`, blueprints) no cambian en absoluto — siguen usando `gestor_dashboard.method()`.

**Tech Stack:** Python 3.11+, SQLAlchemy, Flask. Refactoring puro — sin nuevas dependencias.

---

## Mapa de archivos

### Crear
| Archivo | Responsabilidad |
|---------|----------------|
| `managers/dashboard/__init__.py` | Paquete vacío |
| `managers/dashboard/_helpers.py` | `_iso()`, constantes de módulo (`_TARANCON_*`, `_COLORES_ESTADO`, `_UMBRALES_RETRASO`, `_ESTADOS_OPERATIVOS`, `_ESTADOS_LISTOS_PARA_PICKING`) |
| `managers/dashboard/_base.py` | `GestorDashboardBase`: propiedad `session`, `_ESTADOS_PROTEGIDOS`, `_actualizar_estado_operativo()`, `_tiempo_medio()` |
| `managers/dashboard/gestor_pedidos_mixin.py` | `metricas`, `pedidos_activos`, `alertas`, `eventos`, `historial_pedidos`, `detalle_pedido` |
| `managers/dashboard/gestor_picking_mixin.py` | `picking_activo`, `asignar_picker`, `reasignar_picker`, `completar_picking`, `actualizar_item_picking`, `pickings_del_picker`, `pickings_sin_asignar`, `reclamar_picking`, `buscar_productos` |
| `managers/dashboard/gestor_reparto_mixin.py` | `repartidores`, `mapa`, `asignar_repartidor`, `marcar_salida_reparto`, `marcar_entregado`, `marcar_no_entregado`, `registrar_cobro`, `cierre_caja_repartidor`, `repartos_del_repartidor`, `repartos_sin_asignar`, `reclamar_reparto` |
| `managers/dashboard/gestor_turnos_mixin.py` | `turnos_hoy`, `turnos_historial`, `turnos_planificacion`, `crear_turno`, `editar_turno`, `cancelar_turno` |
| `managers/dashboard/gestor_empleados_mixin.py` | `monitor_empleados`, `empleados_disponibles`, `rendimiento_resumen`, `rendimiento_empleado` (nota: `empleados_disponibles` va AQUÍ — no en reparto) |
| `managers/dashboard/gestor_estadisticas_mixin.py` | `estadisticas` |

### Modificar
| Archivo | Cambio |
|---------|--------|
| `managers/gestor_dashboard.py` | Reemplazar todo el cuerpo de `GestorDashboard` por herencia múltiple de los mixins |

### No tocar
| Archivo | Razón |
|---------|-------|
| `services/__init__.py` | Sigue instanciando `GestorDashboard()` — compatible sin cambios |
| `blueprints/dashboard.py` | Sigue usando `gestor_dashboard.method()` — compatible sin cambios |
| `blueprints/picker.py` | Ídem |
| `blueprints/repartidor.py` | Ídem |
| `tests/` | Los tests existentes son los tests de regresión — no cambiar |

---

## Patrón de cada mixin

> ⚠️ **Advertencia global para quien ejecute este plan:** Los fragmentos de código en cada tarea son ILUSTRATIVOS (estructura, imports aproximados, firmas orientativas). Siempre copiar el cuerpo exacto de los métodos desde `managers/gestor_dashboard.py` usando las líneas indicadas. Los stubs con `...` son marcadores de posición. Las firmas, defaults y lógica interna deben copiarse del fuente, no del plan.

Cada mixin es una clase Python pura sin herencia explícita. Accede a `self.session` (resuelto en runtime por MRO desde `GestorDashboard`). Importa constantes de `_helpers.py` y modelos directamente.

```python
# managers/dashboard/gestor_picking_mixin.py
from managers.dashboard._helpers import (
    _iso, _ESTADOS_LISTOS_PARA_PICKING, _UMBRALES_RETRASO,
)
from models import Pedido, PickingPedido, ...

class GestorPickingMixin:
    def picking_activo(self): ...
    def asignar_picker(self, pedido_id, empleado_id): ...
    # etc.
```

`GestorDashboard` final:

```python
from managers.dashboard._base import GestorDashboardBase
from managers.dashboard.gestor_pedidos_mixin import GestorPedidosMixin
from managers.dashboard.gestor_picking_mixin import GestorPickingMixin
from managers.dashboard.gestor_reparto_mixin import GestorRepartoMixin
from managers.dashboard.gestor_turnos_mixin import GestorTurnosMixin
from managers.dashboard.gestor_empleados_mixin import GestorEmpleadosMixin
from managers.dashboard.gestor_estadisticas_mixin import GestorEstadisticasMixin

class GestorDashboard(
    GestorPedidosMixin,
    GestorPickingMixin,
    GestorRepartoMixin,
    GestorTurnosMixin,
    GestorEmpleadosMixin,
    GestorEstadisticasMixin,
    GestorDashboardBase,
):
    """Composite dashboard manager. Business logic lives in each mixin."""
    pass
```

---

## Task 0: Baseline — verificar tests en verde

**Files:**
- (ninguno — sólo lectura)

- [ ] **Step 1: Ejecutar todos los tests**

```bash
pytest --tb=short -q
```

Esperado: todos los tests pasan (memorizar número exacto). Si alguno falla, parar y reportar — no continuar el refactoring con tests en rojo.

- [ ] **Step 2: Anotar conteo**

```bash
pytest --tb=short -q 2>&1 | tail -3
```

Guardar la línea de resumen (ej. `110 passed in 3.2s`) — se usará para comparar tras cada extracción.

---

## Task 1: Crear paquete `managers/dashboard/` con helpers y base

**Files:**
- Create: `managers/dashboard/__init__.py`
- Create: `managers/dashboard/_helpers.py`
- Create: `managers/dashboard/_base.py`

- [ ] **Step 1: Crear `managers/dashboard/__init__.py`**

```python
# managers/dashboard/__init__.py
```

(Archivo vacío — sólo declara el paquete.)

- [ ] **Step 2: Crear `managers/dashboard/_helpers.py`**

> ⚠️ **Los fragmentos de código en este plan son ILUSTRATIVOS. Copiar siempre el código exacto del archivo fuente, no del plan.** Los valores de constantes, firmas y defaults pueden diferir.

Estructura del archivo (copiar el contenido exacto de `managers/gestor_dashboard.py` líneas 22-64):

```python
# managers/dashboard/_helpers.py
"""Constantes y helpers de módulo compartidos por todos los mixins del dashboard."""

# <pegar aquí el bloque exacto de gestor_dashboard.py líneas 22-64>
# Incluye: _iso(), _TARANCON_LAT, _TARANCON_LNG, _COLORES_ESTADO,
#          _UMBRALES_RETRASO, _ESTADOS_OPERATIVOS, _ESTADOS_LISTOS_PARA_PICKING
# Los valores exactos (hex colors, floats, listas) deben copiarse del fuente.
```

- [ ] **Step 3: Crear `managers/dashboard/_base.py`**

Copiar desde `managers/gestor_dashboard.py` la propiedad `session`, `_ESTADOS_PROTEGIDOS`, `_actualizar_estado_operativo` (líneas 67-100) y el método `_tiempo_medio` (líneas 189-212):

```python
# managers/dashboard/_base.py
"""Clase base del dashboard: session de BD, helpers de instancia compartidos."""
import logging
from datetime import datetime

from models import Empleado, HistorialEstadoPedido
from states import EstadoPedido
from threading import Thread

logger = logging.getLogger(__name__)


class GestorDashboardBase:

    @property
    def session(self):
        from database import get_db
        return get_db()

    _ESTADOS_PROTEGIDOS = frozenset({'en_pausa', 'desconectado'})

    def _actualizar_estado_operativo(self, empleado_id: int, nuevo_estado: str) -> None:
        # (copiar cuerpo exacto de gestor_dashboard.py líneas 76-100)
        ...

    def _tiempo_medio(self, desde: datetime, estado_inicio: EstadoPedido, estado_fin: EstadoPedido):
        # (copiar cuerpo exacto de gestor_dashboard.py líneas 189-212)
        ...
```

> **Nota:** Copiar los cuerpos de función exactamente del archivo original. Los `...` son marcadores de posición en este plan.

- [ ] **Step 4: Ejecutar tests para verificar que el paquete nuevo no rompe nada**

```bash
pytest --tb=short -q
```

Esperado: mismo conteo que en Task 0.

- [ ] **Step 5: Commit**

```bash
git add managers/dashboard/
git commit -m "refactor: create managers/dashboard package with shared helpers and base class"
```

---

## Task 2: Extraer `GestorPedidosMixin`

Funciones a mover (líneas aproximadas en `gestor_dashboard.py`):
- `metricas()` — 106-187
- `pedidos_activos()` — 214-291
- `alertas()` — 516-565
- `eventos()` — 567-584
- `historial_pedidos()` — 1877-1963
- `detalle_pedido()` — 1965-2039

**Files:**
- Create: `managers/dashboard/gestor_pedidos_mixin.py`
- Modify: `managers/gestor_dashboard.py`

- [ ] **Step 1: Crear `managers/dashboard/gestor_pedidos_mixin.py`**

```python
# managers/dashboard/gestor_pedidos_mixin.py
"""Mixin: consultas de pedidos activos, métricas diarias, alertas e historial."""
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, or_, and_

from managers.dashboard._helpers import (
    _iso, _COLORES_ESTADO, _UMBRALES_RETRASO, _ESTADOS_OPERATIVOS,
)
from models import (
    Empleado, HistorialEstadoPedido, Pedido, PedidoDetalle,
    PickingPedido, Producto, Reparto,
)
from states import EstadoPedido, EstadoPicking, EstadoReparto, ESTADOS_TERMINALES_PEDIDO

logger = logging.getLogger(__name__)


class GestorPedidosMixin:

    def metricas(self) -> dict:
        # (copiar cuerpo exacto de gestor_dashboard.py)
        ...

    def pedidos_activos(self, estado=None) -> list:
        # (copiar cuerpo exacto)
        ...

    def alertas(self) -> dict:
        # (copiar cuerpo exacto)
        ...

    def eventos(self, limit: int = 50) -> list:
        # (copiar cuerpo exacto)
        ...

    def historial_pedidos(self, desde=None, hasta=None, estado=None,
                          forma_pago=None, q=None, page=1, per_page=50) -> dict:
        # (copiar cuerpo exacto)
        ...

    def detalle_pedido(self, pedido_id: int) -> dict | None:
        # (copiar cuerpo exacto)
        ...
```

- [ ] **Step 2: Actualizar `managers/gestor_dashboard.py` — añadir herencia**

Añadir el import y la herencia. En este punto `GestorDashboard` heredará de `GestorPedidosMixin` y tendrá los métodos movidos **más** los métodos que aún no se han movido (los que siguen en el cuerpo de la clase):

```python
# Al inicio de managers/gestor_dashboard.py, añadir:
from managers.dashboard.gestor_pedidos_mixin import GestorPedidosMixin
from managers.dashboard._base import GestorDashboardBase

class GestorDashboard(GestorPedidosMixin, GestorDashboardBase):
    # Eliminar los métodos que ya se movieron al mixin:
    # metricas, pedidos_activos, alertas, eventos, historial_pedidos, detalle_pedido
    # Mantener todos los demás métodos intactos
    ...
```

> **Importante:** Verificar que no quedan referencias duplicadas. Si un método existe tanto en el mixin como en la clase, Python usará el de la clase (MRO). Eliminar del cuerpo de `GestorDashboard` los métodos que ya están en el mixin.

- [ ] **Step 3: Ejecutar tests**

```bash
pytest --tb=short -q
```

Esperado: mismo conteo que baseline.

- [ ] **Step 4: Commit**

```bash
git add managers/dashboard/gestor_pedidos_mixin.py managers/gestor_dashboard.py
git commit -m "refactor: extract GestorPedidosMixin (metricas, pedidos_activos, alertas, historial)"
```

---

## Task 3: Extraer `GestorPickingMixin`

Funciones a mover:
- `picking_activo()` — 293-444
- `buscar_productos()` — 611-624
- `asignar_picker()` — 972-1022
- `reasignar_picker()` — 1024-1087
- `completar_picking()` — 1089-1202
- `pickings_del_picker()` — 1270-1326
- `actualizar_item_picking()` — 1453-1485
- `pickings_sin_asignar()` — 1781-1811
- `reclamar_picking()` — 1813-1875

**Files:**
- Create: `managers/dashboard/gestor_picking_mixin.py`
- Modify: `managers/gestor_dashboard.py`

- [ ] **Step 1: Crear `managers/dashboard/gestor_picking_mixin.py`**

```python
# managers/dashboard/gestor_picking_mixin.py
"""Mixin: operaciones de picking — asignación, reclamación, completado."""
import logging
from datetime import datetime

from sqlalchemy import func, or_, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload, selectinload
from threading import Thread

from managers.dashboard._helpers import (
    _iso, _ESTADOS_LISTOS_PARA_PICKING, _UMBRALES_RETRASO,
)
from models import (
    Empleado, Pedido, PedidoDetalle, PickingItem, PickingPedido, Producto,
)
from states import EstadoPedido, EstadoPicking, transicion_valida_pedido

logger = logging.getLogger(__name__)


class GestorPickingMixin:

    def picking_activo(self) -> dict:
        # (copiar cuerpo exacto)
        ...

    def buscar_productos(self, q: str) -> list:
        # (copiar cuerpo exacto)
        ...

    def asignar_picker(self, pedido_id: int, empleado_id: int) -> tuple[bool, str]:
        # (copiar cuerpo exacto)
        ...

    def reasignar_picker(self, picking_id: int, nuevo_empleado_id: int | None) -> tuple[bool, str]:
        # (copiar cuerpo exacto)
        ...

    def completar_picking(self, picking_id: int, picker_id: int | None = None) -> tuple[bool, str, str | None]:
        # (copiar cuerpo exacto)
        ...

    def pickings_del_picker(self, empleado_id: int) -> list:
        # (copiar cuerpo exacto)
        ...

    def actualizar_item_picking(self, item_id: int, **kwargs) -> tuple[bool, str]:
        # (copiar cuerpo exacto)
        ...

    def pickings_sin_asignar(self) -> list:
        # (copiar cuerpo exacto)
        ...

    def reclamar_picking(self, picking_id: int, empleado_id: int) -> tuple[bool, str]:
        # (copiar cuerpo exacto)
        ...
```

- [ ] **Step 2: Actualizar `managers/gestor_dashboard.py`**

Añadir `GestorPickingMixin` a la herencia y eliminar los métodos movidos del cuerpo de la clase.

```python
from managers.dashboard.gestor_picking_mixin import GestorPickingMixin

class GestorDashboard(GestorPedidosMixin, GestorPickingMixin, GestorDashboardBase):
    ...
```

- [ ] **Step 3: Ejecutar tests**

```bash
pytest --tb=short -q
```

Esperado: mismo conteo que baseline.

- [ ] **Step 4: Commit**

```bash
git add managers/dashboard/gestor_picking_mixin.py managers/gestor_dashboard.py
git commit -m "refactor: extract GestorPickingMixin (picking_activo, asignar, reclamar, completar)"
```

---

## Task 4: Extraer `GestorRepartoMixin`

Funciones a mover:
- `repartidores()` — 446-514
- `mapa()` — 586-609
- `asignar_repartidor()` — 1204-1234
- `marcar_salida_reparto()` — 1236-1264
- `marcar_no_entregado()` — 1430-1451
- `marcar_entregado()` — 1487-1543
- `registrar_cobro()` — 1545-1575
- `cierre_caja_repartidor()` — 1577-1661
- `repartos_del_repartidor()` — 1332-1428
- `repartos_sin_asignar()` — 1663-1715
- `reclamar_reparto()` — 1717-1779

**Files:**
- Create: `managers/dashboard/gestor_reparto_mixin.py`
- Modify: `managers/gestor_dashboard.py`

- [ ] **Step 1: Crear `managers/dashboard/gestor_reparto_mixin.py`**

```python
# managers/dashboard/gestor_reparto_mixin.py
"""Mixin: operaciones de reparto — asignación, entrega, cobro, cierre de caja."""
import logging
from datetime import datetime

from sqlalchemy import func, or_, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import joinedload

from managers.dashboard._helpers import (
    _iso, _TARANCON_LAT, _TARANCON_LNG, _COLORES_ESTADO,
)
from models import (
    Empleado, Pedido, PedidoDetalle, Reparto, Rol,
)
from states import EstadoPedido, EstadoReparto, transicion_valida_pedido

logger = logging.getLogger(__name__)


class GestorRepartoMixin:

    def repartidores(self) -> list:
        ...

    def mapa(self) -> list:
        ...

    # NOTA: empleados_disponibles NO va aquí — pertenece a GestorEmpleadosMixin (Task 6)

    def asignar_repartidor(self, pedido_id: int, empleado_id: int) -> tuple[bool, str]:
        ...

    def marcar_salida_reparto(self, reparto_id: int) -> tuple[bool, str, str | None]:
        ...

    def marcar_entregado(self, reparto_id: int) -> tuple[bool, str, str | None]:
        ...

    def marcar_no_entregado(self, reparto_id: int, motivo: str) -> tuple[bool, str, str | None]:
        ...

    def registrar_cobro(self, reparto_id: int, **kwargs) -> tuple[bool, str]:
        ...

    def cierre_caja_repartidor(self, repartidor_id: int, fecha: str | None = None) -> dict:
        ...

    def repartos_del_repartidor(self, repartidor_id: int) -> list:
        ...

    def repartos_sin_asignar(self) -> list:
        ...

    def reclamar_reparto(self, pedido_id: int, empleado_id: int) -> tuple[bool, str]:
        ...
```

- [ ] **Step 2: Actualizar `managers/gestor_dashboard.py`**

```python
from managers.dashboard.gestor_reparto_mixin import GestorRepartoMixin

class GestorDashboard(
    GestorPedidosMixin,
    GestorPickingMixin,
    GestorRepartoMixin,
    GestorDashboardBase,
):
    ...
```

- [ ] **Step 3: Ejecutar tests**

```bash
pytest --tb=short -q
```

Esperado: mismo conteo que baseline.

- [ ] **Step 4: Commit**

```bash
git add managers/dashboard/gestor_reparto_mixin.py managers/gestor_dashboard.py
git commit -m "refactor: extract GestorRepartoMixin (repartidores, asignar, marcar_entregado, cobro)"
```

---

## Task 5: Extraer `GestorTurnosMixin`

Funciones a mover:
- `turnos_hoy()` — 2041-2148
- `turnos_historial()` — 2150-2236
- `turnos_planificacion()` — 2712-2766
- `crear_turno()` — 2768-2812
- `editar_turno()` — 2814-2848
- `cancelar_turno()` — 2850-2869

**Files:**
- Create: `managers/dashboard/gestor_turnos_mixin.py`
- Modify: `managers/gestor_dashboard.py`

- [ ] **Step 1: Crear `managers/dashboard/gestor_turnos_mixin.py`**

```python
# managers/dashboard/gestor_turnos_mixin.py
"""Mixin: gestión de turnos y asistencia — consultas, creación, edición, cancelación."""
import logging
from datetime import datetime, date

from sqlalchemy.exc import SQLAlchemyError

from managers.dashboard._helpers import _iso
from models import Empleado, Rol  # + CheckIn, Turno si están en models

logger = logging.getLogger(__name__)


class GestorTurnosMixin:

    def turnos_hoy(self) -> dict:
        ...

    def turnos_historial(self, desde=None, hasta=None, empleado_id=None,
                         rol=None, page=1, per_page=50) -> dict:
        ...

    def turnos_planificacion(self, desde=None, hasta=None, empleado_id=None,
                              page=1, per_page=50) -> dict:
        ...

    def crear_turno(self, empleado_id: int, **kwargs) -> dict:
        ...

    def editar_turno(self, turno_id: int, **kwargs) -> dict:
        ...

    def cancelar_turno(self, turno_id: int) -> dict:
        ...
```

- [ ] **Step 2: Actualizar `managers/gestor_dashboard.py`**

```python
from managers.dashboard.gestor_turnos_mixin import GestorTurnosMixin

class GestorDashboard(
    GestorPedidosMixin,
    GestorPickingMixin,
    GestorRepartoMixin,
    GestorTurnosMixin,
    GestorDashboardBase,
):
    ...
```

- [ ] **Step 3: Ejecutar tests**

```bash
pytest --tb=short -q
```

- [ ] **Step 4: Commit**

```bash
git add managers/dashboard/gestor_turnos_mixin.py managers/gestor_dashboard.py
git commit -m "refactor: extract GestorTurnosMixin (turnos_hoy, historial, crear, editar, cancelar)"
```

---

## Task 6: Extraer `GestorEmpleadosMixin`

Funciones a mover:
- `empleados_disponibles()` — 626-639
- `monitor_empleados()` — 640-966
- `rendimiento_resumen()` — 2238-2338
- `rendimiento_empleado()` — 2340-2517

**Files:**
- Create: `managers/dashboard/gestor_empleados_mixin.py`
- Modify: `managers/gestor_dashboard.py`

- [ ] **Step 1: Crear `managers/dashboard/gestor_empleados_mixin.py`**

```python
# managers/dashboard/gestor_empleados_mixin.py
"""Mixin: monitorización de empleados y rendimiento individual/colectivo."""
import logging
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import joinedload

from managers.dashboard._helpers import _iso
from models import (
    Empleado, Incidencia, PickingItem, PickingPedido, Reparto,
    Pedido, Rol,
)
from states import EstadoPicking, EstadoReparto

logger = logging.getLogger(__name__)


class GestorEmpleadosMixin:

    def monitor_empleados(self) -> dict:
        ...

    def empleados_disponibles(self, rol: str | None = None) -> list:
        # Lookup genérico de empleados activos por rol — usado por picking y reparto
        ...

    def rendimiento_resumen(self, periodo: str = 'hoy', rol: str | None = None) -> dict:
        ...

    def rendimiento_empleado(self, empleado_id: int, periodo: str = 'semana') -> dict | None:
        ...
```

- [ ] **Step 2: Actualizar `managers/gestor_dashboard.py`**

```python
from managers.dashboard.gestor_empleados_mixin import GestorEmpleadosMixin

class GestorDashboard(
    GestorPedidosMixin,
    GestorPickingMixin,
    GestorRepartoMixin,
    GestorTurnosMixin,
    GestorEmpleadosMixin,
    GestorDashboardBase,
):
    ...
```

- [ ] **Step 3: Ejecutar tests**

```bash
pytest --tb=short -q
```

- [ ] **Step 4: Commit**

```bash
git add managers/dashboard/gestor_empleados_mixin.py managers/gestor_dashboard.py
git commit -m "refactor: extract GestorEmpleadosMixin (monitor_empleados, rendimiento)"
```

---

## Task 7: Extraer `GestorEstadisticasMixin`

Funciones a mover:
- `estadisticas()` — 2519-2710

**Files:**
- Create: `managers/dashboard/gestor_estadisticas_mixin.py`
- Modify: `managers/gestor_dashboard.py`

- [ ] **Step 1: Crear `managers/dashboard/gestor_estadisticas_mixin.py`**

```python
# managers/dashboard/gestor_estadisticas_mixin.py
"""Mixin: analítica histórica de ventas y operaciones."""
import logging
from datetime import datetime, timedelta, date

from sqlalchemy import func

from managers.dashboard._helpers import _iso
from models import Pedido, HistorialEstadoPedido
from states import EstadoPedido, ESTADOS_TERMINALES_PEDIDO

logger = logging.getLogger(__name__)


class GestorEstadisticasMixin:

    def estadisticas(self, desde: str | None = None, hasta: str | None = None,
                     granularidad: str = 'dia') -> dict:
        ...
```

> **Nota sobre `estadisticas`:** Este método computa promedios de tiempo de forma inline y NO llama a `self._tiempo_medio`. Es comportamiento intencional — no intentar unificar ambas implementaciones. Este refactoring es extracción mecánica, no consolidación de lógica.

- [ ] **Step 2: Actualizar `managers/gestor_dashboard.py` — versión final**

En este punto `GestorDashboard` ya no debería tener ningún método propio (todos fueron movidos). Reemplazar el cuerpo completo del archivo:

```python
# managers/gestor_dashboard.py
"""
GestorDashboard — Public API.

All business logic lives in the domain mixins under managers/dashboard/.
This file is intentionally thin: it just assembles the mixins.
"""
import logging

from managers.dashboard._base import GestorDashboardBase
from managers.dashboard.gestor_pedidos_mixin import GestorPedidosMixin
from managers.dashboard.gestor_picking_mixin import GestorPickingMixin
from managers.dashboard.gestor_reparto_mixin import GestorRepartoMixin
from managers.dashboard.gestor_turnos_mixin import GestorTurnosMixin
from managers.dashboard.gestor_empleados_mixin import GestorEmpleadosMixin
from managers.dashboard.gestor_estadisticas_mixin import GestorEstadisticasMixin

logger = logging.getLogger(__name__)


class GestorDashboard(
    GestorPedidosMixin,
    GestorPickingMixin,
    GestorRepartoMixin,
    GestorTurnosMixin,
    GestorEmpleadosMixin,
    GestorEstadisticasMixin,
    GestorDashboardBase,
):
    """Composite dashboard manager. Business logic lives in each domain mixin."""
    pass
```

- [ ] **Step 3: Verificar que el archivo fuente original ya está vacío de métodos**

```bash
wc -l managers/gestor_dashboard.py
```

Esperado: ~30 líneas (sólo imports + clase vacía).

- [ ] **Step 4: Ejecutar tests completos**

```bash
pytest --tb=short -q
```

Esperado: exactamente el mismo conteo que baseline (Task 0, Step 2).

- [ ] **Step 5: Commit final**

```bash
git add managers/dashboard/gestor_estadisticas_mixin.py managers/gestor_dashboard.py
git commit -m "refactor: extract GestorEstadisticasMixin — gestor_dashboard.py is now a thin facade"
```

---

## Task 8: Verificación final

- [ ] **Step 1: Ejecutar suite completa con verbose**

```bash
pytest -v --tb=short 2>&1 | tail -20
```

Esperado: todos los tests pasan. Ninguno nuevo falla.

- [ ] **Step 2: Verificar tamaño del archivo original**

```bash
wc -c managers/gestor_dashboard.py
```

Esperado: < 2 KB (antes era 121 KB).

- [ ] **Step 3: Verificar que los callers no se tocaron**

```bash
git diff $(git merge-base HEAD master) -- services/__init__.py blueprints/dashboard.py blueprints/picker.py blueprints/repartidor.py
```

Esperado: sin cambios en ninguno de estos archivos.

- [ ] **Step 4: Listar archivos del paquete nuevo**

```bash
ls -lh managers/dashboard/
```

Esperado: 8 archivos (`__init__.py`, `_helpers.py`, `_base.py`, 5 mixins) + ningún archivo > 30 KB.

---

## Notas de implementación

### Imports circulares
`_base.py` importa `from database import get_db` dentro del método (lazy import). Mantener este patrón — es intencional para evitar imports circulares al arrancar la app.

### Constantes compartidas que usan valores de `states.py`
`_ESTADOS_LISTOS_PARA_PICKING` y `_ESTADOS_OPERATIVOS` en `_helpers.py` referencian `EstadoPedido`. El import de `states` en `_helpers.py` es seguro (no hay ciclo).

### Background threads con sesión propia
`_actualizar_estado_operativo` y la función `_descontar` de `completar_picking` crean su propio `SessionLocal()`. Este patrón debe mantenerse exactamente — no refactorizar los threads.

### Imports lazy de `CheckIn` y `Turno`
Los métodos de turno (`turnos_hoy`, `turnos_historial`, `rendimiento_empleado`, etc.) usan `from models import CheckIn` y `from models import Turno as TurnoModel` como imports lazy dentro del cuerpo de la función, no al nivel de módulo. Igual que el patrón de `database.get_db`. Mantener este patrón en los mixins — no hoistear al nivel de módulo.

### Orden MRO
El orden de herencia en `GestorDashboard` importa si hay métodos con el mismo nombre en varios mixins. Con los dominios actuales no hay colisiones, pero `GestorDashboardBase` siempre va al final para que sus métodos tengan la menor prioridad.
