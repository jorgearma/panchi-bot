# ACOPLAMIENTO CRÍTICO — PANCHI-BOT

## Resumen Ejecutivo
El análisis revela **7 patrones de acoplamiento fuerte** que rompen **silenciosamente** bajo:
- **Alta concurrencia** (2+ requests simultáneos)
- **Refactors** (cambios en `auth.py`, `states.py`, Redis keys)
- **Tests** (global state, imports circulares, mocks)

---

## 🔴 CRÍTICO — Severidad 5/5

### 1. `_notificar()` triplicada sin sincronización

**Archivos**: 
- `blueprints/picker.py:14-24`
- `blueprints/repartidor.py:15-24`
- `blueprints/dashboard/_common.py:23-34`

**El problema**:
```python
def _notificar(telefono: str, mensaje: str) -> None:
    if not telefono:
        return
    def _enviar():
        try:
            enviar_mensaje_whatsapp(mensaje, telefono)
        except Exception as exc:
            logger.error("...")
    Thread(target=_enviar, daemon=True).start()  # ← SIN LOCK
```

**Por qué es invisible**:
- La función está **triplicada idénticamente** en 3 módulos. Si alguien cambia `blueprints/picker.py`, las otras dos copias quedan obsoletas.
- `Thread(daemon=True)` sin `join()` ni sincronización. En alta carga (100 pedidos/min), se lanzan 100+ threads sin control.
- Si Twilio explota, el thread hijo falla en background y el cliente HTTP ya cerró — **nadie sabe que falló**.
- **Causa**: En refactor del pick/reparto, alguien copy-paste el código en vez de importarlo.

**Impacto**:
- Race conditions en notificaciones
- Fuga de threads
- Mensajes duplicados o perdidos
- Silencio completo en fallo de Twilio

**Fix**:
```python
# services/notification_service.py
from concurrent.futures import ThreadPoolExecutor
import queue

_executor = ThreadPoolExecutor(max_workers=5)

def notificar(telefono: str, mensaje: str) -> None:
    """Envia WhatsApp en thread pool con sincronización."""
    if not telefono:
        return
    future = _executor.submit(_enviar_whatsapp, mensaje, telefono)
    # Opcional: track resultado en queue para logging

def _enviar_whatsapp(mensaje: str, telefono: str) -> None:
    try:
        enviar_mensaje_whatsapp(mensaje, telefono)
    except Exception as exc:
        logger.error("Error enviando WhatsApp a %s: %s", telefono, exc)

# En blueprints/picker.py, repartidor.py, dashboard/_common.py:
from services.notification_service import notificar
# Reemplazar _notificar(telefono, mensaje) por notificar(telefono, mensaje)
```

---

### 2. Stock descuento sin lock (Lost Update)

**Archivo**: `managers/dashboard/picking_flujo.py:200-226`

**El problema**:
```python
def descontar_stock(producto_id, cantidad=1):
    def _descontar():
        _s = SessionLocal()
        try:
            producto = _s.query(Producto).filter_by(ProductoID=producto_id).first()
            stock_anterior = producto.stock
            if stock_anterior > 0:
                producto.stock = stock_anterior - 1  # ← RACE CONDITION
            _s.commit()
        except SQLAlchemyError as e:
            _s.rollback()
        finally:
            _s.close()
    Thread(target=_descontar, daemon=True).start()  # ← ASYNC SIN ESPERA
```

**Por qué es invisible**:
- **Check-then-act no atómico**: Lee stock, decrementa, escribe. Entre lectura y escritura, otro thread puede cambiar el valor.
- **Lost update**: 2 threads con stock=5: ambos leen 5, decrementan a 4, ambos escriben 4. **Resultado: stock=4 en vez de 3.**
- **Async sin espera**: El thread hijo descuenta stock mientras el request HTTP ya respondió. Si hay error, nadie lo sabe.
- **Sin `SELECT ... FOR UPDATE`**: SQLAlchemy no bloquea la fila durante lectura.

**Impacto**:
- Overselling de productos
- Inconsistencia entre inventario real y DB
- Pedidos quedan sin stock físico pero pagado
- Cliente recibe producto inconsistente

