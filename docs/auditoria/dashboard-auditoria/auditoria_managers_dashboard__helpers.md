# Auditoría de `managers/dashboard/_helpers.py`

> Auditoría técnica estricta. Fecha: 2026-04-08.
> Archivos analizados: `managers/dashboard/_helpers.py`, `states.py`.

---

## 1. Rol del archivo

**Responsabilidad principal:** Módulo de constantes y funciones helper puras compartidas por todos los mixins del dashboard y por `managers/metricas/empleados_mixin.py`. Contiene: serialización de datetimes a ISO 8601, cálculo de duración de pickings y repartos, coordenadas geográficas de referencia, mapa de colores de estado, umbrales de retraso y lista de estados operativos y de picking.

**Qué debería hacer:** Proveer utilidades sin estado, sin efectos secundarios, sin acceso a DB ni Redis. Funciones puras y constantes de configuración de dominio.

**Qué no debería hacer:** Acceder a DB, importar Flask, gestionar sesiones, ni contener lógica de negocio condicional.

**Dependencias clave:**
- `states.EstadoPedido` — única dependencia externa.

**Nivel de criticidad:** Medio — un cambio incorrecto aquí (p.ej. en `_UMBRALES_RETRASO` o `_ESTADOS_OPERATIVOS`) afecta silenciosamente la detección de retrasos y el filtrado del panel operativo en todos los mixins que los consumen.

---

## 2. Lo que hace bien

- **Funciones completamente puras** (líneas 8–27): `_dur_picking`, `_dur_reparto` e `_iso` no tienen efectos secundarios, no acceden a estado global y son trivialmente testeables.
- **Manejo de None explícito** (líneas 10, 17, 27): las tres funciones devuelven `None` cuando los campos opcionales no están rellenos, en lugar de lanzar excepciones o devolver valores engañosos.
- **Comentario de motivación en `_iso`** (líneas 23–26): explica exactamente por qué se añade la `Z` (offset de timezone en browsers), lo que previene que alguien "limpie" el sufijo sin entender las consecuencias.
- **Constantes derivadas de enums** (líneas 34–64): `_COLORES_ESTADO`, `_UMBRALES_RETRASO`, `_ESTADOS_OPERATIVOS` y `_ESTADOS_LISTOS_PARA_PICKING` usan `EstadoPedido.X.value` en lugar de strings literales, garantizando que un renombramiento del enum rompa el módulo en lugar de silenciar el error.
- **Docstring de propósito de módulo** (línea 1–3): menciona explícitamente que también es importado por `managers/metricas/empleados_mixin.py`, señalando el contrato de estabilidad que deben mantener estas constantes.
- **Sin dependencias de runtime pesadas**: el único import es `states.EstadoPedido`, lo que hace el módulo cargable en cualquier contexto (tests unitarios, scripts de utilidad, workers).

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** diseño / responsabilidad única
**Severidad:** Baja

**Problema:** `_TARANCON_LAT` y `_TARANCON_LNG` (líneas 31–32) son coordenadas geográficas de un municipio específico. Su presencia en un módulo de helpers del dashboard los convierte en la fuente de verdad de configuración geográfica del sistema. Sin embargo, `maps_module/territories.json` ya contiene configuración territorial. Tener coordenadas de referencia en dos lugares distintos (o potencialmente inconsistentes) es un riesgo de divergencia silenciosa.

**Evidencia:**
```python
# líneas 31-32
_TARANCON_LAT = 40.0041
_TARANCON_LNG = -2.9980
```

**Impacto real:** Bajo hoy si las coordenadas solo se usan para centrar el mapa en el dashboard. Si alguien las usa para validar cobertura de entrega, entraría en conflicto con el polígono de `maps_module`.

**Recomendación mínima concreta:** Añadir un comentario que indique que estas coordenadas son solo para centrado visual del mapa del dashboard, no para validación de cobertura. Alternativamente, leerlas de `maps_module/territories.json` mediante una función en `maps_module` para tener una sola fuente de verdad.

---

### Hallazgo 2

**Tipo:** diseño / mantenibilidad
**Severidad:** Baja

**Problema:** `_COLORES_ESTADO` (líneas 34–40) contiene valores de presentación (colores CSS hex) en un módulo de managers. Los colores son decisiones de UI que pertenecen a la capa de presentación (templates o un módulo de configuración de frontend), no a la capa de acceso a datos.

