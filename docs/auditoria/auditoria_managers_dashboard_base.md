# Auditoría de `managers/dashboard/_base.py`

> Auditoría técnica estricta. Fecha: 2026-04-08.
> Archivos analizados: `managers/dashboard/_base.py`, `database.py`, `states.py`, `models.py` (extracto).

---

## 1. Rol del archivo

**Responsabilidad principal:**  
Clase base `GestorDashboardBase` que proporciona métodos helper para operaciones comunes en el dashboard: actualización de estado de empleados en background, cálculos de métricas de tiempo, carga batch de pickings y repartos.

**Qué debería hacer:**
- Acceso a BD de forma eficiente (evitar N+1, usar eager loading)
- Lógica de negocio relacionada con visualización en dashboard
- Manejo de threading para operaciones que no bloqueen respuestas HTTP

**Qué no debería hacer:**
- Lógica de negocio compleja (debe estar en controllers)
- Exponer sessiones de BD sin abstraer (privado con `_` prefix correcto)
- Asumir contratos sin validación (state machine re-entrada, valores de input)

**Dependencias clave:**
- `database.get_db()` y `database.SessionLocal` (BD)
- `models.Empleado`, `HistorialEstadoPedido`, `PickingPedido`, `Reparto`, `Pedido`
- `states.EstadoPedido`, `EstadoPicking`, `EstadoReparto`
- `threading.Thread` (operaciones async sin RQ)

**Nivel de criticidad:** **MEDIO-ALTO**  
(No es un servicio público, pero afecta el dashboard operativo que es crítico para la empresa. Los fallos en picking/reparto tracking son visibles a operadores.)

---

## 2. Lo que hace bien

1. **Evita N+1 en batch ops** (líneas 89-131): `_batch_pickings` y `_batch_repartos` usan una sola query con `joinedload()` en lugar de iterar empleado por empleado. Buena optimización.

2. **Self-join para tiempo medio** (líneas 56-87): `_tiempo_medio()` usa SQL Server `DATEDIFF` con self-join en lugar de traer todo a Python y calcular. Escalable.

3. **Sesión aislada para thread** (línea 39): `_actualizar_estado_operativo()` crea una sesión nueva en el thread con `SessionLocal()`, no reutiliza la sesión del request. Correcto, evita deadlocks.

4. **Protección de estados manuales** (líneas 24, 41-46): Usa `frozenset` y `notin_()` para no sobreescribir estados `en_pausa` y `desconectado` que el empleado controla manualmente. Buen diseño.

5. **Finally para cleanup** (línea 51-52): Sesión se cierra siempre en el thread, incluso ante exception. Evita resource leak.

6. **ORM para seguridad**: SQLAlchemy ORM evita SQL injection. No hay interpolación de strings en queries.

7. **Enum para estados**: `EstadoPedido`, `EstadoPicking`, `EstadoReparto` son enums, no strings soltos. Buena type safety.

---

## 3. Hallazgos

### Hallazgo 1: Property `session` implementa anti-patrón

**Tipo:** diseño / rendimiento  
**Severidad:** ALTA

**Problema:**  
La property `session` (líneas 18-22) hace lazy import dentro de la property cada vez que se accede:
```python
@property
def session(self):
    """Devuelve la sesión activa de base de datos."""
    from database import get_db
    return get_db()
```

Esto significa:
- El import `from database` se ejecuta cada vez que se accede a `self.session`
- La llamada a `get_db()` obtiene o crea una sesión. Cada método que use `self.session` lo recrea.
- En `_tiempo_medio()` se accede a `self.session` una sola vez (línea 65), pero el patrón sugiere que podría usarse múltiples veces.

**Evidencia:**  
- Línea 18-22: definición de property
- Líneas 65, 110, 153: acceso a `self.session` en los tres métodos que lo necesitan

**Impacto real:**
- Ineficiencia: no crítical para rendimiento pero es código derrochador
- Confusión: otros desarrolladores pueden no notar que es lazy import y pensar que es una sesión cachéada
- Testabilidad: difficil mockear sin conocer la implementación interna

