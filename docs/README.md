# Docs

Documentación corta y práctica del proyecto.

## Objetivo

`docs/` complementa a `maps/`:

- `maps/` = visión amplia, técnica y de referencia.
- `docs/` = guías cortas para entender rápido una carpeta o flujo.

La idea es que sirva para:

- onboarding rápido,
- consultas del día a día,
- dar contexto útil a la IA sin leer todo el repo.

## Estructura actual

```text
docs/
├── README.md
└── backend/
    ├── overview.md
    ├── blueprints.md
    ├── controllers.md
    └── services.md
```

## Regla de estilo

Cada documento de `docs/` debería ser:

- corto,
- directo,
- orientado a intención de negocio,
- útil para humanos y para IA,
- sin repetir el código línea por línea.

## Relación con otras carpetas

- `blueprints/`: entrada HTTP, render, JSON, permisos.
- `controllers/`: orquestación de flujos y reglas de negocio.
- `managers/`: acceso a datos.
- `services/`: integración con sistemas externos.

## Lectura recomendada

Si quieres entender el sistema rápido:

1. `docs/backend/overview.md`
2. `docs/backend/blueprints.md`
3. `docs/backend/controllers.md`
4. `docs/backend/services.md`
5. `maps/PROJECT_MAP.md` si necesitas más profundidad

## Siguiente ampliación sugerida

Cuando quieras seguir, tiene sentido documentar en este orden:

1. `managers/`
2. flujos completos (`registro`, `pedido`, `pago`, `operación interna`)
3. reglas sensibles (`seguridad`, `webhooks`, `permisos`)
