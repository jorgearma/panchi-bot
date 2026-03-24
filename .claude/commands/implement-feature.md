# Implement Feature

Usa este comando para ejecutar una implementacion con agentes de Claude.

## Objetivo

Transformar una solicitud aprobada en cambios concretos siguiendo el plan del plugin.

## Instrucciones

1. Valida que el plugin tenga su manifiesto en `claude/plugin.json`.

2. Lee `claude/runtime/operator-approval.json`. Si `status` no es `approved`, detente e informa al usuario:
   ```
   python3 claude/hooks/approve-plan.py approve --by "nombre"
   ```

3. Ejecuta el despacho:
   ```
   python3 claude/hooks/execute-plan.py
   ```

4. Lee `claude/runtime/execution-dispatch.json`:
   - Si `status` es `blocked`, informa al usuario el motivo y detente.
   - Si `status` es `ready`, continua.

5. Para cada agente en `selected_agents`, invoca al agente correspondiente (`frontend` o `backend`) con:
   - `claude/runtime/execution-brief.json` como guia principal
   - `claude/runtime/execution-dispatch.json` para saber que pasos ejecutar
   - `claude/runtime/execution-brief.md` solo como apoyo humano si existe

6. Cada agente ejecutor escribe su resultado en `claude/runtime/result.json` bajo su clave propia (`frontend` o `backend`).

7. Tras la ejecucion, evalua el resultado:
   - Si algun agente devuelve `status: blocked`: informa al usuario, describe que impidio la ejecucion y sugiere:
     ```
     python3 claude/hooks/recover-cycle.py --keep-plan
     ```
   - Si algun agente devuelve `status: partial`: informa al usuario que la ejecucion fue parcial y lista los artefactos generados y los pasos pendientes.
   - Si todos los agentes devuelven `status: success`: informa al usuario y sugiere continuar con la revision:
     ```
     /review-change
     ```

## Reglas

- limita cada agente al alcance de sus pasos asignados en `step_ids`
- no ejecutes agentes que no esten en `selected_agents`
- lista artefactos modificados al finalizar
- ante cualquier fallo parcial, no silencies el error — exponglo y guia al operador