**Fix**:
```python
def descontar_stock_atomico(producto_id: int) -> bool:
    """Descuento atómico usando SELECT ... FOR UPDATE."""
    s = SessionLocal()
    try:
        # Bloquea la fila hasta fin de transacción
        producto = s.query(Producto).filter_by(ProductoID=producto_id).with_for_update().first()
        if not producto or producto.stock <= 0:
            s.rollback()
            return False
        
        producto.stock -= 1
        s.add(LogMovimientoStock(ProductoID=producto_id, tipo='DESCUENTO_PICKING'))
        s.commit()
        return True
    except SQLAlchemyError as e:
        s.rollback()
        logger.error("Error descuento atómico: %s", e)
        return False
    finally:
        s.close()

# En blueprints/picker.py:
if descontar_stock_atomico(producto_id):
    # Proceder con seguridad
else:
    # Stock insuficiente — responder error al cliente
```

---

### 3. `_actualizar_estado_operativo()` race condition

**Archivo**: `managers/dashboard/_base.py:21-46`

**El problema**:
```python
def _actualizar_estado_operativo(self, empleado_id: int, nuevo_estado: str) -> None:
    def _ejecutar():
        s = SessionLocal()
        try:
            empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id).first()
            if empleado and empleado.estado_operativo not in self._ESTADOS_PROTEGIDOS:
                empleado.estado_operativo = nuevo_estado  # ← RACE CONDITION
            s.commit()
    Thread(target=_ejecutar, daemon=True).start()  # ← ASYNC SIN ESPERAA
```

**Por qué es invisible**:
- **2 requests simultáneos** marcan el mismo picker "disponible". Ambos leen su estado, ambos lo actualizan. **Último en ganar pero ambos creen que ganaron.**
- **Sin `SELECT ... FOR UPDATE`**: No hay bloqueo pessimistic.
- **Sin mecanismo de protección**: Aunque existe `_ESTADOS_PROTEGIDOS`, no hay Lock que lo enforce.
- **Lazy discovery**: La corrupción ocurre pero no hay crash — solo estado inconsistente.

**Impacto**:
- Pickers marcados "disponible" cuando están en pausa
- Repartidores asignados aunque están desconectados
- Sistema de despacho no ve la inconsistencia

**Fix**:
```python
# managers/dashboard/_base.py
from threading import Lock

class GestorDashboardBase:
    def __init__(self):
        self._lock_estado_operativo = {}  # por empleado_id
    
    def _actualizar_estado_operativo_sincronizado(self, empleado_id: int, nuevo_estado: str) -> bool:
        """Actualiza estado con lock por empleado."""
        if empleado_id not in self._lock_estado_operativo:
            self._lock_estado_operativo[empleado_id] = Lock()
        
        with self._lock_estado_operativo[empleado_id]:
            s = SessionLocal()
            try:
                empleado = s.query(Empleado).filter_by(EmpleadoID=empleado_id).with_for_update().first()
                if empleado and empleado.estado_operativo not in self._ESTADOS_PROTEGIDOS:
                    empleado.estado_operativo = nuevo_estado
                    s.commit()
                    return True
                return False
            except SQLAlchemyError as e:
                s.rollback()
                logger.error("Error actualizando estado: %s", e)
                return False
            finally:
                s.close()
```

---

## 🟠 ALTO — Severidad 4/5

### 4. Imports cruzados entre blueprints

**Patrón**: 8 blueprints importan `requiere_rol` de `blueprints.auth`:
- `blueprints/picker.py:7`
- `blueprints/repartidor.py:8`
- `blueprints/empleado.py:6`
- `blueprints/metricas_operacion.py:4`
- `blueprints/metricas_analitica.py:6`
- `blueprints/dashboard/picking.py:5`
- `blueprints/dashboard/pedidos.py:5`
- `blueprints/dashboard/reparto.py:5`

**El problema**:
```python
# En blueprints/picker.py
from blueprints.auth import requiere_rol

@bp.route('/estado', methods=['POST'])
@requiere_rol('picker')  # ← Acoplamiento a auth.py
def cambiar_estado():
    ...
```

**Por qué es invisible**:
- Los blueprints **NO deberían importar de otros blueprints**. Crea una jerarquía implícita: `auth.py` → 8 blueprints.
- Si alguien refactoriza `auth.py` (ej: renombra a `autenticacion.py`), los 8 archivos explotan.
- El decorador usa `session.get('rol')` directamente, acoplando auth a Flask Session. Si cambias a JWT, todos los 8 se rompen.

