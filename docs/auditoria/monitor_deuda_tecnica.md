# Deuda técnica: managers/dashboard/empleados_monitor.py

Fecha: 2026-04-10

## Problema

El archivo tiene 385 líneas y mezcla tres responsabilidades distintas:

1. **Queries a BD** — correcto para un manager
2. **Lógica de negocio en Python** — cálculo de `rendimiento` (rápido/normal/lento), `estado` (sobrecargado/activo/inactivo/sin_carga), `carga`, tiempos medios, `tiempo_inactivo_min` — esto pertenece a un controller según la arquitectura del proyecto
3. **Construcción de dicts para el front** — ensamblado de la respuesta JSON

## Por qué ocurrió

El dashboard no tiene controllers. El blueprint llama directamente al manager, así que toda la lógica de negocio ha ido acumulándose en la capa de datos por falta de una capa intermedia.

## Solución propuesta

Crear controllers de dashboard que reciban los datos crudos del manager y apliquen los cálculos y reglas de negocio antes de entregar la respuesta al blueprint.

```
blueprints/dashboard/  →  controllers/dashboard/  →  managers/dashboard/
```

## Impacto del refactor

- Crear `controllers/dashboard/monitor.py` (o similar)
- Mover los cálculos de rendimiento, estado y tiempos al controller
- El manager devuelve datos crudos; el controller los transforma
- Actualizar `blueprints/dashboard/pages.py` para pasar por el controller
- Actualizar tests afectados

## Prioridad

Baja — no afecta al funcionamiento actual. Abordar cuando haya un ciclo de refactor planificado.

---

## Mejora futura: caché Redis en `/dashboard/monitor/datos`

### Situación actual

El endpoint ejecuta ~22 queries a SQL Server en cada poll (15s). Con 2 usuarios el volumen es ~176 queries/minuto — asumible para el volumen actual.

### Cuándo aplicar

Si se escala a múltiples restaurantes con BD compartida, o si el número de usuarios del dashboard crece.

### Cómo implementarlo

```
Request → ¿clave en Redis? → SÍ  → devuelve JSON cacheado (0 queries a BD)
                            → NO  → ejecuta queries → guarda en Redis TTL 15s → devuelve
```

El TTL de 15s iguala el intervalo de polling — el usuario no percibe diferencia en frescura de datos.

### Impacto a escala

| Escenario | Sin caché | Con caché |
|---|---|---|
| 1 restaurante, 2 usuarios | ~176 queries/min | ~88 queries/min |
| 10 restaurantes, 2 usuarios c/u | ~1.760 queries/min | ~220 queries/min |

### Lo que ya existe

`container.py` exporta `cache` (gestor Redis). La infraestructura está disponible — el cambio sería ~10 líneas en `blueprints/dashboard/pages.py`, sin tocar el manager.

### Prioridad

Baja — no necesario hasta escalar más allá de 1-2 restaurantes.
