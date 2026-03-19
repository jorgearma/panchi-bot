# Diseño — Panchi-Bot: Llevar a Producción
**Fecha:** 2026-03-19 | **Rama:** `refactorizar-estructura` | **Estado:** Aprobado

---

## Contexto

Panchi-Bot es un sistema de pedidos para restaurante vía WhatsApp (Twilio). El flujo completo existe y funciona en pruebas controladas: registro de clientes, menú web con pago online (Monei) o contra reembolso, app de picker para preparación en almacén, app de repartidor con mapa real, y dos paneles de control (dashboard de gestión + monitor en tiempo real). El sistema aún no ha salido a producción.

**Volumen esperado:** 50–200 pedidos/día (medio).

**Objetivo de este plan:** llevar el sistema de "funciona en pruebas controladas" a "listo para producción real" mediante cuatro fases ordenadas por dependencia lógica.

---

## Enfoque elegido: Por capas horizontales

Cuatro fases en orden estricto de dependencia:
1. Cerrar bugs pendientes (base de datos fiable)
2. Sistema de logs y métricas (visibilidad real del negocio)
3. Pulido de todas las interfaces (experiencia sin aristas)
4. Hardening de producción (estabilidad, resiliencia, deployment)

El motivo de este orden: las métricas no son fiables si los datos tienen bugs; la UX no tiene sentido pulir sobre una base inestable; el hardening requiere que todo lo anterior esté correcto.

---

## Fase 1 — Bugs Pendientes

**Criterio de aceptación:** `pytest` pasa al 100% (≥110 tests) después de cada fix. Ningún bug de esta lista queda abierto antes de continuar.

### Bugs de integridad

| ID | Fichero | Problema | Impacto |
|----|---------|----------|---------|
| BUG-1 | `blueprints/webhook.py` | `order_id` no se castea a `int` antes de usarlo | Pagos confirmados por Monei no actualizan el pedido |
| BUG-2 | `services/__init__.py:23` | `cache = redismanager.client` en lugar de `redismanager` | Callers reciben el cliente raw sin retry/logging del wrapper |
| BUG-3 | `services/token_service.py:17` | `generar_token_temporal` devuelve tupla en error en lugar de lanzar `ValueError` | URLs rotas del tipo `.../menu/Datos de usuario inválidos.` |
| BUG-4 | `controllers/registro.py:36` | `confirmar_direccion` devuelve `1` en lugar de `False` | Lógica de registro rota silenciosamente en casos de error |
| BUG-5 | `templates/` | `error.html` no existe | Flask lanza 500 (TemplateNotFound) en lugar de 403 |
| BUG-6 | `blueprints/menu.py:57` | `last_pedido` sin guard `None` | AttributeError en producción cuando el usuario no tiene pedidos |

### Deuda técnica bloqueante

| ID | Fichero | Problema |
|----|---------|----------|
| TD-11 | `requirements.txt` | Faltan dependencias: `shapely`, `spacy`, `sentry-sdk`, `tenacity`, `Monei` — el deploy falla al instalar |
| LEGACY-1 | `blueprints/webhook.py` | Ruta `/webhoo/monei` (typo) sigue activa — eliminar una vez Monei dashboard apunte a `/webhook/monei` |
| DB-1 | `database.py:54,76` | `Base = declarative_base()` declarado dos veces |

---

## Fase 2 — Sistema de Logs y Métricas

### 2a — Logs estructurados

Consolidar en un único `logging.basicConfig` en `create_app()`. Eliminar todos los `print()` en managers y controllers, reemplazar por `logger`. El logger emite líneas con campos: `timestamp`, `evento`, `pedido_id` (si aplica), `usuario` (si aplica), `modulo`.

**Eventos mínimos a loguear:**
- Registro nuevo completado
- Pedido iniciado / carrito confirmado / pago iniciado / pago confirmado
- Cambio de estado de pedido (con estado anterior y nuevo)
- Error de entrega / incidencia abierta
- Error de autenticación (firma Twilio, token interno)

### 2b — Métricas de negocio en el dashboard

Nueva sección en el dashboard existente (sin servicios externos). Los datos se extraen de `HistorialEstadoPedido`, que ya guarda timestamps de cada transición.