**Impacto**:
- Refactors de autenticación rompen silenciosamente
- Imposible testear blueprints sin `auth.py`
- Ciclos implícitos (si `auth.py` importa de `picker.py`, tienes un ciclo)

**Fix**:
```python
# Opción 1: Mover decorador a `utils/auth_decorators.py`
# utils/auth_decorators.py
from functools import wraps
from flask import session, abort

def requiere_rol(*roles_permitidos):
    def decorador(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            rol = session.get('rol')
            if rol not in roles_permitidos:
                abort(403)
            return f(*args, **kwargs)
        return wrapper
    return decorador

# En blueprints/picker.py
from utils.auth_decorators import requiere_rol
@requiere_rol('picker')
def cambiar_estado():
    ...

# Opción 2: Usar middleware en Flask app
# main.py
app.before_request(check_auth)
def check_auth():
    # Validar rol basado en route + sesión
```

---

### 5. `GestorEmpleado` importado dinámicamente en metrics

**Archivo**: `managers/metricas/empleados_mixin.py:74-76, 138`

**El problema**:
```python
def rendimiento_empleados(self, desde, hasta):
    try:
        from managers.gestor_empleado import GestorEmpleado  # ← LATE BINDING
        ge = GestorEmpleado()  # ← AD-HOC, sin inyección
        punt_data = ge.puntualidad_empleado(...)
```

**Por qué es invisible**:
- **Late binding**: El import ocurre DENTRO del método. Si `GestorEmpleado` falla a importar, no lo sabes hasta que ejecutas `rendimiento_empleados()`.
- **Sin inyección**: `GestorEmpleado()` se instancia ad-hoc. Si su `__init__` cambia (ej: requiere `session_factory`), explota.
- **No mockeable**: En tests, no hay forma de inyectar un mock de `GestorEmpleado`. Tienes que parchear `managers.gestor_empleado` globalmente.
- **Ciclo implícito**: Si `GestorEmpleado` → `GestorMetricas` → `GestorEmpleado`, no está documentado.

**Impacto**:
- Fallos tarde en ejecución (no al importar)
- Tests frágiles y dependientes de módulo global
- Refactors de `GestorEmpleado` rompen sin avisar

**Fix**:
```python
# managers/metricas/empleados_mixin.py
class GestorMetricasEmpleadosMixin:
    def __init__(self, gestor_empleado=None):
        self.gestor_empleado = gestor_empleado or GestorEmpleado()
    
    def rendimiento_empleados(self, desde, hasta):
        """Usa inyección en vez de import dinámico."""
        try:
            punt_data = self.gestor_empleado.puntualidad_empleado(...)
            # ...

# En blueprints/metricas_operacion.py
from managers.metricas import GestorMetricasOperacion
from managers.gestor_empleado import GestorEmpleado

gestor = GestorMetricasOperacion(
    gestor_empleado=GestorEmpleado()
)
resultado = gestor.rendimiento_empleados(...)
```

---

### 6. Hardcode de flujo de estados en múltiples lugares

**Ubicaciones**:
- `blueprints/menu/navegacion.py:73-84` (valida ENLACE → ENLACE2)
- `blueprints/webhook.py:138` (valida Monei → PAGADO)
- `managers/dashboard/picking_flujo.py:58-66` (valida → EN_PREPARACION)
- Múltiples managers con `if estado == EstadoPedido.ENLACE2`

**El problema**:
```python
# blueprints/menu/navegacion.py
if estado == EstadoPedido.ENLACE:
    return render_template('quiniela.html', ...)
elif estado == EstadoPedido.ENLACE2:
    pedido_id = last_pedido.redisID
    return redirect(f'/confirmacion_pago?pedido_id={pedido_id}')

# blueprints/webhook.py
if data.get('status') == 'SUCCEEDED':
    gestor_pedidos.procesar_pago_confirmado(...)
```

**Por qué es invisible**:
- **Lógica de flujo esparcida**: Si añades un estado nuevo (`ENLACE3`), tienes que actualizar `navegacion.py`, `webhook.py`, `picking_flujo.py`, **y cualquier otro lugar que tenga hardcodes**.
- **Sin validación centralizada**: Cada blueprint/manager valida sus propias transiciones. Si alguien edita `states.py` pero se olvida de actualizar `webhook.py`, hay divergencia.
- **Sin constantes**: Si cambias `EstadoPedido.ENLACE2.value` de `"ENLACE2"` a `"ENLACE_2"`, los hardcodes quedan obsoletos.

