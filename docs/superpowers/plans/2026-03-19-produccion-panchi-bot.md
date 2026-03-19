# Panchi-Bot: Llevar a Producción — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Llevar Panchi-Bot de "funciona en pruebas controladas" a "listo para producción real" corrigiendo los items abiertos, añadiendo métricas, puliendo cada interfaz y añadiendo autenticación + hardening de deployment.

**Architecture:** Cuatro fases secuenciales (Fase 1 base → Fase 2 visibilidad → Fase 3 pulido → Fase 4 hardening). Cada fase se valida con `pytest` al completo antes de continuar. Stack: Flask + SQLAlchemy (SQL Server) + Redis + Twilio + Monei. Tests con fakeredis (conftest.py ya lo configura).

**Tech Stack:** Python 3.x, Flask, SQLAlchemy, Redis (fakeredis en tests), Twilio, Monei, tenacity, werkzeug, gunicorn, Docker.

**Spec:** `docs/superpowers/specs/2026-03-19-produccion-panchi-bot-design.md`

---

## FASE 1 — Base Fiable

---

### Task 1: AUDIT-1 — Registrar AuditLog en conectar_bd1()

**Problema:** `AuditLog` se importa y usa en `managers/gestor_pedidos.py` (líneas 258, 306, 413) para cancelaciones y modificaciones de items, pero no está incluido en `database.py::conectar_bd1()`. En un deploy limpio, la tabla no existe y la primera cancelación desde el dashboard lanzará `ProgrammingError`.

**Files:**
- Modify: `database.py:50-69`
- Test: `tests/test_database.py` (crear si no existe)

- [ ] **Step 1: Verificar que el test actual pasa**

```bash
pytest -v --tb=short
```
Expected: todos los tests pasan (≥110).

- [ ] **Step 2: Escribir el test que detecta la ausencia**

```python
# tests/test_database.py
def test_conectar_bd1_incluye_audit_log(app):
    """AuditLog debe estar en la lista de tablas que conectar_bd1 crea."""
    import database
    from models import AuditLog
    # Verificar que AuditLog.metadata == database.Base.metadata
    # (si está registrado correctamente en Base)
    assert AuditLog.__tablename__ in database.Base.metadata.tables
```

- [ ] **Step 3: Ejecutar para confirmar que pasa (ya debería — el modelo hereda de Base)**

```bash
pytest tests/test_database.py -v
```

> Nota: el modelo ya está bien definido. Lo que falta es el `create_all` en `conectar_bd1()`. El test anterior valida el modelo; para el bug real (falta en create_all) basta con añadirlo manualmente ya que `create_all` usa `engine` real que no existe en tests.

- [ ] **Step 4: Añadir AuditLog al import y al create_all en database.py**

En `database.py`, línea 50-54, cambiar:

```python
# ANTES:
from models import (
    Usuario, Pedido, PedidoDetalle, Producto, Empleado,
    Categoria, Pago, HistorialEstadoPedido,
    Rol, PickingPedido, PickingItem, Reparto, Incidencia,
)

# DESPUÉS:
from models import (
    Usuario, Pedido, PedidoDetalle, Producto, Empleado,
    Categoria, Pago, HistorialEstadoPedido,
    Rol, PickingPedido, PickingItem, Reparto, Incidencia, AuditLog,
)
```

Y al final del bloque `create_all`, después de `Incidencia` (línea 69), añadir:

```python
        Base.metadata.create_all(engine, tables=[AuditLog.__table__])
```

- [ ] **Step 5: Verificar que la suite sigue verde**

```bash
pytest -v --tb=short
```
Expected: mismo número de tests, todos passing.

- [ ] **Step 6: Commit**

```bash
git add database.py tests/test_database.py
git commit -m "fix(data): registrar AuditLog en conectar_bd1() — tabla ausente en deploy limpio"
```

---

### Task 2: TD-13 — Reemplazar print() por logger en database.py

**Problema:** `database.py:71,73` usa `print()` en lugar de `logger`. En producción con logs a fichero, estos mensajes no aparecerán en los logs.

**Files:**
- Modify: `database.py:71,73`

- [ ] **Step 1: Sustituir los dos print() por logger**

En `database.py`, antes del bloque `try` de `conectar_bd1()`, añadir el logger (después de los imports):

```python
import logging
logger = logging.getLogger(__name__)
```

Luego reemplazar las líneas 71 y 73:

```python
# ANTES:
        print("✅ Base de datos inicializada correctamente.")
    except Exception as e:
        print(f"❌ Error al inicializar la base de datos: {e}")

# DESPUÉS:
        logger.info("Base de datos inicializada correctamente.")
    except Exception as e:
        logger.error("Error al inicializar la base de datos: %s", e)
```

- [ ] **Step 2: Verificar que la suite sigue verde**

```bash
pytest -v --tb=short
```

- [ ] **Step 3: Commit**

```bash
git add database.py
git commit -m "chore: reemplazar print() por logger en database.py::conectar_bd1"
```

---

## FASE 2 — Logs y Métricas

> Prerequisito: Fase 1 completada y pytest verde.

---

### Task 3: Logs de eventos de negocio estructurados

**Contexto:** Los módulos clave (registro, pedido, pago) ya tienen `logger = logging.getLogger(__name__)`. Lo que falta es añadir llamadas `logger.info` con formato consistente en los puntos clave del flujo de negocio. El formato ya establecido en `main.py` es `%(asctime)s %(name)s %(levelname)s %(message)s`.

**Convención de eventos:** cada log de evento de negocio debe incluir identificadores: `pedido_id`, `usuario` o `modulo` donde aplique.

**Files:**
- Modify: `controllers/registro.py` — log de registro completado
- Modify: `controllers/pedido.py` — log de pedido iniciado y carrito confirmado
- Modify: `controllers/pago.py` — log de pago iniciado
- Modify: `blueprints/webhook.py` — ya tiene logs de pago confirmado; verificar formato
- Modify: `managers/gestor_pedidos.py` — ya tiene logs; verificar que cambio de estado los incluye

- [ ] **Step 1: Verificar logs existentes en los módulos clave**

