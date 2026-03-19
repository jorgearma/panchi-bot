# Diseño — Panchi-Bot: Llevar a Producción
**Fecha:** 2026-03-19 | **Rama:** `refactorizar-estructura` | **Estado:** Aprobado (v2)

---

## Contexto

Panchi-Bot es un sistema de pedidos para restaurante vía WhatsApp (Twilio). El flujo completo existe y funciona en pruebas controladas: registro de clientes, menú web con pago online (Monei) o contra reembolso, app de picker para preparación en almacén, app de repartidor con mapa real, y dos paneles de control (dashboard de gestión + monitor en tiempo real). El sistema aún no ha salido a producción.

**Volumen esperado:** 50–200 pedidos/día (medio).

**Objetivo de este plan:** llevar el sistema de "funciona en pruebas controladas" a "listo para producción real" mediante cuatro fases ordenadas por dependencia lógica.

---

## Estado verificado del codebase (2026-03-19)

Los siguientes items del REFACTOR_PLAN.md ya están resueltos en el código actual y **no requieren trabajo**:

| Item | Estado |
|------|--------|
| BUG-1: cast `order_id` a int en webhook Monei | ✅ Resuelto — `webhook.py:128` |
| BUG-2: `cache = redismanager.client` | ✅ Resuelto — `services/__init__.py:25` lee `redismanager` |
| BUG-3: `generar_token_temporal` devuelve tupla | ✅ Resuelto — `token_service.py:18` lanza `ValueError` |
| BUG-4: `confirmar_direccion` devuelve `1` | ✅ Resuelto — `registro.py:36` retorna `False` |
| BUG-5: `error.html` no existe | ✅ Resuelto — `templates/error.html` existe |
| BUG-6: `last_pedido` sin guard None | ✅ Resuelto — `menu.py` tiene el guard |
| BUG-CRÍTICO: `nombre_usuario` vs `numero_cliente` | ✅ Resuelto — `mensajes_registrados.py:25` pasa `numero_cliente` |
| TD-11: `requirements.txt` incompleto | ✅ Resuelto — shapely, spacy, sentry-sdk, tenacity, Monei presentes |
| DB-1: `Base = declarative_base()` doble | ✅ Resuelto — única declaración en `database.py:27` |
| TD-3: Clases wrapper estáticas `Mensajeria`, `ValidacionNombre`, `ValidacionDireccion` | ✅ Resuelto — no existen en el codebase actual |
| TD-12: Múltiples `logging.basicConfig` dispersos | ✅ Resuelto — única llamada en `create_app()` (`main.py:16`) |
| SEC-1..SEC-6: Fase de seguridad | ✅ Completada en rama anterior |
| Fase 4 tests (110 passing) | ✅ Completada |

---

## Enfoque elegido: Por capas horizontales

Cuatro fases en orden estricto de dependencia:

1. **Base fiable** — cerrar los items abiertos reales que bloquean producción
2. **Visibilidad** — sistema de logs y métricas
3. **Pulido** — experiencia sin aristas en todas las interfaces
4. **Hardening** — resiliencia, configuración, autenticación de paneles, deployment

```
Fase 1 (base fiable)
    └── Fase 2 (logs/métricas)   ← requiere datos fiables
            └── Fase 3 (pulido)  ← requiere visibilidad para validar
                    └── Fase 4 (hardening) ← requiere todo lo anterior correcto
```

Cada fase se valida con `pytest` al completo antes de continuar.

---

## Fase 1 — Base Fiable

**Criterio de aceptación:** `pytest` pasa al 100% (≥110 tests) después de cada cambio. Todos los items de esta fase resueltos antes de continuar.

### Items reales abiertos

| ID | Fichero | Problema | Impacto en producción |
|----|---------|----------|-----------------------|
| AUDIT-1 | `database.py` | `AuditLog` se importa y usa en `gestor_pedidos.py` (líneas 258, 306, 413) pero no está en `conectar_bd1()`. Nota: `scripts/migrar_sprint3.py:61` ya crea la tabla condicionalmente para despliegues existentes — pero `conectar_bd1()` es la ruta autoritativa para un deploy limpio. Fix: añadir `AuditLog` al import y al `create_all` de `conectar_bd1()`. Para datos existentes, ejecutar el migration script. | En un deploy limpio: `ProgrammingError` en la primera cancelación o modificación de item desde el dashboard |
| TD-13 | `database.py:71,73` | `print()` en lugar de `logger` en `conectar_bd1()` | Logs de BD que no llegan a los ficheros de log en producción |