**Recomendación mínima concreta:**
Hacer que `session` sea un atributo inicializado en `__init__()` si esta clase va a ser instanciada, o simplemente eliminar la property y pasar la sesión como parámetro. Pero como es clase base, probablemente se instancia en subclases. Verificar cómo se usa.

---

### Hallazgo 2: Threading daemon sin manejo robusto de errores

**Tipo:** errores / observabilidad  
**Severidad:** ALTA

**Problema:**  
El thread en `_actualizar_estado_operativo()` (línea 54) es daemon y corre en background. Cuando falla:
1. Se loga solo warning (línea 49)
2. El error no se propaga al request
3. El dashboard no sabe si la actualización funcionó
4. El operador ve estado desactualizado sin aviso

```python
Thread(target=_ejecutar, daemon=True).start()
```

Si el thread muere (SQL Server timeout, conexión drop), nadie se entera excepto logs. No hay reintentos automáticos como con RQ.

**Evidencia:**
- Línea 54: `Thread(..., daemon=True).start()`
- Línea 48-50: captura Exception pero no hay mecanismo de reintentos
- No hay `threading.Lock` o sincronización con la sesión del request

**Impacto real:**
- **Operacional**: Empleado queda con estado_operativo desactualizado. Dashboard muestra "en_reparto" pero empleado nunca fue actualizado.
- **Invisible**: No hay feedback visual al usuario que hizo clic en "pausa"

**Recomendación mínima concreta:**
1. Considera usar RQ (Redis Queue) que ya está en el proyecto (`message_queue.py`, `worker.py`) en lugar de Thread daemon. RQ reintentos automáticos.
2. Si mantienes Thread, añade logging.error + contexto (empleado_id, timestamp) y considera notificación al supervisor si falla 3 veces.
3. Devuelve al menos un booleano o Future para que el caller sepa si se encoló o falló inmediatamente.

---

### Hallazgo 3: Falta validación de inputs

**Tipo:** validación  
**Severidad:** ALTA

**Problema:**  
Los métodos no validan parámetros de entrada:

1. `_actualizar_estado_operativo(empleado_id: int, nuevo_estado: str)`:
   - `empleado_id` puede ser 0 o negativo. Solo chequea `if not empleado_id` (línea 32), que falla si `empleado_id == 0`.
   - `nuevo_estado` no se valida. ¿Qué pasa si es string vacío o None?

2. `_batch_pickings(ids: list, ...)`:
   - `ids` no se valida. ¿Puede ser None? ¿Puede contener None?
   - Si `ids = [None, 1, 2]`, SQL Server puede fallar.

3. `_batch_repartos(ids: list, ...)`:
   - Idem anterior.

**Evidencia:**
- Línea 26: firma sin validación
- Línea 32: `if not empleado_id` es insuficiente (no chequea < 0)
- Línea 89-94: `ids: list` sin type hints de contenido, sin validation
- Línea 133-138: idem

**Impacto real:**
- Si caller pasa `empleado_id = -5`, se crea query `WHERE Empleado.EmpleadoID == -5` que no falla pero no hace nada.
- Si `ids = [None, ...]`, SQL Server devuelve error, exception no capturada, genera 500 en la respuesta.

**Recomendación mínima concreta:**
```python
def _actualizar_estado_operativo(self, empleado_id: int, nuevo_estado: str) -> None:
    if not isinstance(empleado_id, int) or empleado_id <= 0:
        logger.warning("empleado_id inválido: %s", empleado_id)
        return
    if not nuevo_estado or not isinstance(nuevo_estado, str):
        logger.warning("nuevo_estado inválido: %s", nuevo_estado)
        return
    # ...

def _batch_pickings(self, ids: list[int], ...):
    if not ids or not all(isinstance(i, int) for i in ids):
        logger.warning("ids inválida: %s", ids)
        return defaultdict(lambda: {'activos': [], 'completados': []})
    # ...
```

