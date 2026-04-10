# Hallazgos: managers/dashboard/reparto_asignacion.py

Fecha: 2026-04-10

## Contexto

Este mixin forma parte de `GestorDashboard` y sirve al dashboard de operaciones donde el jefe/admin puede observar el estado del reparto en tiempo real. El dashboard refresca cada 10 segundos y tiene máximo 2 usuarios simultáneos por restaurante.

---

## Métodos y su responsabilidad real

| Método | Consumidor | Veredicto |
|---|---|---|
| `repartidores()` | `blueprints/dashboard/reparto.py` | Correcto — monitorización del jefe |
| `asignar_repartidor()` | `blueprints/dashboard/reparto.py` | Correcto — acción manual del admin si lo considera oportuno |
| `repartos_sin_asignar()` | `blueprints/repartidor.py` | **Dominio incorrecto** |
| `reclamar_reparto()` | `blueprints/repartidor.py` | **Dominio incorrecto** |

---

## Problema identificado: cruce de dominios

`repartos_sin_asignar` y `reclamar_reparto` están en el gestor del dashboard pero su consumidor real es el blueprint del repartidor (`/repartidor/cola` y `/repartidor/cola/coger/<id>`). El flujo del repartidor está usando `gestor_dashboard` para sus propias operaciones.

Estos dos métodos pertenecen al dominio del repartidor, no al dominio del dashboard.

**Impacto actual:** bajo — funciona correctamente. El riesgo es de mantenimiento: cualquier cambio en `gestor_dashboard` puede afectar sin querer el flujo del repartidor, y viceversa.

---

## Refactor pendiente (no urgente)

Mover `repartos_sin_asignar` y `reclamar_reparto` fuera de `gestor_dashboard` a su propio gestor o al gestor de pedidos, y actualizar `blueprints/repartidor.py` para que apunte al gestor correcto.

No tocar hasta que haya un ciclo de refactor planificado — el cambio tiene impacto en blueprint + container + tests.

---

## Observaciones sobre las queries de `repartidores()`

- 5-6 queries por refresco, todas acotadas por fecha/estado/IDs. Carga asumible con el volumen actual.
- `_batch_repartos()` está bien implementado — evita el problema N+1 en el loop de empleados.
- Oportunidad de mejora: las queries que cargan objetos ORM completos (`Empleado`, `Pedido`) podrían seleccionar solo las columnas que el dict final usa, reduciendo datos transferidos desde SQL Server.
- `repartos_sin_asignar()` carga `Pedido.detalles` con `selectinload` solo para hacer `len()`. Un `COUNT` en BD sería más eficiente, pero dado que este método lo usa el repartidor (no el polling del dashboard), no afecta al rendimiento del refresco del jefe.
