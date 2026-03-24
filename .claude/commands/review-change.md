# Review Change

Usa este comando para revisar una implementacion finalizada.

## Objetivo

Encontrar errores, regresiones y riesgos antes de dar por bueno el cambio.

## Instrucciones

1. Valida que el plugin tenga su manifiesto en `claude/plugin.json`.

2. Genera el despacho al reviewer ejecutando:
   ```
   python3 claude/hooks/dispatch-reviewer.py
   ```

3. Lee `claude/runtime/reviewer-dispatch.json`:
   - Si `status` es `blocked`, informa al usuario el motivo y detente. No invoques al reviewer sin resultado disponible.
   - Si `status` es `ready`, continua.

4. Invoca al agente `reviewer` pasandole:
   - `claude/runtime/plan.json`
   - `claude/runtime/execution-brief.json`
   - `claude/runtime/execution-dispatch.json`
   - `claude/runtime/result.json`
   - `claude/runtime/reviewer-dispatch.json`

5. El reviewer analiza el resultado contra el plan y devuelve un JSON compatible con `claude/schemas/review.json`.

6. Guarda el resultado en `claude/runtime/review.json`.

7. Muestra al operador el estado de la revision y los findings principales.

## Reglas

- no invoques al reviewer si `reviewer-dispatch.json` tiene `status: blocked`
- prioriza problemas funcionales sobre detalles cosmeticos
- si el resultado tiene agentes en estado `partial` o `blocked`, incluyelo como contexto al reviewer