**Métricas a mostrar:**
- Pedidos por hora y por día (gráfico de barras simple)
- Tiempo medio de preparación: `en-preparacion` → `preparado`
- Tiempo medio de entrega: `en-reparto` → `entregado`
- Tasa de cancelaciones con desglose por motivo
- Ingresos del día desglosados por método de pago (cash / tarjeta / online)
- Ratio de incidencias por repartidor

### 2c — Alertas en dashboard

Warning visible (sin sonido, sin notificación push) cuando:
- Un pedido lleva más de N minutos en el mismo estado (N configurable por estado)
- Hay una incidencia abierta sin resolver

---

## Fase 3 — Pulido de Interfaces

Criterio: cada flujo se puede recorrer completo con datos reales sin errores ni estados ambiguos.

### 3a — Bot WhatsApp
- Mensajes de error claros en cada paso del registro cuando el input es inesperado
- Timeout gracioso para enlaces activos muy antiguos: mensaje explicativo en lugar de error genérico
- Revisión de ortografía y tono uniforme en todos los mensajes salientes

### 3b — Menú web
- Página `error.html` con mensaje útil según tipo de error: token inválido, pedido ya pagado, enlace caducado
- Flujo contra reembolso revisado end-to-end (cash y tarjeta en casa)
- Validación de carrito vacío antes de confirmar

### 3c — App del Picker
- Indicador claro de items pendientes vs items listos
- Aviso explícito cuando el picking está completo y el pedido puede pasar a reparto
- Estado consistente si el picker cierra la app a medias (el estado persiste en BD)

### 3d — App del Repartidor
- Flujo de cobro obligatorio (cash / tarjeta / mixto) antes de poder marcar como entregado
- Mapa con coordenadas reales: revisión de edge cases (dirección sin coordenadas, GPS no disponible)
- Flujo completo de incidencias: apertura, descripción, cierre

### 3e — Dashboard y Monitor
- Monitor de empleados: actualización automática (polling o SSE) sin recarga manual
- Asignación de repartidor: no permite asignar si ya hay uno asignado sin confirmación explícita
- Cambio de estado manual: guard contra transiciones inválidas con mensaje de error claro

---

## Fase 4 — Hardening de Producción

### 4a — Resiliencia
- Reintentos con backoff exponencial en llamadas a Twilio y Monei (usando `tenacity`)
- Timeout explícito en llamadas a Google Maps y Monei (máximo 5s)
- Si Redis no está disponible: degradación limpia (sin crash), log de alerta, funcionalidad sin estado en caché desactivada temporalmente

### 4b — Configuración
- Validación de variables de entorno obligatorias al arrancar `create_app()`: si falta alguna, fallo inmediato con mensaje claro (no fallo silencioso en primer request)
- `config.py` como única fuente de verdad para todas las variables (consolidar los módulos que leen `os.environ` directamente)
- Separación dev/prod en configuración: debug off, logs a fichero en prod

### 4c — Deployment
- `gunicorn` como servidor WSGI (no el dev server de Flask)
- `docker-compose.yml` con servicios: app + Redis + reverse proxy (nginx o caddy)
- Ruta `/health` que verifica: conexión a BD, conexión a Redis, variables críticas presentes

### 4d — Observabilidad
- Verificar que Sentry recibe errores con contexto útil (pedido_id, usuario) — ya configurado en Fase 1 de seguridad
- Rotación de logs si se escribe a fichero (evitar llenado de disco)
- Runbook mínimo: cómo arrancar, cómo reiniciar, cómo recuperar un pedido en estado incorrecto manualmente

---

## Lo que NO incluye este plan

- CI/CD automatizado
- Autenticación SSO o roles complejos
- Rediseño visual de ninguna interfaz
- Servicios externos de métricas (Grafana, Prometheus, Datadog)
- Kitchen display (`cocina/` — placeholder, fuera de scope)

---

## Orden de ejecución y dependencias

```
Fase 1 (bugs)
    └── Fase 2 (logs/métricas)   ← requiere datos fiables
            └── Fase 3 (pulido)  ← requiere visibilidad para validar
                    └── Fase 4 (hardening) ← requiere todo lo anterior correcto
```

Cada fase se valida con `pytest` al completo antes de continuar a la siguiente.