**Evidencia:**
```python
# líneas 34-40
_COLORES_ESTADO = {
    EstadoPedido.PAGADO.value:           "#10b981",
    EstadoPedido.CONTRA_REEMBOLSO.value: "#8b5cf6",
    ...
}
```

**Impacto real:** Bajo en términos de correctitud. Si el diseñador cambia el color de un estado, debe modificar un archivo de managers en lugar de un archivo de estilos o configuración de UI, lo que viola el principio de menor sorpresa para futuros mantenedores.

**Recomendación mínima concreta:** Mover `_COLORES_ESTADO` a un archivo de configuración de presentación (p.ej. `utils/dashboard_ui.py` o directamente en un bloque JavaScript del template base del dashboard) en una futura iteración. No es urgente.

---

### Hallazgo 3

**Tipo:** validación de inputs
**Severidad:** Baja

**Problema:** `_dur_picking` y `_dur_reparto` no validan que `completado_en >= iniciado_en` (o `hora_entrega_real >= hora_salida`). Si hay datos corruptos en DB con timestamps invertidos, las funciones devolverán una duración negativa en minutos sin advertencia.

**Evidencia:**
```python
# línea 11
return (pk.completado_en - pk.iniciado_en).total_seconds() / 60
# línea 18
return (r.hora_entrega_real - r.hora_salida).total_seconds() / 60
```

**Impacto real:** Bajo si los timestamps los genera únicamente el sistema (no hay input manual de datetimes). Si hay una migración de datos, corrección manual en DB, o bug en la escritura de `completado_en`, el dashboard mostraría duraciones negativas sin que nadie lo detecte fácilmente.

**Recomendación mínima concreta:**
```python
def _dur_picking(pk) -> float | None:
    if pk.iniciado_en and pk.completado_en:
        delta = (pk.completado_en - pk.iniciado_en).total_seconds() / 60
        return delta if delta >= 0 else None  # guard contra timestamps corruptos
    return None
```

---

### Hallazgo 4

**Tipo:** diseño / mantenibilidad
**Severidad:** Baja

**Problema:** `_UMBRALES_RETRASO` (líneas 43–49) mezcla tres conceptos en cada tupla: tiempo en minutos, nivel de severidad de alerta (`"warning"` / `"error"`) y mensaje descriptivo. La estructura de tupla plana es frágil: si se añade un cuarto elemento (p.ej. acción recomendada), hay que actualizar todos los accesos por índice en los mixins que la consumen.

**Evidencia:**
```python
# líneas 44-49
_UMBRALES_RETRASO = {
    EstadoPedido.PAGADO.value: (10, "warning", "pagado sin iniciar picking"),
    ...
}
```

**Impacto real:** Bajo hoy (solo 5 entradas, estructura estable). Riesgo de mantenibilidad si crece.

**Recomendación mínima concreta:** Definir un `NamedTuple` o `dataclass`:
```python
from typing import NamedTuple
class UmbralRetraso(NamedTuple):
    minutos: int
    nivel: str   # "warning" | "error"
    mensaje: str
```
Esto hace los accesos autodocumentados (`umbral.minutos` en lugar de `umbral[0]`) y permite añadir campos sin romper código existente.

---

### Hallazgo 5

**Tipo:** observabilidad
**Severidad:** Baja

**Problema:** El módulo no tiene ningún logging. Esto es correcto para funciones puras y constantes. Sin embargo, si `_ESTADOS_OPERATIVOS` o `_UMBRALES_RETRASO` se cargan con valores de enum que no existen (por un futuro cambio en `states.py`), el error se manifestará lejos del punto de definición.

**Evidencia:** No aplica directamente — es una observación estructural.

**Impacto real:** Muy bajo. El uso de `.value` en las keys garantiza que un cambio en el enum rompe el import del módulo inmediatamente (fallo rápido).

**Recomendación mínima concreta:** Ninguna acción inmediata necesaria. El patrón de usar `.value` como key ya es el fallo-rápido correcto.

---

### Hallazgo 6

**Tipo:** testabilidad
**Severidad:** Baja

**Problema:** No existe ningún test para `_dur_picking`, `_dur_reparto` ni `_iso`. Son funciones triviales pero su comportamiento con `None`, timestamps negativos o datetimes sin tzinfo no está cubierto formalmente.

**Evidencia:** Ausencia de tests — verificado por contexto del repositorio.