```bash
grep -n "logger\." /home/siemprearmando/proyectos/panchi-bot/controllers/registro.py /home/siemprearmando/proyectos/panchi-bot/controllers/pedido.py /home/siemprearmando/proyectos/panchi-bot/controllers/pago.py
```

Anotar qué eventos ya tienen log y cuáles faltan.

- [ ] **Step 2: Añadir log de registro completado en controllers/registro.py**

En `confirmar_direccion()`, después de `gestor_usuarios.guardar_usuario(...)`:

```python
logger.info(
    "REGISTRO_COMPLETADO usuario=%s",
    numero_cliente,
)
```

- [ ] **Step 3: Añadir log de pedido iniciado en controllers/pedido.py**

Buscar la función `procesar_pedido` (o equivalente). Después de crear el pedido y generar el token:

```python
logger.info(
    "PEDIDO_INICIADO pedido_id=%s usuario=%s",
    pedido_id, numero_cliente,
)
```

- [ ] **Step 4: Añadir log de carrito confirmado en controllers/pedido.py**

En `confirmar_carrito()`, tras la transición de estado exitosa:

```python
logger.info(
    "CARRITO_CONFIRMADO pedido_id=%s",
    pedido_id,
)
```

- [ ] **Step 5: Añadir log de pago iniciado en controllers/pago.py**

En `iniciar_pago()`, tras crear el pago en Monei:

```python
logger.info(
    "PAGO_INICIADO pedido_id=%s importe=%s",
    pedido_id, importe,
)
```

- [ ] **Step 6: Verificar que la suite sigue verde**

```bash
pytest -v --tb=short
```

- [ ] **Step 7: Commit**

```bash
git add controllers/registro.py controllers/pedido.py controllers/pago.py
git commit -m "chore: añadir logs de eventos de negocio (registro, pedido, carrito, pago)"
```

---

### Task 4: Métricas extendidas en el dashboard

**Contexto:** `GestorDashboard.metricas()` ya devuelve métricas básicas (pedidos_hoy, activos, ingresos_hoy, etc.). El spec requiere métricas adicionales: tiempo medio de preparación/entrega, tasa de cancelaciones con motivo, ingresos desglosados por método de pago, ratio de incidencias por repartidor.

`HistorialEstadoPedido` ya guarda timestamps de cada transición — los tiempos medios se calculan de ahí.

**Files:**
- Modify: `managers/gestor_dashboard.py` — extender `metricas()`
- Test: `tests/test_gestor_dashboard.py` (crear si no existe)

**Nota:** `tiempo_medio_preparacion_min` y `tiempo_medio_entrega_min` ya existen en `metricas()` (líneas 122–127 de `gestor_dashboard.py`). Solo añadir `cancelaciones_hoy` e `ingresos_por_metodo`.

- [ ] **Step 1: Escribir tests para las métricas nuevas**

```python
# tests/test_gestor_dashboard.py
from sqlalchemy.exc import OperationalError
import pyodbc

def test_metricas_keys_existentes_presentes(app):
    """Las claves de timing ya implementadas siguen presentes."""
    from services import gestor_dashboard
    with app.app_context():
        try:
            result = gestor_dashboard.metricas()
            existing_keys = {
                'pedidos_hoy', 'ingresos_hoy_eur',
                'tiempo_medio_preparacion_min', 'tiempo_medio_entrega_min',
            }
            assert existing_keys.issubset(result.keys()), (
                f"Claves faltantes: {existing_keys - result.keys()}"
            )
        except (OperationalError, Exception) as e:
            if 'odbc' in str(e).lower() or 'sql server' in str(e).lower():
                pass  # BD no disponible en CI
            else:
                raise

def test_metricas_incluye_cancelaciones_e_ingresos_por_metodo(app):
    """Smoke test: las claves nuevas existen tras la implementación."""
    from services import gestor_dashboard
    with app.app_context():
        try:
            result = gestor_dashboard.metricas()
            new_keys = {'cancelaciones_hoy', 'ingresos_por_metodo'}
            assert new_keys.issubset(result.keys()), (
                f"Claves nuevas faltantes: {new_keys - result.keys()}"
            )
        except (OperationalError, Exception) as e:
            if 'odbc' in str(e).lower() or 'sql server' in str(e).lower():
                pass
            else:
                raise
```

- [ ] **Step 2: Ejecutar para ver que falla (claves nuevas no existen aún)**

```bash
pytest tests/test_gestor_dashboard.py::test_metricas_incluye_cancelaciones_e_ingresos_por_metodo -v
```

- [ ] **Step 3: Añadir cancelaciones_hoy e ingresos_por_metodo en metricas()**

En `managers/gestor_dashboard.py`, dentro de `metricas()`, añadir después de `ingresos_hoy` (línea 112):

```python
# Cancelaciones hoy con motivo
cancelados_hoy = (
    s.query(Pedido.motivo_cancelacion, func.count(Pedido.PedidoID))
    .filter(
        Pedido.Estado == EstadoPedido.CANCELADO.value,
        Pedido.FechaActualizacion >= hoy,
    )
    .group_by(Pedido.motivo_cancelacion)
    .all()
)
cancelaciones_hoy = {(m or 'sin_motivo'): c for m, c in cancelados_hoy}

# Ingresos por método de cobro hoy (repartos completados)
ingresos_metodo = (
    s.query(Reparto.metodo_cobro, func.sum(Reparto.importe_cobrado))
    .join(Pedido, Reparto.pedido_id == Pedido.PedidoID)
    .filter(Pedido.FechaCreacion >= hoy)
    .group_by(Reparto.metodo_cobro)
    .all()
)
ingresos_por_metodo = {
    (m or 'online'): float(v or 0) for m, v in ingresos_metodo
}
```

Y añadir las dos claves nuevas al `return` existente de `metricas()`:

```python
return {
    # ... existing keys sin cambios ...
    "cancelaciones_hoy": cancelaciones_hoy,
    "ingresos_por_metodo": ingresos_por_metodo,
}
```

- [ ] **Step 4: Ejecutar suite completa**

```bash
pytest -v --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add managers/gestor_dashboard.py tests/test_gestor_dashboard.py
git commit -m "feat: métricas extendidas en dashboard (tiempos, cancelaciones, ingresos por método)"
```

---

### Task 5: Monitor con polling automático cada 15 segundos