### Nota sobre migración de datos

El BUG-CRÍTICO (`TelefonoEntrega` con nombre en lugar de teléfono) ya está corregido en el código. Si el sistema fue usado con el código incorrecto, ejecutar antes de producción:
```sql
UPDATE p SET p.TelefonoEntrega = u.Telefono
FROM Pedidos p
JOIN Usuarios u ON p.UsuarioID = u.ID
WHERE p.TelefonoEntrega = u.Nombre;
```
Si es un deploy desde cero (sin datos previos), este paso no aplica.

---

## Fase 2 — Sistema de Logs y Métricas

### 2a — Logs estructurados

Un único `logging.basicConfig` en `create_app()` (consolidando TD-12 y TD-13 de Fase 1 como base). El logger emite líneas con campos: `timestamp`, `nivel`, `evento`, `pedido_id` (si aplica), `usuario` (si aplica), `modulo`.

**Eventos mínimos a loguear:**
- Registro nuevo completado
- Pedido iniciado / carrito confirmado / pago iniciado / pago confirmado
- Cambio de estado de pedido (estado anterior → nuevo)
- Error de entrega / incidencia abierta
- Error de autenticación (firma Twilio, token interno)

### 2b — Métricas de negocio en el dashboard

Nueva sección en el dashboard existente (sin servicios externos). Los datos se extraen directamente de `HistorialEstadoPedido`, que ya guarda timestamps de cada transición de estado.

**Métricas a mostrar:**
- Pedidos por hora y por día (gráfico de barras simple)
- Tiempo medio de preparación: `en-preparacion` → `preparado`
- Tiempo medio de entrega: `en-reparto` → `entregado`
- Tasa de cancelaciones con desglose por motivo
- Ingresos del día desglosados por método de pago (cash / tarjeta / online)
- Ratio de incidencias por repartidor

### 2c — Alertas en dashboard

Warning visible (sin notificación push) cuando:
- Un pedido lleva más de N minutos en el mismo estado (N configurable por estado en `config.py`)
- Hay una incidencia abierta sin resolver

---

## Fase 3 — Pulido de Interfaces

Criterio: cada flujo se puede recorrer completo con datos reales sin errores ni estados ambiguos.

### 3a — Bot WhatsApp
- Mensajes de error claros en cada paso del registro cuando el input es inesperado
- Timeout gracioso para enlaces activos muy antiguos: mensaje explicativo en lugar de error genérico
- Revisión de ortografía y tono uniforme en todos los mensajes salientes

### 3b — Menú web
- Flujo contra reembolso revisado end-to-end (cash y tarjeta en casa)
- Validación de carrito vacío antes de confirmar
- Mensajes de error en `error.html` diferenciados por tipo: token inválido, pedido ya pagado, enlace caducado

### 3c — App del Picker
- Indicador claro de items pendientes vs items listos
- Aviso explícito cuando el picking está completo y el pedido puede pasar a reparto
- Estado consistente si el picker cierra la app a medias (el estado persiste en BD, no en memoria)

### 3d — App del Repartidor
- Flujo de cobro (cash / tarjeta / mixto): el botón "Entregado" permanece desactivado en el frontend hasta que se complete el cobro; adicionalmente, el endpoint `marcar_entregado` añade un guard server-side: verificar que `reparto.metodo_cobro IS NOT NULL` para pedidos con `forma_pago` en efectivo o tarjeta antes de permitir la transición a `entregado`
- Mapa con coordenadas reales: manejo explícito de edge cases (dirección sin coordenadas → fallback a texto; GPS no disponible → aviso al repartidor)
- Flujo completo de incidencias: apertura, descripción, cierre

### 3e — Dashboard y Monitor
- Monitor de empleados: polling cada 15 segundos (no SSE — suficiente para 50-200 pedidos/día, sin infraestructura adicional)
- Asignación de repartidor: confirmación explícita si ya hay uno asignado
- Cambio de estado manual: guard contra transiciones inválidas con mensaje de error claro al operador