---

### Hallazgo 4: Race condition en actualización de estado

**Tipo:** consistencia / threading  
**Severidad:** MEDIA-ALTA

**Problema:**  
El thread actualiza `estado_operativo` después de que el request haya respondido al cliente. Entre que el request lanza el thread y el thread llega a la BD, pueden pasar milisegundos. Si el empleado hace clic en otro botón o la sesión del request modifica el mismo campo, hay carrera:

**Timeline:**
1. Request lee `estado_operativo = "desconectado"`
2. Request lanza thread para update a "recibiendo_pedidos"
3. Request responde al cliente (200 OK)
4. Mientras tanto, otro request cambia el estado a "en_pausa" (manual)
5. Thread llega a BD y hace UPDATE con WHERE `estado_operativo NOT IN ('en_pausa', 'desconectado')`
6. Thread ve que es "en_pausa", no actualiza
7. Dashboard muestra "en_pausa" (correcto, el thread lo respetó)

Pero si timeline es diferente:
1. Request lanza thread para update a "recibiendo_pedidos"
2. Otro request cambia estado a "en_pausa"
3. Thread ejecuta UPDATE WHERE `estado_operativo NOT IN (...)` → falla (estado ya es "en_pausa")
4. Thread loga warning
5. El primer request nunca sabe

No es corrupción de datos pero el estado final puede no ser lo que esperaba.

**Evidencia:**
- Línea 41-46: UPDATE con WHERE protege contra re-write, pero no sincroniza con request
- Línea 54: `.start()` sin `.join()`, request no espera el thread

**Impacto real:**
- Baja probabilidad en uso normal, pero en carga alta con muchos empleados cambiando estado, puede ocurrir.
- El estado operativo muestra algo diferente a lo esperado brevemente.

**Recomendación mínima concreta:**
Si es crítico sincronizar, considera:
1. Usar RQ con `.get()` para esperar resultado (pero bloquea respuesta HTTP)
2. Devolver `{"status": "updating"}` al cliente y actualizar UI con polling
3. Confiar en la protección `notin_(estados_protegidos)` y aceptar eventual consistency

Para ahora, documentar en código que hay eventual consistency (segundos de latencia).

---

### Hallazgo 5: Falta de logging en operaciones exitosas y paths críticos

**Tipo:** observabilidad  
**Severidad:** MEDIA

**Problema:**  
Solo hay logging en error (línea 49 warning), pero no en casos exitosos o críticos:

- `_actualizar_estado_operativo`: si update funciona, no hay log. Dashboard actualiza estado, operador no sabe si el sistema lo hizo o fue caché.
- `_tiempo_medio`: sin logs. Si tarda 2 segundos, nadie sabe. Si devuelve None, ¿era error o legítimamente no hay datos?
- `_batch_pickings` / `_batch_repartos`: sin logs. Si devuelven dicts vacíos, ¿es porque no hay empleados o porque falló la query?

**Evidencia:**
- Línea 49: único log (warning)
- Líneas 56-87, 89-131, 133-176: sin logging en path exitoso

**Impacto real:**
- En producción, es imposible debuggear "¿por qué el dashboard no muestra los pickings del empleado X?"
- No hay trazabilidad de cuándo el estado fue actualizado
- Métricas de latencia no existen

**Recomendación mínima concreta:**
Añade logging en level INFO para operaciones exitosas y DEBUG para parámetros:

```python
def _actualizar_estado_operativo(self, empleado_id: int, nuevo_estado: str) -> None:
    if not empleado_id:
        return
    logger.debug(f"Encolando update estado_operativo para empleado {empleado_id} → {nuevo_estado}")
    # ...
    s.commit()
    logger.info(f"Actualizado estado_operativo empleado {empleado_id} → {nuevo_estado}")

def _tiempo_medio(self, desde: datetime, estado_inicio: EstadoPedido, estado_fin: EstadoPedido):
    result = ...
    logger.debug(f"tiempo_medio {estado_inicio.value}→{estado_fin.value} desde {desde}: {result} min")
    return result
```