**Impacto**:
- Fallos silenciosos al añadir estados
- Inconsistencia entre `states.py` y la lógica real
- Imposible entender el flujo sin buscar en 5+ archivos

**Fix**:
```python
# states.py — CENTRALIZAR TODAS LAS TRANSICIONES
class EstadoTransicion:
    # Definir qué transiciones son válidas
    VALIDAS = {
        EstadoPedido.PENDIENTE: [EstadoPedido.ENLACE],
        EstadoPedido.ENLACE: [EstadoPedido.ENLACE2],
        EstadoPedido.ENLACE2: [EstadoPedido.CONFIRMANDO_PAGO],
        EstadoPedido.CONFIRMANDO_PAGO: [EstadoPedido.PAGADO, EstadoPedido.CANCELADO],
        EstadoPedido.PAGADO: [EstadoPedido.EN_PREPARACION, EstadoPedido.CANCELADO],
        # ...
    }
    
    @staticmethod
    def es_transicion_valida(estado_actual, estado_nuevo):
        return estado_nuevo in EstadoTransicion.VALIDAS.get(estado_actual, [])

# En blueprints/menu/navegacion.py
from states import EstadoPedido, EstadoTransicion

if estado == EstadoPedido.ENLACE and EstadoTransicion.es_transicion_valida(estado, EstadoPedido.ENLACE2):
    return redirect(f'/confirmacion_pago?pedido_id={pedido_id}')

# En managers/dashboard/picking_flujo.py
if EstadoTransicion.es_transicion_valida(pedido.Estado, EstadoPedido.EN_PREPARACION):
    pedido.Estado = EstadoPedido.EN_PREPARACION
```

---

### 7. Twilio `_client` global sin lock

**Archivo**: `services/whatsapp_service.py:11-19`

**El problema**:
```python
_client = None

def _get_client():
    global _client
    if _client is None:
        _client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _client
```

**Por qué es invisible**:
- **Global mutable state**: Singleton global sin sincronización.
- **Race condition**: Si 2 threads llaman a `_get_client()` simultáneamente en el `if _client is None`, crean 2 clientes.
- **Sin invalidación**: Si `config.TWILIO_ACCOUNT_SID` cambia en runtime, el cliente global sigue usando las credenciales viejas.
- **Difícil de testear**: En tests, tienes que parchear el módulo globalmente.

**Impacto**:
- Tests paralelos crean múltiples clientes
- Cambio de credenciales en runtime no toma efecto
- Overhead de creación de cliente duplicado

**Fix**:
```python
# services/whatsapp_service.py
from threading import Lock

_client = None
_client_lock = Lock()

def _get_client():
    global _client
    with _client_lock:
        if _client is None:
            _client = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
    return _client

# O mejor: usar una clase
class TwilioClientSingleton:
    _instance = None
    _lock = Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = Client(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN)
        return cls._instance
```

---

## 🟡 MEDIO — Severidad 3/5

### 8. Redis keys inconsistentes (sin namespace centralizado)

**Ubicaciones**:
- `managers/estado_usuario.py:24` — usa raw `numero_cliente` como clave
- `managers/gestor_redis.py:67` — usa `f"bloqueo:{numero}"`
- `services/token_service.py:29` — usa raw `token` como clave
- `blueprints/menu/navegacion.py:29` — usa raw `token`

**El problema**:
```python
# managers/estado_usuario.py
estado = self.redismanager.get(self.numero_cliente)  # ← Key: "123456789"

# managers/gestor_redis.py
key = f"bloqueo:{numero}"  # ← Key: "bloqueo:123456789"

# services/token_service.py
redismanager.set(token, json.dumps(...))  # ← Key: "uuid-token"
```

**Por qué es invisible**:
- **Inconsistencia de namespaces**: `EstadoUsuario` usa raw numero, `gestor_redis` usa `bloqueo:` prefix. **¿Cuál es la convención?**
- **Sin centralización**: Si cambias la estrategia de keys (ej: `user:{numero}` vs `numero`), tienes que buscar en múltiples archivos.
- **Colisiones potenciales**: Si alguien hace `redismanager.get("123456789")`, obtiene el estado del usuario. Si hay un token llamado `"123456789"`, conflicto.

