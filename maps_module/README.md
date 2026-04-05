# maps_module

Módulo de validación geográfica para Panchi-Bot. Valida que una dirección enviada por un usuario de WhatsApp existe en Tarancón y es entregable (tiene número de portal).

Diseñado para vivir dentro del monolito pero extraíble como microservicio independiente sin cambios de contrato.

---

## Qué hace

Cuando un usuario escribe su dirección durante el registro, este módulo:

1. **Normaliza** el texto (expande abreviaciones, corrige variantes conocidas)
2. **Geocodifica** con Google Maps API dentro del contexto de Tarancón
3. **Valida** que las coordenadas caen dentro del polígono de reparto
4. **Comprueba** que el resultado es una dirección entregable (no solo el nombre del pueblo)
5. **Sugiere** la calle correcta si Google no la encuentra (búsqueda difusa contra el catálogo)
6. **Autocorrige** silenciosamente: si hay sugerencia con alta confianza, reintenta con Google y pregunta al usuario si es correcta

---

## Flujo completo

```
usuario escribe "avda pablo yglesias 5"
        │
        ▼
limpiar_direccion()
  "avda" → "avenida"
  resultado: "avenida pablo iglesias 5"
        │
        ▼
Google Maps API
  contexto: "16400 Tarancón, Cuenca, España"
        │
        ├─── ✅ Encuentra y valida
        │         ▼
        │    validar_coordenadas() — ¿está dentro del polígono?
        │         ▼
        │    ¿es street_address / premise / subpremise?
        │         ▼
        │    devuelve (True, "Avenida de Pablo Iglesias 5, Tarancón...", None)
        │
        └─── ❌ Falla (no encontrada, fuera de zona, sin número)
                  ▼
             sugerir_calle() — búsqueda difusa en calles_tarancon.json
                  │
                  ├─── score alto (≥86, alta confianza)
                  │         ▼
                  │    construye "avenida de pablo iglesias 5"
                  │    reintenta con Google Maps
                  │         ▼
                  │    ✅ válida → pregunta al usuario "¿Es esta tu dirección?"
                  │    ❌ falla  → mensaje con sugerencia de texto
                  │
                  ├─── score medio (72–85)
                  │         ▼
                  │    mensaje: "¿Te refieres a Avenida de Pablo Iglesias?"
                  │
                  └─── score bajo (<72) o fuera de zona
                            ▼
                       mensaje genérico con ejemplos
```

---

## Archivos

| Archivo | Responsabilidad |
|---------|-----------------|
| `service.py` | Lógica principal: normalización, geocodificación, validación de polígono |
| `street_suggest.py` | Búsqueda difusa de calles con `rapidfuzz` |
| `territories.json` | Configuración del territorio: polígono, tipos válidos, normalizaciones |
| `calles_tarancon.json` | Catálogo oficial de calles de Tarancón (311 calles) |
| `schemas.py` | Modelos Pydantic para los endpoints REST |
| `blueprint.py` | Blueprint Flask con endpoints `/api/v1/maps/*` |
| `__init__.py` | API pública del módulo |

---

## API pública (uso desde controllers)

```python
from maps_module import validar_direccion, sugerir_calle

# Validación completa
valida, formateada, motivo = validar_direccion("calle mayor 5")

# Motivos de rechazo posibles:
# "no_encontrada"      — Google no devuelve resultados
# "fuera_de_zona"      — coordenadas fuera del polígono
# "demasiado_generica" — Google devuelve el pueblo, no una dirección
# "sin_numero"         — dentro del polígono pero sin número de portal
# "error_api"          — fallo de red tras 3 reintentos

# Sugerencia difusa
sugerencia, alta_confianza = sugerir_calle("avda pablo yglesias")
# sugerencia = "avenida de pablo iglesias"
# alta_confianza = True si score >= 86, False si score 72-85, None si < 72
```

---

## Endpoints REST (blueprint registrado en el monolito)

```
POST /api/v1/maps/validate-address
  body: { "address": "calle mayor 5", "territory": "tarancon" }

POST /api/v1/maps/geocode
  body: { "address": "calle mayor 5" }

POST /api/v1/maps/validate-coords
  body: { "lat": 40.001, "lng": -3.010 }

GET  /api/v1/maps/territories
```

Estos endpoints ya tienen el contrato del futuro microservicio. Para extraerlo: copiar el módulo a un repo nuevo con un `main.py` de Flask y un `Dockerfile`.

---

## Configuración del territorio (`territories.json`)

El polígono, los tipos de dirección válidos y las normalizaciones están externalizados en `territories.json`. Para añadir un nuevo territorio de reparto, añadir una entrada al array `territories` sin tocar código.

Campos relevantes:

| Campo | Descripción |
|-------|-------------|
| `polygon` | Coordenadas `[lng, lat]` del polígono de reparto |
| `valid_address_types` | Tipos de resultado de Google que se aceptan (`street_address`, `premise`, `subpremise`) |
| `excluded_result_types` | Tipos de Google que se rechazan siempre (`locality`, `administrative_area`...) |
| `normalizations` | Reglas regex aplicadas al input antes de mandarlo a Google |

---

## Scripts de diagnóstico

```bash
# Prueba el suggest contra todo el catálogo (sin API de Google)
python maps_module/scripts/test_sugerencias.py
python maps_module/scripts/test_sugerencias.py --solo-fallos

# Prueba cada calle contra Google Maps (requiere GOOGLE_MAPS_API_KEY en .env)
python maps_module/scripts/test_calles_google.py --limit 20    # prueba rápida
python maps_module/scripts/test_calles_google.py --solo-fallos # solo problemas
```

---

## Añadir un nuevo pueblo

1. Añadir entrada en `territories.json` con su polígono, CP, tipos válidos y normalizaciones
2. Añadir su catálogo de calles como `calles_<pueblo>.json` en esta carpeta
3. Actualizar `street_suggest.py` para cargar el catálogo según el territory
4. Pasar `territory="nuevo_pueblo"` en las llamadas a `validar_direccion`