---

## Fase 4 — Hardening de Producción

### 4a — Autenticación de paneles internos (BLOQUEANTE)

`dashboard`, `picker` y `repartidor` no tienen ningún mecanismo de autenticación. En cuanto el sistema sea accesible desde internet, cualquiera puede asignar pickers, cambiar estados o marcar entregas.

**Solución mínima:** login con PIN por rol, usando sesiones Flask con `werkzeug.security` para verificar el hash (ya disponible, `Empleado.password_hash` ya está en el modelo en `models.py:191`). Tres roles: `manager` (dashboard completo), `picker` (solo picker), `repartidor` (solo repartidor). El modelo `Rol` ya existe — reutilizar.

**Binding sesión-empleado:** tras el login, la sesión almacena `session['empleado_id']`. El `empleado_id` se lee exclusivamente de la sesión en todos los blueprints afectados:

- **picker**: rutas `/picker` (línea 25), `/picker/manifest.json` (46), `/picker/mis-pedidos` (66) — actualmente usan `?id=` o `?picker_id=` como parámetro URL
- **repartidor**: rutas `/repartidor` (26), `/repartidor/manifest.json` (46), `/repartidor/mis-pedidos` (66), `/repartidor/cierre` (130), `/repartidor/cierre/datos` (138) — actualmente usan `?id=` o `?repartidor_id=`
- **dashboard**: endpoints `/cancelar`, `/eliminar-item`, `/sustituir-item` y asignaciones (líneas 165, 179, 201, 248, 269, 282) — actualmente reciben `empleado_id` del body JSON

El patrón `?id=` queda retirado. Esto impide que un empleado autenticado suplante a otro manipulando parámetros.

### 4b — Resiliencia

- Reintentos con backoff exponencial en llamadas a Twilio y Monei (usando `tenacity`, ya en requirements)
- Timeout explícito en llamadas a Google Maps y Monei: máximo 5 segundos
- Redis: si falla, el sistema loguea el error y devuelve 503 con mensaje claro. **No** se implementa degradación silenciosa — Redis es estructural para rate-limit y tokens. Hacerlo opcional requeriría refactorizar los blueprints webhook y menu, lo que está fuera del scope de esta fase. La disponibilidad de Redis es un requisito de infraestructura.

### 4c — Configuración

- Validación de variables de entorno obligatorias en `create_app()`: si falta alguna, fallo inmediato con mensaje claro (no fallo silencioso en primer request)
- `config.py` como única fuente de verdad — consolidar los módulos que leen `os.environ` directamente
- Separación dev/prod: debug off, logs a fichero en prod, `SECRET_KEY` generada con `secrets.token_hex(32)`

### 4d — Deployment

- `gunicorn` como servidor WSGI (no el dev server de Flask)
- `docker-compose.yml` con servicios: app + Redis + reverse proxy (nginx o caddy)
- Ruta `/health` que verifica: conexión a BD, conexión a Redis, variables críticas presentes — usada por el proxy para health checks

### 4e — Observabilidad

- Verificar que Sentry recibe errores con contexto útil (`pedido_id`, módulo) — ya configurado en Fase de Seguridad
- Rotación de logs si se escribe a fichero (`logging.handlers.RotatingFileHandler`)
- Runbook mínimo: cómo arrancar, cómo reiniciar, cómo recuperar manualmente un pedido en estado incorrecto

---

## Checklist pre-producción (fuera de fases, dependiente de acciones externas)

- [ ] **LEGACY-1**: Una vez el dashboard de Monei esté configurado para apuntar a `/webhook/monei`, eliminar la ruta legacy `/webhoo/monei` de `blueprints/webhook.py:90`. Trigger: confirmación de que la URL en Monei ha sido actualizada.

---

## Lo que NO incluye este plan

- CI/CD automatizado
- Rediseño visual de ninguna interfaz
- Servicios externos de métricas (Grafana, Prometheus, Datadog)
- Degradación silenciosa de Redis (requiere refactor arquitectónico fuera de scope)
- Kitchen display (`cocina/` — placeholder, fuera de scope)
- Decisión de proveedor cloud (pendiente de decisión del usuario)