**Impacto real:** Bajo hoy. Si se modifica `_iso` para añadir timezone awareness (p.ej. soportar datetimes con tzinfo) sin tests de regresión, el cambio podría silenciosamente romper la serialización para todos los clientes del dashboard.

**Recomendación mínima concreta:** Añadir un fichero `tests/test_dashboard_helpers.py` con al menos 5 casos (ver sección 6).

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| Divergencia de coordenadas geográficas | Un operador actualiza el polígono de cobertura en `maps_module/territories.json` pero olvida actualizar `_TARANCON_LAT/_LNG`; el mapa del dashboard centra en coordenadas desactualizadas |
| Duración negativa silenciosa | Una migración de datos escribe `completado_en` con un valor anterior a `iniciado_en`; el dashboard muestra "–8.3 min" en la tarjeta del picker sin alarma ni log |
| Fragilidad de `_UMBRALES_RETRASO` por índice | Un mixin accede a `umbral[2]` (mensaje); alguien añade un segundo elemento de severidad entre `umbral[1]` y `umbral[2]`; todos los accesos por índice devuelven el valor incorrecto sin error en runtime |
| Colores de UI acoplados a managers | Un cambio de branding requiere editar `managers/dashboard/_helpers.py`, confundiendo a desarrolladores que buscan estilos en templates o CSS |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **Añadir guard de duración negativa en `_dur_picking` y `_dur_reparto`** — previene datos engañosos en el dashboard con un cambio de 2 líneas. Bajo riesgo de regresión.
2. **Convertir `_UMBRALES_RETRASO` a `NamedTuple`** — mejora mantenibilidad sin cambiar comportamiento. Requiere actualizar los accesos por índice en los mixins consumidores (búsqueda global de `[0]`, `[1]`, `[2]` sobre el diccionario).
3. **Añadir comentario en `_TARANCON_LAT/_LNG`** aclarando que son solo para centrado visual y no para validación de cobertura.

### Qué NO tocar todavía

- Las funciones `_dur_picking`, `_dur_reparto` e `_iso` — su lógica es correcta y el único gap es el guard de negativo.
- `_ESTADOS_OPERATIVOS` y `_ESTADOS_LISTOS_PARA_PICKING` — listas correctas, derivadas de enums, estables.
- La estructura de `_COLORES_ESTADO` — mover colores a UI es una mejora válida pero de baja urgencia; hacerlo requiere coordinar con templates.

---

## 6. Tests que deberían existir

- `test_dur_picking_ambos_campos_rellenos` — verifica que devuelve el número correcto de minutos dado un mock con `iniciado_en` y `completado_en` concretos.
- `test_dur_picking_campo_none_devuelve_none` — verifica que con `iniciado_en=None` o `completado_en=None` devuelve `None`.
- `test_dur_picking_timestamps_invertidos_devuelve_none` — verifica el guard de duración negativa (una vez implementado).
- `test_dur_reparto_calculo_correcto` — análogo para `hora_salida` → `hora_entrega_real`.
- `test_iso_datetime_devuelve_Z` — verifica que un datetime cualquiera produce una cadena terminada en `Z`.
- `test_iso_none_devuelve_none` — verifica que `_iso(None)` devuelve `None` sin excepción.
- `test_umbrales_retraso_todas_las_claves_son_estados_validos` — verifica que todas las keys de `_UMBRALES_RETRASO` son valores válidos de `EstadoPedido`.
- `test_estados_operativos_no_contiene_estados_terminales` — verifica que `ENTREGADO`, `CANCELADO` y `REEMBOLSADO` no están en `_ESTADOS_OPERATIVOS`.

---

## 7. Veredicto final

**Estado general del archivo:** Muy bueno. Es el archivo más limpio y bien diseñado del conjunto auditado: funciones puras, sin efectos secundarios, dependencia mínima, constantes derivadas de enums. Los hallazgos son oportunidades de mejora menores, no problemas activos.

**¿Bloquea crecimiento?** No. Su diseño modular y sin estado facilita añadir nuevas constantes o helpers sin riesgo de regresión.

**¿Bloquea testeo?** No. Las funciones son trivialmente testeables con objetos mock simples. La ausencia de tests es una deuda menor, no un impedimento estructural.

**¿Tiene riesgo operativo real?** Bajo. El único riesgo concreto es la duración negativa silenciosa ante datos corruptos, y la divergencia potencial de coordenadas geográficas. Ninguno de los dos es crítico en el estado actual del sistema.