---

### Hallazgo 6: Baja testabilidad — dependencia de sesión de BD real

**Tipo:** testabilidad  
**Severidad:** MEDIA

**Problema:**  
No hay forma fácil de testear estos métodos sin una BD real o mock sofisticado:

1. `_actualizar_estado_operativo` crea `SessionLocal()` en el thread. Imposible mockear sin monkeypatch de `database.SessionLocal`.
2. `_tiempo_medio` accede a `self.session` que es lazy import. Necesita monkeypatch de `database.get_db`.
3. `_batch_pickings` / `_batch_repartos` idem.

El proyecto usa `FakeRedis` para tests (per CLAUDE.md), pero no hay mención de cómo mockear BD. Probablemente los tests reales usan BD de test o mockean con `unittest.mock`.

**Evidencia:**
- Línea 21: `from database import get_db` dentro de property
- Línea 38: `from database import SessionLocal` dentro de función
- No hay dependencias inyectables

**Impacto real:**
- Tests corren lento porque necesitan BD
- Tests son frágiles si BD está lenta o caída
- No se puede ejecutar CI sin servidor SQL Server

**Recomendación mínima concreta:**
Refactor para inyección de dependencias:
```python
class GestorDashboardBase:
    def __init__(self, session_factory=None, session_getter=None):
        self._session_factory = session_factory or SessionLocal
        self._session_getter = session_getter or get_db
    
    @property
    def session(self):
        return self._session_getter()
```

Esto permite tests pasar mock:
```python
def test_actualizar_estado():
    mock_session = MagicMock()
    gestor = GestorDashboardBase(session_getter=lambda: mock_session)
    # ...
```

---

### Hallazgo 7: Dependencia en comentarios de contrato (state machine no re-entrada)

**Tipo:** diseño / documentación  
**Severidad:** BAJA

**Problema:**  
Los métodos `_tiempo_medio()` y `_batch_pickings()` tienen comentarios que dicen "el state machine no permite re-entrada":

```python
# Note: uses a SQL Server DATEDIFF self-join. If a pedido has multiple estado_inicio
# events (re-entry), all pairs are included in the average. Safe under the current
# state machine which does not allow state re-entry.
```

Esto es contrato frágil. Si alguien cambia `states.py` para permitir re-entrada, estos métodos dan resultados incorrectos sin warning.

**Evidencia:**
- Línea 62-63: comentario en `_tiempo_medio`
- Línea 104-105: comentario en `_batch_pickings`
- Línea 146-147: comentario en `_batch_repartos`

**Impacto real:**
- Bajo en producción (state machine es poco probable que cambie)
- Pero si cambia, las métricas estarán sesgadas

**Recomendación mínima concreta:**
Converter comentarios en assertions:
```python
def _tiempo_medio(self, desde: datetime, estado_inicio: EstadoPedido, estado_fin: EstadoPedido):
    """Calcula tiempo medio entre dos estados usando self-join."""
    # El state machine no permite re-entrada. Si esto cambia, la lógica debe revisarse.
    # Validar una sola vez que la transición es válida en states.py
    if not transicion_valida_pedido(estado_inicio.value, estado_fin.value):
        logger.error(f"Transición inválida: {estado_inicio.value} → {estado_fin.value}")
        return None
    # ...
```

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| **Dashboard desactualizado** | Empleado hace clic en "pausa", thread falla silenciosamente, dashboard sigue mostrando "recibiendo_pedidos". Operador asigna pedidos al empleado en pausa. |
| **SQL injection potencial via caller** | Si caller pasa `empleado_id` no validado desde URL/API, query toca DB con ID inválido (baja severidad porque es int, pero malo). |
| **Métricas incorrectas** | Si state machine permite re-entrada en futuro, `_tiempo_medio()` sumará múltiples tiempos por el mismo pedido. |
| **Latencia oculta** | Si `_batch_pickings()` tarda 5s en query lenta (millones de filas), nadie sabe. Dashboard congela. |
| **Tests lento o imposible** | Tests de Dashboard necesitan BD. CI no puede correr en contenedor sin SQL Server. |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Validación de inputs** (Hallazgo 3, media-alta severidad)
   - Añade type checking y rangos válidos a `empleado_id`, `ids`, `nuevo_estado`.
   - 20 líneas, sin cambios a BD, sin regresiones.