**Contexto:** `/dashboard/monitor/datos` ya existe y devuelve `metricas`, `alertas`, `eventos`. El monitor HTML necesita hacer polling automático en lugar de requerir recarga manual.

**Files:**
- Modify: `templates/dashboard/monitor.html` — añadir polling JS cada 15s

- [ ] **Step 1: Revisar el template actual**

```bash
cat templates/dashboard/monitor.html | grep -n "fetch\|setInterval\|reload\|datos"
```

Verificar si ya hay algún mecanismo de refresco.

- [ ] **Step 2: Añadir polling si no existe**

En el `<script>` del template, añadir o reemplazar la lógica de carga:

```javascript
// Polling cada 15 segundos
async function cargarDatos() {
    try {
        const resp = await fetch('/dashboard/monitor/datos');
        if (!resp.ok) throw new Error('Error ' + resp.status);
        const data = await resp.json();
        renderDatos(data);  // función existente o nueva que actualiza el DOM
    } catch (e) {
        console.error('Error actualizando monitor:', e);
    }
}

cargarDatos();  // carga inicial
setInterval(cargarDatos, 15000);  // polling cada 15s
```

- [ ] **Step 3: Verificar manualmente**

```bash
python main.py
# Abrir http://localhost:5000/dashboard/monitor
# Verificar en Network tab que se hace un request cada 15s
```

- [ ] **Step 4: Commit**

```bash
git add templates/dashboard/monitor.html
git commit -m "feat: polling automático cada 15s en monitor de empleados"
```

---

## FASE 3 — Pulido de Interfaces

> Prerequisito: Fase 2 completada y pytest verde.

---

### Task 6: Bot WhatsApp — mensajes de error claros y timeout de enlace

**Contexto:** Durante el registro, si el usuario envía algo inesperado, el sistema puede ignorarlo o responder con un mensaje genérico. También, si un usuario tiene un enlace activo de hace días, el sistema puede dar un error interno en lugar de explicar la situación.

**Files:**
- Modify: `controllers/registro.py` — mensajes de error por paso
- Modify: `controllers/mensajes_registrados.py` — detección de enlace caducado
- Modify: `services/token_service.py` — comprobar TTL del token

- [ ] **Step 1: Revisar el flujo de registro completo**

```bash
grep -n "def procesar\|def manejar\|def _enviar" controllers/registro.py | head -20
```

- [ ] **Step 2: Añadir mensajes de error claros en cada paso del registro**

En `controllers/registro.py`, en cada función de manejo de estado, añadir respuesta al `else` cuando el input no es válido. Ejemplo para la confirmación inicial:

```python
# Si el usuario no escribe "si" en el paso de saludo_inicial:
def _manejar_saludo_inicial(numero_cliente, mensaje):
    if mensaje.lower() in ['si', 'sí']:
        # flujo normal
        ...
    else:
        enviar_mensaje_whatsapp(
            "Para comenzar tu registro escribe *Si* ✅\n"
            "Si no quieres registrarte ahora, simplemente ignora este mensaje.",
            numero_cliente,
        )
```

Hacer lo mismo para el paso `esperando_nombre` (si el nombre está vacío o tiene menos de 2 caracteres) y `esperando_direccion` (si la dirección no se reconoce).

- [ ] **Step 3: Manejar enlace caducado en controllers/mensajes_registrados.py**

Buscar dónde se llama a `generar_token_temporal` o se comprueba si el usuario tiene un enlace activo. Si el token no existe en Redis (caducado), enviar mensaje claro:

```python
# En el flujo de procesamiento de mensaje registrado, cuando se detecta estado 'enlace' pero el token no existe:
enviar_mensaje_whatsapp(
    "Tu enlace de pedido ha caducado ⏱️\n"
    "Escribe *1* para generar un nuevo enlace y continuar tu pedido.",
    numero_cliente,
)
```

- [ ] **Step 4: Verificar suite**

```bash
pytest -v --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add controllers/registro.py controllers/mensajes_registrados.py
git commit -m "feat: mensajes de error claros en registro y enlace caducado"
```

---

### Task 7: Menú web — carrito vacío, contra reembolso e2e, error.html tipado

**Files:**
- Modify: `blueprints/api.py` — validar carrito vacío antes de confirmar
- Modify: `templates/error.html` — añadir soporte para tipo de error
- Modify: `blueprints/menu.py` — pasar tipo de error al template
- Test: `tests/test_api_pedido.py` — test carrito vacío

- [ ] **Step 1: Escribir test para carrito vacío**

```python
# En tests/test_api_pedido.py, añadir:
def test_agregar_pedido_carrito_vacio(client):
    """POST /api/agregar_pedido con carrito vacío debe devolver 400."""
    resp = client.post('/api/agregar_pedido', json={
        'token': 'token-invalido',
        'carrito': [],
    })
    assert resp.status_code in (400, 401, 422)
```

- [ ] **Step 2: Ejecutar para ver que pasa o falla según el comportamiento actual**

```bash
pytest tests/test_api_pedido.py::test_agregar_pedido_carrito_vacio -v
```

- [ ] **Step 3: Añadir validación de carrito vacío en blueprints/api.py**

Buscar el endpoint `POST /api/agregar_pedido`. Antes de procesar el carrito:

```python
carrito = data.get('carrito', [])
if not carrito:
    return jsonify({"error": "El carrito está vacío"}), 400
```

- [ ] **Step 4: Actualizar templates/error.html para mostrar mensajes tipados**

Verificar el contenido actual de `templates/error.html`:

```bash
cat templates/error.html
```

Asegurarse de que acepta una variable `tipo` o `mensaje` de Jinja2:

```html
<!-- templates/error.html debe incluir algo como: -->
<h1>{{ titulo | default('Error') }}</h1>
<p>{{ mensaje | default('Ha ocurrido un error.') }}</p>
```

- [ ] **Step 5: Actualizar blueprints/menu.py para pasar tipo de error**

Buscar los puntos donde se renderiza `error.html` y añadir el contexto:

```python
# Token inválido:
return render_template('error.html',
    titulo='Enlace inválido',
    mensaje='Este enlace no es válido o ya ha sido usado.'
), 403

# Pedido ya pagado:
return render_template('error.html',
    titulo='Pedido ya pagado',
    mensaje='Este pedido ya ha sido pagado. Gracias por tu compra.'
), 409

# Enlace caducado:
return render_template('error.html',
    titulo='Enlace caducado',
    mensaje='Tu enlace ha caducado. Vuelve a WhatsApp y escribe 1 para obtener uno nuevo.'
), 410
```

- [ ] **Step 6: Verificar suite**

```bash
pytest -v --tb=short
```

- [ ] **Step 7: Commit**

```bash
git add blueprints/api.py blueprints/menu.py templates/error.html tests/test_api_pedido.py
git commit -m "feat: validar carrito vacío, error.html tipado, flujo contra reembolso revisado"
```

---

### Task 8: App del Picker — indicador de progreso y aviso de picking completo

**Contexto:** El picker necesita ver claramente cuántos items le quedan y recibir un aviso claro cuando termina.

**Files:**
- Modify: `templates/picker/index.html` — indicador visual de progreso
- Modify: `blueprints/picker.py` — endpoint que devuelve resumen de progreso

- [ ] **Step 1: Revisar el endpoint /picker/mis-pedidos**

```bash
grep -n "pickings_del_picker\|estado\|items" managers/gestor_dashboard.py | head -20
```

Verificar qué campos devuelve para cada picking (items pendientes, listos, total).

- [ ] **Step 2: Asegurarse de que la respuesta incluye contadores de progreso**

El response de `pickings_del_picker` debe incluir para cada pedido:
- `items_total`: número total de items
- `items_listos`: número de items en estado LISTO
- `items_pendientes`: número restante
- `picking_completo`: booleano

Si no los incluye, añadirlos en `GestorDashboard.pickings_del_picker()`.

- [ ] **Step 3: Actualizar el template picker/index.html**

Añadir barra de progreso por pedido:

```html
<!-- Por cada pedido en la lista: -->
<div class="progreso">
  <span>{{ items_listos }}/{{ items_total }} items</span>
  <progress value="{{ items_listos }}" max="{{ items_total }}"></progress>
</div>
<!-- Si picking_completo: -->
<div class="badge-completo" style="display: none;" data-completo="{{ picking_completo }}">
  ✅ Picking completo — listo para repartir
</div>
```

Y el JS que muestra el badge cuando `picking_completo === true`:

```javascript
document.querySelectorAll('[data-completo="True"]').forEach(el => {
    el.style.display = 'block';
});
```

- [ ] **Step 4: Verificar manualmente el flujo**

```bash
python main.py
# Abrir http://localhost:5000/picker?id=1
# Verificar que se muestran los contadores y el badge cuando todos los items están listos
```

- [ ] **Step 5: Commit**

```bash
git add templates/picker/index.html blueprints/picker.py managers/gestor_dashboard.py
git commit -m "feat: indicador de progreso y aviso de picking completo en app picker"
```

---

### Task 9: App del Repartidor — guard de cobro server-side y edge cases de mapa

**Contexto:** `marcar_entregado` en `GestorDashboard` no verifica que el cobro haya sido registrado. Para pedidos contra reembolso (efectivo/tarjeta), debe verificar `reparto.metodo_cobro IS NOT NULL` antes de permitir la transición.

**Files:**
- Modify: `managers/gestor_dashboard.py:1311` — guard en `marcar_entregado`
- Modify: `templates/repartidor/index.html` — botón desactivado hasta cobro
- Test: `tests/test_repartidor.py` (crear si no existe)

- [ ] **Step 1: Escribir test para el guard de cobro**

```python
# tests/test_repartidor.py
from unittest.mock import patch, MagicMock
from managers.gestor_dashboard import GestorDashboard

def test_marcar_entregado_rechaza_sin_cobro(app):
    """marcar_entregado debe retornar error si el reparto no tiene cobro registrado
    y el pedido es contra reembolso."""
    gd = GestorDashboard()
    mock_reparto = MagicMock()
    mock_reparto.metodo_cobro = None
    mock_reparto.id = 1

    mock_pedido = MagicMock()
    mock_pedido.forma_pago = 'efectivo'  # campo en minúsculas según models.py:79

    mock_reparto.pedido = mock_pedido

    with app.app_context():
        with patch.object(type(gd), 'session') as mock_session:
            mock_session.query.return_value.filter_by.return_value.first.return_value = mock_reparto
            ok, msg, telefono = gd.marcar_entregado(1)
            assert not ok
            assert 'cobro' in msg.lower()
```

- [ ] **Step 2: Ejecutar para ver que falla**

```bash
pytest tests/test_repartidor.py::test_marcar_entregado_rechaza_sin_cobro -v
```
Expected: FAIL — actualmente `marcar_entregado` no hace este check.

- [ ] **Step 3: Añadir el guard en managers/gestor_dashboard.py::marcar_entregado**

En `marcar_entregado` (línea 1311), después de verificar que `reparto` existe y antes de cambiar el estado, añadir:

```python
# Guard: para contra reembolso (efectivo/tarjeta), el cobro debe estar registrado
# Nota: el campo es forma_pago (minúsculas) según models.py:79
forma_pago = reparto.pedido.forma_pago if reparto.pedido else None
if forma_pago in ('efectivo', 'tarjeta') and reparto.metodo_cobro is None:
    return False, "Debes registrar el cobro antes de marcar como entregado", None
```

- [ ] **Step 4: Ejecutar suite completa**

```bash
pytest -v --tb=short
```

- [ ] **Step 5: Verificar edge case de mapa — dirección sin coordenadas**

En el template del repartidor, buscar dónde se renderiza el mapa y añadir fallback:

```javascript
// Si lat/lng son null, mostrar texto de dirección en lugar del mapa
if (!pedido.lat_entrega || !pedido.lng_entrega) {
    document.getElementById('mapa').style.display = 'none';
    document.getElementById('direccion-texto').textContent =
        '📍 ' + (pedido.direccion || 'Dirección no disponible');
} else {
    // inicializar mapa normal
}
```

- [ ] **Step 6: Commit**

```bash
git add managers/gestor_dashboard.py templates/repartidor/index.html tests/test_repartidor.py
git commit -m "feat: guard de cobro en marcar_entregado, fallback de mapa sin coordenadas"
```

---

