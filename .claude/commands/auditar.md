---
name: auditar
description: Auditoría técnica estricta de un archivo: responsabilidad única, acoplamiento, validación, errores, seguridad, consistencia de estado, duplicados, rendimiento, observabilidad y testabilidad. Genera un informe en docs/.
---

# Auditar — Revisión técnica estricta

Realiza una auditoría real del archivo indicado en `$ARGUMENTS`. No una opinión general, no una refactorización completa.

## Restricciones obligatorias

- Analiza **solo el archivo indicado** y las dependencias directas necesarias para entenderlo.
- No te disperses por todo el repositorio.
- No propongas reescribir la arquitectura.
- Si algo no se puede confirmar con el archivo y sus dependencias directas, márcalo explícitamente como **"posible riesgo no confirmado"**.

## Proceso (4 pasos)

### Paso 1 — Leer el archivo y sus dependencias directas

1. Lee el archivo indicado completo.
2. Identifica sus imports. Lee **solo** los archivos que necesitas para entender la lógica del archivo auditado:
   - El manager o servicio que llama
   - El schema que valida
   - El estado o enum que usa
3. Para. No sigas la cadena más allá de lo necesario.

### Paso 2 — Analizar con estas 10 lentes (sin saltarte ninguna)

Para cada lente, busca evidencia concreta en el código (números de línea):

1. **Responsabilidad única** — ¿El archivo mezcla routing, lógica de negocio, acceso a DB o utilidades?
2. **Acoplamiento y dependencias** — ¿Imports lazy dentro de funciones? ¿Dependencias ocultas? ¿Globals?
3. **Validación de inputs** — ¿Se valida todo lo que viene de fuera (usuario, webhook, API)?
4. **Manejo de errores** — ¿Hay excepciones tragadas? ¿Logs inútiles ("ocurrió un error")? ¿Paths sin try/except?
5. **Seguridad** — ¿Input del usuario llega sin sanitizar a DB/shell/log? ¿HMAC o tokens verificados?
6. **Consistencia de estado** — ¿Puede quedar estado parcial en Redis o DB tras un fallo? ¿Se limpia el estado al terminar?
7. **Idempotencia / duplicados** — ¿Pueden ejecutarse inserts o acciones críticas dos veces ante un reintento?
8. **Rendimiento** — ¿Hay lecturas redundantes de Redis o DB? ¿Queries dentro de loops?
9. **Observabilidad** — ¿Los paths de error tienen logging? ¿Los eventos de negocio clave tienen `logger.info`?
10. **Testabilidad** — ¿Hay imports lazy, globals o dependencias no inyectables que impiden mockear?

**Busca especialmente:**
- Mezcla de capas (HTTP + negocio + DB + utilidades en el mismo lugar)
- Estados inválidos o mal protegidos tras un fallo
- Posibles duplicados de inserts, pagos o pedidos ante reintentos del webhook de Meta/Twilio
- Falta de validación en datos del usuario o del webhook
- Excepciones capturadas y descartadas sin log útil
- Retorno de HTTP 4xx/5xx ante errores de validación de usuario (Meta reintenta ante no-2xx)
- `threading.Thread` sin manejo de errores (patrón conocido en este proyecto)
- Código que no se puede testear sin una DB o Redis real

### Paso 3 — Construir el informe

Usa **exactamente** este formato markdown:

```markdown
# Auditoría de `<ruta/del/archivo.py>`

> Auditoría técnica estricta. Fecha: <fecha actual>.
> Archivos analizados: <lista de archivos leídos>.

---

## 1. Rol del archivo

**Responsabilidad principal:**
**Qué debería hacer:**
**Qué no debería hacer:**
**Dependencias clave:**
**Nivel de criticidad:** Bajo / Medio / Alto / Crítico

---

## 2. Lo que hace bien

[Lista de aspectos correctos, concretos y con referencia a líneas si aplica]

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** diseño / seguridad / rendimiento / consistencia / errores / testabilidad / observabilidad
**Severidad:** Baja / Media / Alta / Crítica

**Problema:**
**Evidencia:** (cita el código con número de línea)
**Impacto real:**
**Recomendación mínima concreta:**

[Repetir para cada hallazgo numerado]

---

## 4. Riesgos principales si no se toca

[Tabla: Riesgo | Escenario concreto]

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)
### Qué NO tocar todavía

---

## 6. Tests que deberían existir

[Lista de nombres de test y qué verifican]

---

## 7. Veredicto final

**Estado general del archivo:**
**¿Bloquea crecimiento?**
**¿Bloquea testeo?**
**¿Tiene riesgo operativo real?**
```

### Paso 4 — Guardar el informe

Determina el nombre del archivo de salida a partir de la ruta del archivo auditado:
- `controllers/registro.py` → `docs/auditoria_controllers_registro.md`
- `blueprints/webhook.py` → `docs/auditoria_blueprints_webhook.md`
- `managers/estado_usuario.py` → `docs/auditoria_managers_estado_usuario.md`

Guarda el informe completo en `docs/` con ese nombre.

## Arquitectura de referencia (panchi-bot)

```
blueprints/    → Solo routing HTTP. Valida esquema, llama al controller, devuelve respuesta. Sin lógica de negocio.
controllers/   → Lógica de negocio y máquinas de estado. No toca DB ni APIs externas directamente.
managers/      → Acceso a DB (SQLAlchemy) y Redis. Sin lógica de negocio.
services/      → Adaptadores de APIs externas (WhatsApp, Maps, Monei, tokens). Sin lógica de negocio.
schemas/       → Validación de entrada con Pydantic.
utils/         → Helpers sin estado, sin dependencias de dominio.
maps_module/   → Validación de direcciones. Diseñado como microservicio extraíble.
```

**Problemas conocidos en el proyecto** (mencionarlos si aparecen en el archivo auditado):
- `gestor_dashboard.py` — god object de 121 KB, no añadir más lógica
- `blueprints/api/` — tiene lógica de negocio que pertenece a controllers
- `blueprints/picker.py`, `repartidor.py`, `dashboard/` — `threading.Thread` sin manejo de errores
- `/webhoo/monei` — typo de ruta que coexiste con `/webhook/monei`, no replicar el patrón

**Patrones de riesgo conocidos:**
- Meta/Twilio reintenta el webhook si no recibe 2xx — devolver 4xx ante input inválido del usuario provoca procesamiento doble
- Redis no tiene TTL configurado en todas las claves — estados pueden quedar huérfanos
- `tenacity` en managers protege contra caídas de SQL Server — no eliminarlo

## Señales de que te estás pasando

Para inmediatamente si te encuentras:
- Leyendo archivos que no son dependencias directas del archivo auditado
- Proponiendo una refactorización completa en lugar de cambios mínimos
- Añadiendo hallazgos sin evidencia concreta en el código
- Sugiriendo cambios de estilo o nomenclatura como hallazgos
