# Start Cycle

Usa este comando como checklist manual para iniciar un ciclo desde una petición del usuario.

## Objetivo

Preparar el flujo manual `reader → build-subgraph → planner → writer` sin scripts de automatización extra.

## Instrucciones

1. Valida que el plugin tenga su manifiesto en `.claude/plugin.json`.

2. Si faltan mapas o están desactualizados, ejecuta:
   ```
   python3 .claude/hooks/analyze-repo.py
   ```

3. Recibe la peticion del usuario e invoca al agente `reader` con la herramienta **Agent** (general-purpose).
   - El prompt al reader debe ser **exactamente** este texto (reemplaza solo `[petición textual del usuario]`):

     ```
     RESTRICCIONES: PROHIBIDO Bash, Glob, Grep, Search, ls. Solo Read y Write. NO planifiques, NO propongas soluciones, NO escribas texto — solo escribe el JSON.

     Lee estos archivos siguiendo el flujo actual del reader:
     1. .claude/maps/ROUTING_MAP.json
     2. Solo los índices relevantes para la petición:
        - .claude/maps/DOMAIN_INDEX_api.json
        - .claude/maps/DOMAIN_INDEX_data.json
        - .claude/maps/DOMAIN_INDEX_ui.json
        - .claude/maps/DOMAIN_INDEX_services.json
        - .claude/maps/DOMAIN_INDEX_jobs.json
        - .claude/maps/CONTRACT_MAP.json (siempre)
        - .claude/maps/DATA_MODEL_MAP.json (solo si hace falta estructura de datos)
        - .claude/maps/TEST_MAP.json (solo si hace falta cobertura)
        - .claude/maps/DEPENDENCY_MAP.json (solo si hace falta expandir seeds)

     Después escribe .claude/runtime/reader-context.json usando el formato vigente del agente reader y del schema .claude/schemas/reader-context.json.

     Petición del operador: [petición textual del usuario]
     ```

   - **NO agregues ni quites nada** del prompt de arriba. Solo reemplaza la petición.
   - Si el reader devuelve `status: "blocked_no_maps"`, ejecuta `python3 .claude/hooks/analyze-repo.py` y vuelve a intentarlo.

4. Si quieres enriquecer el contexto antes de planificar, ejecuta:
   ```
   python3 .claude/hooks/build-subgraph.py
   ```

5. Invoca al agente `planner` con el contenido de `.claude/runtime/reader-context.json`:
   - El planner descompone el trabajo en pasos concretos.
   - Devuelve un JSON compatible con `.claude/schemas/plan.json`.
   - Guarda el resultado en `.claude/runtime/plan.json`.

6. Invoca al agente `writer` con el contenido de `.claude/runtime/plan.json`:
   - El writer transforma el plan en una guia de ejecucion.
   - Devuelve un JSON compatible con `.claude/schemas/execution-brief.json`.
   - Guarda el resultado en `.claude/runtime/execution-brief.json`.
   - Si genera vista humana, guardala en `.claude/runtime/execution-brief.md`.

7. Informa al operador:
   - Muestra un resumen del plan generado.
   - Indica los agentes seleccionados y los pasos principales.
   - Continúa con la ejecución manual paso por paso.

## Reglas

- No ejecutes agentes implementadores (frontend/backend) en este comando.
- No avances al paso siguiente si el anterior devuelve un error o JSON invalido.
- Si el reader no puede clasificar la peticion, informa al usuario y detente.
- Si el plan no tiene pasos ejecutables, indica al operador antes de llegar al writer.