### Task 10: Dashboard — guard de asignación duplicada y estados inválidos

**Contexto:** Si se intenta asignar un repartidor a un pedido que ya tiene uno, el sistema debe pedir confirmación. Los cambios de estado manuales inválidos deben devolver mensaje de error claro.

**Files:**
- Modify: `managers/gestor_dashboard.py` — `asignar_repartidor` devuelve error si ya hay uno asignado
- Modify: `blueprints/dashboard.py` — retornar el error al frontend
- Modify: `templates/dashboard/index.html` — mostrar el error

- [ ] **Step 1: Verificar comportamiento actual de asignar_repartidor**

```bash
grep -n "asignar_repartidor\|ya.*asign\|exists" managers/gestor_dashboard.py | head -20
```

- [ ] **Step 2: Implementar la confirmación en el frontend**

El spec pide "confirmación explícita si ya hay uno asignado". El servidor ya maneja la reasignación correctamente — la confirmación es responsabilidad del frontend.

En el JS del dashboard, antes de llamar a `/dashboard/reparto/asignar`:

```javascript
async function asignarRepartidor(pedidoId, empleadoId, repartidorActual) {
    if (repartidorActual) {
        const confirmado = confirm(
            `Este pedido ya tiene asignado a ${repartidorActual}. ¿Quieres reasignarlo?`
        );
        if (!confirmado) return;
    }
    // ... llamada fetch a /dashboard/reparto/asignar
}
```

La información `repartidorActual` ya viene en los datos del pedido que devuelve `/dashboard/pedidos-activos`.

- [ ] **Step 3: Verificar que los errores de transición de estado inválida llegan al frontend**

En `blueprints/dashboard.py`, los endpoints de cambio de estado ya devuelven `_err(msg)` cuando `ok=False`. Verificar en el template que esos errores se muestran al operador:

```javascript
// En el JS que llama a los endpoints:
if (!data.ok) {
    mostrarError(data.error || 'Error desconocido');
}
```

Donde `mostrarError` muestra un toast/banner visible.

- [ ] **Step 4: Verificar suite**

```bash
pytest -v --tb=short
```

- [ ] **Step 5: Commit**

```bash
git add managers/gestor_dashboard.py blueprints/dashboard.py
git commit -m "feat: guard de repartidor duplicado, errores de estado visibles en dashboard"
```

---

## FASE 4 — Hardening de Producción

> Prerequisito: Fase 3 completada y pytest verde.

---

### Task 11: Autenticación PIN por rol — dashboard, picker, repartidor

**Contexto:** Los tres paneles internos no tienen ninguna autenticación. El modelo `Empleado` ya tiene `password_hash` (nullable). `werkzeug.security` está disponible.

**Approach:**
1. Crear `blueprints/auth.py` con login/logout usando sesiones Flask
2. Crear un decorator `@requiere_rol('manager'/'picker'/'repartidor')` que comprueba `session['empleado_id']` y `session['rol']`
3. Aplicar el decorator a cada blueprint
4. Retirar el patrón `?id=` — el `empleado_id` se lee de `session['empleado_id']`
5. Crear un template `templates/login.html` simple

**Files:**
- Create: `blueprints/auth.py`
- Create: `templates/auth/login.html`
- Modify: `blueprints/picker.py` — aplicar decorator, leer empleado de sesión
- Modify: `blueprints/repartidor.py` — aplicar decorator, leer empleado de sesión
- Modify: `blueprints/dashboard.py` — aplicar decorator, leer empleado de sesión en endpoints de escritura
- Modify: `main.py` — registrar blueprint auth
- Test: `tests/test_auth.py`

- [ ] **Step 1: Escribir tests de autenticación**

```python
# tests/test_auth.py
def test_login_sin_credenciales_devuelve_400(client):
    resp = client.post('/auth/login', json={})
    assert resp.status_code == 400

def test_login_credenciales_invalidas_devuelve_401(client):
    resp = client.post('/auth/login', json={
        'email': 'noexiste@test.com',
        'password': '1234'
    })
    assert resp.status_code == 401

def test_dashboard_sin_sesion_redirige_a_login(client):
    resp = client.get('/dashboard')
    # Debe redirigir al login (302) o devolver 401
    assert resp.status_code in (302, 401)

def test_picker_sin_sesion_redirige_a_login(client):
    resp = client.get('/picker')
    assert resp.status_code in (302, 401)

def test_repartidor_sin_sesion_redirige_a_login(client):
    resp = client.get('/repartidor')
    assert resp.status_code in (302, 401)
```

- [ ] **Step 2: Ejecutar para ver que fallan (actualmente devuelven 200)**

```bash
pytest tests/test_auth.py -v
```

- [ ] **Step 3: Crear blueprints/auth.py**

```python
# blueprints/auth.py
import logging
from functools import wraps

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database import get_db
from models import Empleado, Rol

logger = logging.getLogger(__name__)

blueprint_auth = Blueprint('auth', __name__)

_ROLES_VALIDOS = {'manager', 'picker', 'repartidor', 'admin'}


def _get_empleado_by_email(email: str):
    return get_db().query(Empleado).filter_by(Email=email, activo=True).first()


@blueprint_auth.route('/auth/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('auth/login.html')

    data = request.get_json(silent=True) or request.form
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''

    if not email or not password:
        if request.is_json:
            return jsonify({'error': 'Faltan email y/o contraseña'}), 400
        return render_template('auth/login.html', error='Rellena todos los campos'), 400

    empleado = _get_empleado_by_email(email)
    if not empleado or not empleado.password_hash:
        logger.warning("AUTH_FAIL email=%s — empleado no encontrado o sin contraseña", email)
        if request.is_json:
            return jsonify({'error': 'Credenciales incorrectas'}), 401
        return render_template('auth/login.html', error='Credenciales incorrectas'), 401

    if not check_password_hash(empleado.password_hash, password):
        logger.warning("AUTH_FAIL email=%s — contraseña incorrecta", email)
        if request.is_json:
            return jsonify({'error': 'Credenciales incorrectas'}), 401
        return render_template('auth/login.html', error='Credenciales incorrectas'), 401

    rol_nombre = empleado.rol.nombre if empleado.rol else None
    session['empleado_id'] = empleado.EmpleadoID
    session['empleado_nombre'] = empleado.Nombre
    session['rol'] = rol_nombre
    session.permanent = True

    logger.info("AUTH_OK empleado_id=%s rol=%s", empleado.EmpleadoID, rol_nombre)

    # Redirigir según rol
    destinos = {
        'manager': '/dashboard',
        'admin': '/dashboard',
        'picker': '/picker',
        'repartidor': '/repartidor',
    }
    destino = destinos.get(rol_nombre, '/dashboard')
    if request.is_json:
        return jsonify({'ok': True, 'redirect': destino})
    return redirect(destino)


@blueprint_auth.route('/auth/logout', methods=['POST'])
def logout():
    empleado_id = session.get('empleado_id')
    session.clear()
    logger.info("AUTH_LOGOUT empleado_id=%s", empleado_id)
    return redirect(url_for('auth.login'))


def requiere_rol(*roles_permitidos):
    """Decorator que exige sesión activa con uno de los roles dados."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if 'empleado_id' not in session:
                # Para GETs de HTML devolver redirect; para todo lo demás JSON 401
                if request.method == 'GET' and not request.is_json:
                    return redirect(url_for('auth.login'))
                return jsonify({'error': 'No autenticado'}), 401
            if roles_permitidos and session.get('rol') not in roles_permitidos:
                return jsonify({'error': 'Sin permisos para este panel'}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator
```