**Impacto**:
- Colisiones de keys bajo alta concurrencia
- Confusión en qué contiene cada key
- Migración de estrategia es costosa

**Fix**:
```python
# constants/redis_keys.py
class RedisKey:
    """Centraliza TODAS las keys de Redis con namespaces consistentes."""
    
    # Prefijos por dominio
    USER = "user"
    TOKEN = "token"
    LOCK = "lock"
    CACHE = "cache"
    
    @staticmethod
    def user_state(numero: str) -> str:
        return f"{RedisKey.USER}:{numero}:state"
    
    @staticmethod
    def user_lock(numero: str) -> str:
        return f"{RedisKey.LOCK}:{numero}"
    
    @staticmethod
    def menu_token(token: str) -> str:
        return f"{RedisKey.TOKEN}:{token}"
    
    @staticmethod
    def cache_key(tipo: str, id: int) -> str:
        return f"{RedisKey.CACHE}:{tipo}:{id}"

# En managers/estado_usuario.py
from constants.redis_keys import RedisKey
estado = self.redismanager.get(RedisKey.user_state(self.numero_cliente))

# En managers/gestor_redis.py
key = RedisKey.user_lock(numero)

# En services/token_service.py
redismanager.set(RedisKey.menu_token(token), json.dumps(...))
```

---

## 📋 TABLA DE ACCIÓN

| Patrón | Severidad | Archivo | Fix Esfuerzo | Prueba Recomendada |
|--------|-----------|---------|-------------|-------------------|
| `_notificar()` triplicada | 5/5 | picker, repartidor, _common | 2h | Tests concurrentes (10 threads) |
| Stock descuento sin lock | 5/5 | picking_flujo.py | 3h | Test: 2 threads, mismo producto |
| Estado operativo race | 5/5 | _base.py | 2h | Test: 2 requests → cambio simultáneo |
| Imports de blueprints | 4/5 | auth.py → 8 blueprints | 4h | Refactor a utils/auth.py |
| `GestorEmpleado` late binding | 4/5 | metricas/empleados_mixin.py | 1h | Inyección en `__init__` |
| Hardcode estados flujo | 4/5 | navegacion, webhook, picking | 5h | Centralizar en `EstadoTransicion` |
| Twilio `_client` global | 4/5 | whatsapp_service.py | 1h | Lock en `_get_client()` |
| Redis keys inconsistentes | 3/5 | 4+ archivos | 2h | Constantes en `redis_keys.py` |

---

## 🚀 Plan de Remediación por Fase

### Fase 1 (URGENTE — Semana 1)
1. **Stock descuento** — Cambiar a `SELECT ... FOR UPDATE` (evita overselling)
2. **Estado operativo** — Agregar locks por empleado (evita asignación incorrecta)
3. **`_notificar()` triplicada** — Centralizar en ThreadPoolExecutor (evita fuga de threads)

### Fase 2 (IMPORTANTE — Semana 2)
4. Hardcode de estados → Centralizar en `EstadoTransicion`
5. Redis keys inconsistentes → `constants/redis_keys.py`
6. Twilio `_client` → Thread-safe con Lock

### Fase 3 (MEJORA — Semana 3)
7. Imports de blueprints → Extraer a `utils/auth.py`
8. `GestorEmpleado` late binding → Inyección en `__init__`

---

## 📝 Testing

**Agregar tests de concurrencia** en `tests/test_concurrency.py`:

```python
import pytest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

def test_stock_descuento_atomico_concurrente():
    """2 threads decrementan el mismo stock — debe ser atómico."""
    produto_id = 1
    
    def descontar():
        descontar_stock_atomico(producto_id)
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(descontar) for _ in range(2)]
        for f in futures:
            f.result()
    
    # Verificar que stock se decrementó 2 veces, no 1
    assert get_stock(producto_id) == original_stock - 2
```

---

## 📌 Conclusión

El acoplamiento fuerte más peligroso es **el invisible**: funciones triplicadas, global state sin sincronización, imports dinámicos. Estos rompen bajo carga o refactor sin crash obvio. La remediación debe priorizarse por **Fase 1** (críticos de datos) antes de cualquier feature nueva.
