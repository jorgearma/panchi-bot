---
name: refactorizar
description: Use when code has logic in the wrong architectural layer, a file mixes responsibilities, or code is hard to follow for new developers or AI agents. Do NOT use for style-only changes, adding features, or fixing bugs.
---

# Refactorizar — Solo lo justo

Refactoriza el código indicado moviendo cada pieza a su capa correcta. Sin cambios de comportamiento, sin extras, sin mejoras no pedidas.

## Arquitectura de referencia (panchi-bot)

```
blueprints/    → Solo routing HTTP. Valida esquema, llama al controller, devuelve respuesta.
controllers/   → Lógica de negocio y máquinas de estado. No toca DB ni APIs externas directamente.
managers/      → Acceso a DB (SQLAlchemy) y Redis. Sin lógica de negocio.
services/      → Adaptadores de APIs externas (WhatsApp, Maps, Monei, tokens). Sin lógica de negocio.
schemas/       → Validación de entrada con Pydantic.
utils/         → Helpers sin estado, sin dependencias de dominio.
```

**Problemas conocidos** (prioridad alta si el archivo indicado es uno de estos):
- `blueprints/api.py` — tiene lógica de negocio que pertenece a controllers
- `gestor_dashboard.py` — god object de 121 KB, extraer a submódulos en managers
- `blueprints/picker.py`, `repartidor.py`, `dashboard.py` — `threading.Thread` sin manejo de errores

## Proceso (4 pasos, sin saltar ninguno)

### Paso 1 — Leer y clasificar

Lee el archivo indicado. Para cada bloque de código escribe mentalmente:
- ¿Qué hace este bloque?
- ¿En qué capa vive ahora?
- ¿En qué capa debería vivir según la arquitectura?

Si ya está en la capa correcta: **para aquí**. No refactorices lo que ya está bien.

### Paso 2 — Listar movimientos mínimos

Haz una lista de los movimientos necesarios, en orden:

```
MOVER: <descripción breve del bloque>
  Desde: blueprints/api.py
  Hacia: controllers/pago.py (función existente o nueva)
  Motivo: lógica de negocio fuera de blueprint
```

**Regla de oro:** Si un movimiento no corrige una violación de capa, no está en la lista.

No incluyas:
- Renombrar variables por estilo
- Añadir docstrings o comentarios
- Extraer helpers "por si acaso"
- Cambiar el manejo de errores salvo que sea el motivo de la refactorización

### Paso 3 — Ejecutar

Para cada movimiento de la lista:

1. **Lee los archivos destino** antes de modificar nada.
2. Mueve el bloque al archivo destino **sin cambiar su comportamiento**.
3. En el archivo origen, reemplaza el bloque con una llamada al destino.
4. Verifica que los imports queden correctos en ambos archivos.
5. No toques nada más en esos archivos.

**Si el destino no existe:** crea el archivo mínimo necesario. Solo las funciones que estás moviendo, nada más.

**Si el movimiento genera un conflicto de dependencias circular:** documéntalo y para. No lo resuelvas improvisando.

### Paso 4 — Verificar

Ejecuta los tests:

```bash
pytest -v --tb=short
```

Si algo falla:
- Revisa si el fallo es por el movimiento (imports, nombres)
- Corrige solo eso
- No arregles tests preexistentes que ya fallaban antes de tu cambio

Si los tests no cubren el código movido, no añadas tests nuevos en este paso — eso es trabajo separado.

## Qué reportar al terminar

```
Archivos modificados:
  - blueprints/api.py         (extraído: validar_pedido, crear_pago)
  - controllers/pago.py       (añadido: validar_pedido, crear_pago)

Movimientos realizados: 2
Comportamiento cambiado: NO
Tests: X pasados, Y fallados (Y igual que antes del cambio / Y nuevos — indicar)

Pendiente fuera de alcance:
  - [si detectaste algo que necesita refactorización pero no era el objetivo]
```

## Señales de que te estás pasando

Para inmediatamente si te encuentras:
- Renombrando funciones o variables sin moverlas de capa
- Dividiendo una función "porque es larga"
- Añadiendo logging, métricas o manejo de errores nuevo
- Modificando un archivo que no aparece en la lista de movimientos
- Haciendo más de un ciclo de "pequeña mejora extra"

Esas acciones son trabajo separado. Este skill es solo para mover código a su capa correcta.