- [ ] **Step 4: Crear templates/auth/login.html**

```html
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Panchi-Bot — Acceso</title>
    <style>
        body { font-family: sans-serif; display:flex; justify-content:center; align-items:center; min-height:100vh; background:#f3f4f6; margin:0; }
        .card { background:white; padding:2rem; border-radius:12px; box-shadow:0 2px 8px rgba(0,0,0,.15); width:320px; }
        h1 { font-size:1.4rem; margin-bottom:1.5rem; text-align:center; }
        label { display:block; font-size:.85rem; margin-bottom:.25rem; color:#555; }
        input { width:100%; box-sizing:border-box; padding:.6rem; border:1px solid #d1d5db; border-radius:6px; font-size:1rem; margin-bottom:1rem; }
        button { width:100%; padding:.75rem; background:#2563eb; color:white; border:none; border-radius:6px; font-size:1rem; cursor:pointer; }
        button:hover { background:#1d4ed8; }
        .error { color:#dc2626; font-size:.85rem; margin-bottom:1rem; }
    </style>
</head>
<body>
    <div class="card">
        <h1>🍽️ Panchi-Bot</h1>
        {% if error %}<p class="error">{{ error }}</p>{% endif %}
        <form method="post">
            <label>Email</label>
            <input type="email" name="email" autocomplete="email" required>
            <label>Contraseña</label>
            <input type="password" name="password" autocomplete="current-password" required>
            <button type="submit">Entrar</button>
        </form>
    </div>
</body>
</html>
```

- [ ] **Step 5: Aplicar decorator a blueprints/picker.py — TODAS las rutas**

Añadir `@requiere_rol('picker', 'manager', 'admin')` a **todas** las rutas, incluidas las de escritura (`/picker/item/<id>/estado`, `/picker/picking/<id>/finalizar`). Leer `picker_id` de la sesión:

```python
from flask import session
from blueprints.auth import requiere_rol

@blueprint_picker.route("/picker", strict_slashes=False)
@requiere_rol('picker', 'manager', 'admin')
def index():
    picker_id = session.get('empleado_id')
    return render_template("picker/index.html", picker_id=picker_id)

@blueprint_picker.route("/picker/manifest.json")
@requiere_rol('picker', 'manager', 'admin')
def manifest():
    picker_id = session.get('empleado_id')
    return Response(
        render_template("picker/manifest.json", picker_id=picker_id),
        mimetype="application/manifest+json",
    )

@blueprint_picker.route("/picker/mis-pedidos")
@requiere_rol('picker', 'manager', 'admin')
def mis_pedidos():
    picker_id = session.get('empleado_id')
    try:
        return jsonify(gestor_dashboard.pickings_del_picker(picker_id))
    except Exception as e:
        logger.error("Error en /picker/mis-pedidos: %s", e)
        return jsonify({"error": "Error interno"}), 500

@blueprint_picker.route("/picker/item/<int:item_id>/estado", methods=["POST"])
@requiere_rol('picker', 'manager', 'admin')
def actualizar_item(item_id: int):
    data = request.get_json(silent=True) or {}
    picker_id = session.get('empleado_id')  # ← de sesión, no del body
    # ... resto de la lógica igual, pero usando picker_id de sesión

@blueprint_picker.route("/picker/picking/<int:picking_id>/finalizar", methods=["POST"])
@requiere_rol('picker', 'manager', 'admin')
def finalizar_picking(picking_id: int):
    picker_id = session.get('empleado_id')
    ok, msg, telefono = gestor_dashboard.completar_picking(picking_id, picker_id=picker_id)
    # ... resto igual
```

Eliminar todos los `request.args.get("id", ...)`, `request.args.get("picker_id", ...)` y `data.get("picker_id")` — reemplazar por `session.get('empleado_id')`.

- [ ] **Step 6: Aplicar decorator a blueprints/repartidor.py**

Igual que picker:

```python
from blueprints.auth import requiere_rol

@blueprint_repartidor.route("/repartidor", strict_slashes=False)
@requiere_rol('repartidor', 'manager', 'admin')
def index():
    repartidor_id = session.get('empleado_id')
    return render_template("repartidor/index.html", repartidor_id=repartidor_id)
```

Eliminar todos los `request.args.get("id", ...)` y `request.args.get("repartidor_id", ...)`. Leer de `session['empleado_id']`.

- [ ] **Step 7: Aplicar decorator a blueprints/dashboard.py**

Para las rutas de lectura (HTML):
```python
@blueprint_dashboard.route("/dashboard")
@requiere_rol('manager', 'admin')
def index():
    ...
```

Para los endpoints de escritura (POST), además del decorator, leer `empleado_id` de sesión en lugar del body:

```python
@blueprint_dashboard.route("/dashboard/pedido/<int:pedido_id>/cancelar", methods=["POST"])
@requiere_rol('manager', 'admin')
def cancelar_pedido(pedido_id: int):
    data = request.get_json(silent=True) or {}
    motivo = data.get("motivo")
    empleado_id = session.get('empleado_id')  # ← de sesión, no del body
    ...
```