2. **Logging en operaciones exitosas** (Hallazgo 5, media severidad)
   - Añade `logger.info()` después de commits exitosos.
   - 10 líneas, sin cambios de lógica.

3. **Eliminar property, pasar sesión en init** (Hallazgo 1, alta severidad pero bajo esfuerzo)
   - Si clase se instancia, refactor para inyección. Si es clase base sin instancias, no hacer nada.
   - Verificar primero quién la instancia.

### Qué NO tocar todavía

- **Threading → RQ migration** (Hallazgo 2): RQ es buena idea pero es refactor grande. Hacerlo cuando hay contexto y tiempo, no ahora. Documentar como TODO.
- **Race condition sincronización** (Hallazgo 4): Baja probabilidad, mitigado por `notin_(estados_protegidos)`. Aceptar eventual consistency por ahora.
- **State machine validación** (Hallazgo 7): Conversión de comentarios en assertions puede ser overkill. Dejar comentarios por ahora.

---

## 6. Tests que deberían existir

- `test_actualizar_estado_operativo_encolado_correctamente()` — verifica que thread se lanza, no bloquea respuesta
- `test_actualizar_estado_operativo_respeta_protegidos()` — verifica que no sobreescribe "en_pausa", "desconectado"
- `test_actualizar_estado_operativo_empleado_id_invalido()` — verifica que retorna sin error si id ≤ 0
- `test_tiempo_medio_resultado_correcto()` — verifica que calcula average(datediff) correctamente con fixtures de HistorialEstadoPedido
- `test_tiempo_medio_sin_transiciones()` — verifica que devuelve None si no hay transiciones
- `test_batch_pickings_list_vacia()` — verifica que devuelve defaultdict vacío si ids=[]
- `test_batch_pickings_activos_vs_completados()` — verifica que agrupa correctamente por estado
- `test_batch_repartos_list_vacia()` — verifica que devuelve defaultdict vacío si ids=[]
- `test_batch_repartos_eager_load()` — verifica que Reparto.pedido.cliente está cargado (sin N+1)

Todos estos tests deberían mockear `SessionLocal` o usar fixture de BD de test.

---

## 7. Veredicto final

**Estado general del archivo:**  
**FUNCIONAL pero FRÁGIL**. El código hace su trabajo en casos normales pero tiene riesgos operacionales ocultos (threading sin observabilidad) y deuda técnica (baja testabilidad, lazy imports anti-patrón).

**¿Bloquea crecimiento?**  
NO, pero documentar TODO: "Considera migrar threading a RQ", "Añadir validación de inputs".

**¿Bloquea testeo?**  
SÍ, parcialmente. Tests necesitan BD real o mock sofisticado.

**¿Tiene riesgo operativo real?**  
SÍ, MEDIA severidad:
- Estados de empleado desactualizados si thread falla (invisible a operadores)
- Sin observabilidad de qué está pasando en background
- Pero: no es corrupción de datos, no afecta pagos, solo UX del dashboard

**Recomendación para producción:**  
✅ SEGURO para mantener como está mientras agregues validación + logging (Hallazgos 3, 5).  
🔄 REFACTOR urgente: migrar threading a RQ (Hallazgo 2) si dashboard es crítico operacionalmente.  
📋 DEUDA: mejorar testabilidad con inyección de dependencias (Hallazgo 6).

---

**Fecha de auditoría:** 2026-04-08  
**Criticidad del proyecto:** MEDIA (operativo, visible a operadores, no finanzas)  
**Recomendación de revisión:** Cada 6 meses o tras cambios en state machine / threading
