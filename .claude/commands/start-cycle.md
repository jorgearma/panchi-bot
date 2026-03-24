# Start Cycle

Usa este comando para iniciar un nuevo ciclo de planificacion desde una peticion del usuario.

## Objetivo

Orquestar el flujo completo desde la peticion del usuario hasta dejar el plan listo para aprobacion del operador.

## Instrucciones

1. Valida que el plugin tenga su manifiesto en `claude/plugin.json`.

2. Si hay un ciclo anterior en curso, ejecuta primero:
   ```
   python3 claude/hooks/recover-cycle.py
   ```
   Confirma con el usuario antes de resetear si `claude/runtime/operator-approval.json` tiene `status: approved` o si `claude/runtime/result.json` existe.

3. Recibe la peticion del usuario e invoca al agente `reader`:
   - Pasa la peticion completa al reader.
   - El reader clasifica el dominio, activa los readers especializados necesarios y devuelve un JSON compatible con `claude/schemas/reader-context.json`.
   - Guarda el resultado en `claude/runtime/reader-context.json`.

4. Invoca al agente `planner` con el contenido de `claude/runtime/reader-context.json`:
   - El planner descompone el trabajo en pasos concretos.
   - Devuelve un JSON compatible con `claude/schemas/plan.json`.
   - Guarda el resultado en `claude/runtime/plan.json`.

5. Invoca al agente `writer` con el contenido de `claude/runtime/plan.json`:
   - El writer transforma el plan en una guia de ejecucion.
   - Devuelve un JSON compatible con `claude/schemas/execution-brief.json`.
   - Guarda el resultado en `claude/runtime/execution-brief.json`.
   - Si genera vista humana, guardala en `claude/runtime/execution-brief.md`.

6. Informa al operador:
   - Muestra un resumen del plan generado.
   - Indica los agentes seleccionados y los pasos principales.
   - Indica que debe aprobar o rechazar antes de ejecutar:
     ```
     python3 claude/hooks/approve-plan.py approve --by "nombre"
     python3 claude/hooks/approve-plan.py reject --by "nombre" --notes "motivo"
     ```

## Reglas

- No ejecutes agentes implementadores (frontend/backend) en este comando.
- No avances al paso siguiente si el anterior devuelve un error o JSON invalido.
- Si el reader no puede clasificar la peticion, informa al usuario y detente.
- Si el plan no tiene pasos ejecutables, indica al operador antes de llegar al writer.