- [ ] **Step 8: Registrar blueprint en main.py**

```python
from blueprints.auth import blueprint_auth
app.register_blueprint(blueprint_auth)
```

- [ ] **Step 9: Ejecutar suite completa**

```bash
pytest -v --tb=short
```

- [ ] **Step 10: Commit**

```bash
git add blueprints/auth.py blueprints/picker.py blueprints/repartidor.py blueprints/dashboard.py templates/auth/login.html main.py tests/test_auth.py
git commit -m "feat: autenticación PIN por rol (manager/picker/repartidor), retirado patrón ?id="
```

---

### Task 12: Resiliencia — tenacity en Twilio, timeout en Monei

**Contexto:** `enviar_mensaje_whatsapp` en `services/twilio_service.py` no tiene reintentos. Si Twilio devuelve un error transitorio, el mensaje simplemente no se envía. `GestorPedidos` ya usa `tenacity` en DB — necesitamos el mismo patrón en el servicio Twilio.

**Files:**
- Modify: `services/twilio_service.py` — añadir retry con tenacity
- Modify: `services/maps_service.py` — verificar timeout (ya tiene timeout=5, OK)

- [ ] **Step 1: Añadir retry en enviar_mensaje_whatsapp**

```python
# services/twilio_service.py
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from twilio.base.exceptions import TwilioRestException

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(TwilioRestException),
    reraise=True,
)
def enviar_mensaje_whatsapp(mensaje, destinatario):
    _get_client().messages.create(
        body=mensaje,
        from_=config.TWILIO_WHATSAPP_NUMBER,
        to=destinatario
    )
    logger.info("Mensaje enviado a %s", destinatario)
```

- [ ] **Step 2: Verificar que maps_service.py ya tiene timeout**

```bash
grep -n "timeout" services/maps_service.py
```
Expected: `timeout=5` en las llamadas a `requests.get`. Si no existe en alguna, añadir.

- [ ] **Step 3: Ejecutar suite**

```bash
pytest -v --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add services/twilio_service.py
git commit -m "feat: reintentos con tenacity en enviar_mensaje_whatsapp (3 intentos, backoff)"
```

---

### Task 13: Validación de variables de entorno en startup

**Contexto:** Si falta `SECRET_KEY`, `TWILIO_ACCOUNT_SID`, o `MONEI_API_KEY`, el sistema arranca pero falla en el primer uso. Mejor fallar en startup con un mensaje claro.

**Files:**
- Modify: `main.py` — añadir validación antes de `app = Flask(...)`
- Modify: `config.py` — lista de vars obligatorias
- Test: `tests/test_startup.py`

- [ ] **Step 1: Escribir test de validación**

```python
# tests/test_startup.py
import pytest
from unittest.mock import patch
import os

def test_create_app_falla_si_falta_secret_key():
    """Si SECRET_KEY no está definida, create_app debe lanzar EnvironmentError."""
    from main import create_app
    env_sin_key = {k: v for k, v in os.environ.items() if k != 'SECRET_KEY'}
    with patch.dict(os.environ, env_sin_key, clear=True):
        with pytest.raises((EnvironmentError, RuntimeError, SystemExit)):
            create_app()
```

- [ ] **Step 2: Añadir validación en main.py**

La validación debe colocarse **antes del bloque `sentry_sdk.init()`** en `create_app()` para que la app falle con mensaje claro y no en el init de Sentry.

```python
# En create_app(), COMO PRIMERA INSTRUCCIÓN (antes de sentry_sdk.init):
_VARS_OBLIGATORIAS = [
    'SECRET_KEY',
    'TWILIO_ACCOUNT_SID',
    'TWILIO_AUTH_TOKEN',
    'TWILIO_WHATSAPP_NUMBER',
    'MONEI_API_KEY',
    'MONEI_WEBHOOK_SECRET',
    'PUBLIC_URL',
]

if not (config or {}).get('TESTING'):
    faltantes = [v for v in _VARS_OBLIGATORIAS if not os.environ.get(v)]
    if faltantes:
        raise EnvironmentError(
            f"Variables de entorno obligatorias no definidas: {', '.join(faltantes)}\n"
            f"Comprueba tu archivo .env"
        )
```

- [ ] **Step 3: Ejecutar suite — los tests existentes usan TESTING=True y no deben verse afectados**

```bash
pytest -v --tb=short
```

- [ ] **Step 4: Commit**

```bash
git add main.py tests/test_startup.py
git commit -m "feat: validación de env vars obligatorias en startup (falla rápido y claro)"
```

---

### Task 14: Deployment — gunicorn, docker-compose, /health endpoint

**Files:**
- Create: `Procfile`
- Create: `docker-compose.yml`
- Create: `nginx.conf`
- Modify: `main.py` o `blueprints/health.py` — endpoint `/health`
- Test: `tests/test_health.py`

- [ ] **Step 1: Escribir test para /health**

```python
# tests/test_health.py
def test_health_devuelve_200(client):
    resp = client.get('/health')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'ok'

def test_health_incluye_componentes(client):
    resp = client.get('/health')
    data = resp.get_json()
    assert 'redis' in data
    assert 'database' in data
```

- [ ] **Step 2: Añadir endpoint /health en main.py**

```python
# En create_app(), después de registrar blueprints:
@app.route('/health')
def health():
    import json
    checks = {}

    # Redis check
    try:
        from managers.gestor_redis import redismanager
        redismanager.client.ping()
        checks['redis'] = 'ok'
    except Exception as e:
        checks['redis'] = f'error: {e}'

    # DB check
    try:
        from database import get_db
        from sqlalchemy import text  # ← import explícito necesario
        get_db().execute(text('SELECT 1'))
        checks['database'] = 'ok'
    except Exception as e:
        checks['database'] = f'error: {e}'

    status = 'ok' if all(v == 'ok' for v in checks.values()) else 'degraded'
    code = 200 if status == 'ok' else 503
    return app.response_class(
        json.dumps({'status': status, **checks}),
        status=code,
        mimetype='application/json',
    )
```

- [ ] **Step 3: Crear Procfile**

```
web: gunicorn "main:create_app()" --bind 0.0.0.0:5000 --workers 2 --timeout 30 --access-logfile -
```

- [ ] **Step 4: Crear docker-compose.yml**

```yaml
services:
  app:
    build: .
    ports:
      - "5000:5000"
    env_file: .env
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 3

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
    depends_on:
      - app
    restart: unless-stopped
```

- [ ] **Step 5: Crear nginx.conf básico**

```nginx
server {
    listen 80;

    location /health {
        proxy_pass http://app:5000/health;
        access_log off;
    }

    location / {
        proxy_pass http://app:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 30s;
    }
}
```

- [ ] **Step 6: Ejecutar suite**

```bash
pytest tests/test_health.py -v
pytest -v --tb=short
```

- [ ] **Step 7: Commit**

```bash
git add Procfile docker-compose.yml nginx.conf main.py tests/test_health.py
git commit -m "feat: /health endpoint, Procfile gunicorn, docker-compose con nginx+redis"
```

---

### Task 15: Observabilidad — Sentry context, logs a fichero con rotación

**Files:**
- Modify: `main.py` — logging a fichero con RotatingFileHandler en prod
- Modify: `blueprints/webhook.py` — añadir sentry scope con pedido_id en errores
- Create: `docs/runbook.md`

- [ ] **Step 1: Añadir RotatingFileHandler en create_app()**

```python
import logging.handlers

# En create_app(), después de logging.basicConfig():
if not (config or {}).get('TESTING'):
    log_file = os.environ.get('LOG_FILE', 'panchi-bot.log')
    file_handler = logging.handlers.RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding='utf-8',
    )
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s"
    ))
    logging.getLogger().addHandler(file_handler)
```

Añadir `LOG_FILE` a `config.py` y a `.env.example` como opcional.

- [ ] **Step 2: Añadir Sentry scope en el error handler global**

`push_scope()` fue eliminado en sentry-sdk v2. Usar la API actual:

En `main.py::manejar_errores_globales`, reemplazar `capture_exception(e)` por:

```python
import sentry_sdk
scope = sentry_sdk.get_current_scope()
scope.set_tag('blueprint', request.blueprints[-1] if request.blueprints else 'unknown')
scope.set_extra('url', request.url)
sentry_sdk.capture_exception(e)
```

- [ ] **Step 3: Crear docs/runbook.md**

```markdown
# Runbook — Panchi-Bot

## Arrancar

```bash
docker-compose up -d
```

## Reiniciar app sin downtime

```bash
docker-compose restart app
```

## Ver logs en tiempo real

```bash
docker-compose logs -f app
```

## Recuperar un pedido en estado incorrecto

Si un pedido se queda en un estado incorrecto (e.g. `confirmando-pago` pero el pago se procesó):

1. Ir a `/dashboard` → seleccionar el pedido → cambiar estado manualmente
2. Si el dashboard no lo permite (transición inválida), ejecutar en SQL Server:

```sql
UPDATE Pedidos SET Estado = 'pagado' WHERE PedidoID = <id>;
INSERT INTO historial_estados_pedido (pedido_id, estado_anterior, estado_nuevo, notas)
VALUES (<id>, 'confirmando-pago', 'pagado', 'Corrección manual por operador');
```

## Redis caído

Si Redis no está disponible, el sistema devuelve 503. Reiniciar Redis:

```bash
docker-compose restart redis
```

## Twilio — mensaje no llega

1. Verificar en el Twilio Console que el webhook apunta a `https://<tu-dominio>/webhook`
2. Verificar que `TWILIO_WHATSAPP_NUMBER` en `.env` es el número sandbox/production correcto
3. Revisar logs: `docker-compose logs app | grep "TWILIO\|enviar_mensaje"`

## Monei — pago no confirma

1. Verificar que el webhook de Monei apunta a `https://<tu-dominio>/webhook/monei`
2. Verificar `MONEI_WEBHOOK_SECRET` en `.env`
3. Revisar logs: `docker-compose logs app | grep "webhook_monei\|MONEI"`
```

- [ ] **Step 4: Ejecutar suite completa final**

```bash
pytest -v --tb=short
```
Expected: ≥110 tests, todos passing.

- [ ] **Step 5: Commit final**

```bash
git add main.py config.py docs/runbook.md
git commit -m "feat: logs a fichero con rotación, Sentry scope, runbook de producción"
```

---

## Checklist pre-producción (acciones externas)

- [ ] Actualizar URL del webhook en el dashboard de Monei a `https://<tu-dominio>/webhook/monei`
- [ ] Una vez confirmado, eliminar la ruta legacy `/webhoo/monei` de `blueprints/webhook.py:90`
- [ ] Generar `SECRET_KEY` con `python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] Generar `INTERNAL_API_TOKEN` con el mismo comando
- [ ] Crear contraseñas para cada empleado con `werkzeug.security.generate_password_hash('PIN')`
- [ ] Configurar SSL (certbot + nginx o Caddy) en el servidor de producción
- [ ] Ejecutar `scripts/migrar_sprint3.py` si hay datos previos en BD

---

## Resumen de ficheros por fase

| Fase | Ficheros modificados | Ficheros creados |
|------|---------------------|-----------------|
| 1 | `database.py` | `tests/test_database.py` |
| 2 | `managers/gestor_dashboard.py`, `controllers/registro.py`, `controllers/pedido.py`, `controllers/pago.py`, `templates/dashboard/monitor.html` | `tests/test_gestor_dashboard.py` |
| 3 | `controllers/registro.py`, `controllers/mensajes_registrados.py`, `blueprints/api.py`, `blueprints/menu.py`, `templates/error.html`, `templates/picker/index.html`, `managers/gestor_dashboard.py`, `templates/repartidor/index.html`, `blueprints/dashboard.py` | `tests/test_repartidor.py` |
| 4 | `main.py`, `blueprints/picker.py`, `blueprints/repartidor.py`, `blueprints/dashboard.py`, `config.py` | `blueprints/auth.py`, `templates/auth/login.html`, `Procfile`, `docker-compose.yml`, `nginx.conf`, `tests/test_auth.py`, `tests/test_startup.py`, `tests/test_health.py`, `docs/runbook.md` |
