# Plan Detallado: Extracción de Maps Service a Microservicio Independiente

**Fecha:** 2026-04-04  
**Objetivo:** Desacoplar `maps_service` del monolito y convertirlo en un microservicio independiente con contrato HTTP estable.

---

## 1. Resumen Ejecutivo

**Estado actual:** `maps_service` está moderadamente acoplado (7/10) al monolito por:
- Importaciones directas desde controladores
- Reglas de negocio territorial embebidas en código
- Falta de versionado API

**Resultado deseado:** Microservicio independiente con:
- API REST versionada (`/api/v1/...`)
- Configuración externali­zada (polígono, tipos válidos, localidades)
- Contrato bien definido (JSON request/response)
- Tests aislados (sin dependencias del monolito)
- Deploying independiente en Docker

---

## 2. Fases del Plan

### **Fase 1: Diseño del Contrato API (3-4 horas)**

#### 1.1 Definir endpoints del microservicio

```
POST /api/v1/validate-address
├─ Input: { address: str, territory: str (opt) }
├─ Output: { valid: bool, formatted_address: str, coords: {lat, lng}, types: [...] }
└─ Errors: 400 (invalid), 500 (API error)

POST /api/v1/geocode
├─ Input: { address: str, territory: str (opt) }
├─ Output: { lat: float, lng: float }
└─ Errors: 400, 500

POST /api/v1/validate-coordinates
├─ Input: { lat: float, lng: float, territory: str (opt) }
├─ Output: { valid: bool, message: str }
└─ Errors: 400, 500

GET /api/v1/territories
└─ Output: { territories: [ { name, polygon, region, valid_types } ] }
```

#### 1.2 Crear schemas Pydantic para request/response

```python
# schemas/address.py
class ValidateAddressRequest(BaseModel):
    address: str
    territory: str = "tarancon"  # default

class ValidateAddressResponse(BaseModel):
    valid: bool
    formatted_address: Optional[str]
    coords: Optional[dict]  # {lat, lng}
    types: list
```

#### 1.3 Definir estructura de configuración (JSON/YAML)

```json
// config/territories.json
{
  "territories": [
    {
      "name": "tarancon",
      "region": "Cuenca",
      "polygon": [[lon, lat], ...],
      "valid_address_types": ["street_address", "premise", "subpremise"],
      "excluded_addresses": ["Tarancón, Cuenca, Spain"],
      "normalizations": [
        { "pattern": "paseo.*estacion", "replacement": "paseo estación" }
      ]
    }
  ]
}
```

### **Fase 2: Crear el Microservicio Base (4-5 horas)**

#### 2.1 Estructura de carpetas del nuevo proyecto

```
maps-microservice/
├── main.py                    # Flask app
├── requirements.txt
├── Dockerfile
├── .env.example
├── config/
│   ├── __init__.py
│   ├── territories.json       # Config externali­zada
│   └── settings.py            # Carga de env vars
├── services/
│   ├── __init__.py
│   ├── google_maps.py         # Cliente Google Maps (sin lógica)
│   └── territory_validator.py # Validación de polígono/tipos
├── schemas/
│   ├── __init__.py
│   └── address.py             # Pydantic models
├── blueprints/
│   ├── __init__.py
│   └── api.py                 # Endpoints /api/v1/*
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   └── test_validators.py
└── README.md
```

#### 2.2 Implementar endpoints base

**`blueprints/api.py`:**
```python
from flask import Blueprint, request, jsonify
from schemas.address import ValidateAddressRequest, ValidateAddressResponse
from services.territory_validator import validate_address, geocode_address

api_bp = Blueprint('api', __name__, url_prefix='/api/v1')

@api_bp.route('/validate-address', methods=['POST'])
def validate_address_endpoint():
    try:
        data = ValidateAddressRequest(**request.json)
        result = validate_address(data.address, data.territory)
        response = ValidateAddressResponse(**result)
        return response.model_dump(), 200
    except ValueError as e:
        return {"error": str(e)}, 400
    except Exception as e:
        return {"error": "Internal server error"}, 500

@api_bp.route('/geocode', methods=['POST'])
def geocode_endpoint():
    # Similar structure
    pass

@api_bp.route('/territories', methods=['GET'])
def territories_endpoint():
    # Return list of configured territories
    pass
```

#### 2.3 Extraer lógica de mapeo sin cambios

**`services/territory_validator.py`:**
```python
# Copia la lógica de validar_direccion(), geocodificar_direccion(), 
# validar_coordenadas() sin cambios inicialmente
# Refactoriza para que reciba `territory` como parámetro en lugar de hardcodear

def validate_address(address: str, territory: str = "tarancon") -> dict:
    config = load_territory_config(territory)
    # ... lógica existente ...
    return {
        "valid": True,
        "formatted_address": "...",
        "coords": {"lat": 40.0, "lng": -3.0},
        "types": [...]
    }
```

#### 2.4 Crear Dockerfile minimalista

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

CMD ["gunicorn", "-w", "2", "-b", "0.0.0.0:5001", "main:app"]
```

---

### **Fase 3: Tests del Microservicio (2-3 horas)**

#### 3.1 Mock de Google Maps API

```python
# tests/conftest.py
@pytest.fixture
def mock_google_maps(mocker):
    return mocker.patch('services.google_maps.requests.get')
```

#### 3.2 Tests de validación de dirección

```python
# tests/test_api.py
def test_validate_valid_address(client, mock_google_maps):
    mock_google_maps.return_value.json.return_value = {
        "status": "OK",
        "results": [{
            "formatted_address": "Calle Ejemplo 123, Tarancón, Cuenca, Spain",
            "geometry": {"location": {"lat": 40.001, "lng": -3.001}},
            "types": ["street_address"]
        }]
    }
    
    response = client.post('/api/v1/validate-address', 
        json={"address": "Calle Ejemplo 123"})
    
    assert response.status_code == 200
    assert response.json["valid"] == True
```

---

### **Fase 4: Adaptador en el Monolito (2-3 horas)**

#### 4.1 Crear cliente HTTP para el microservicio

**`services/maps_client.py`** (en el monolito):
```python
import requests
from config import MAPS_MICROSERVICE_URL

class MapsClient:
    def __init__(self, base_url: str = MAPS_MICROSERVICE_URL):
        self.base_url = base_url
    
    def validar_direccion(self, address: str) -> tuple:
        """Mantiene la interfaz existente, pero llama al microservicio."""
        response = requests.post(
            f"{self.base_url}/api/v1/validate-address",
            json={"address": address},
            timeout=5
        )
        if response.status_code != 200:
            return False, None
        
        data = response.json()
        return data["valid"], data.get("formatted_address")
    
    def geocodificar_direccion(self, address: str) -> tuple:
        response = requests.post(
            f"{self.base_url}/api/v1/geocode",
            json={"address": address},
            timeout=5
        )
        if response.status_code != 200:
            return None
        
        data = response.json()
        return data["lat"], data["lng"]
```

#### 4.2 Reemplazar imports en el monolito

**Cambios en `controllers/registro.py`:**
```python
# Antes:
from services.maps_service import validar_direccion

# Después:
from services.maps_client import MapsClient
maps_client = MapsClient()
validada, direccion_resultante = maps_client.validar_direccion(mensaje_cliente)
```

#### 4.3 Agregar MAPS_MICROSERVICE_URL a `.env`

```env
MAPS_MICROSERVICE_URL=http://localhost:5001
```

---

### **Fase 5: Migración Gradual (3-4 horas)**

#### 5.1 Estrategia dual (monolito + microservicio simultáneamente)

```python
# En config.py o settings
USE_MAPS_MICROSERVICE = os.getenv("USE_MAPS_MICROSERVICE", "false").lower() == "true"
```

```python
# En controllers/registro.py (adaptador inteligente)
def get_maps_validator():
    if config.USE_MAPS_MICROSERVICE:
        from services.maps_client import MapsClient
        return MapsClient()
    else:
        from services.maps_service import validar_direccion
        return maps_service

validada, _ = get_maps_validator().validar_direccion(mensaje_cliente)
```

#### 5.2 Testing side-by-side

```python
# tests/test_migration.py
def test_maps_service_and_microservice_parity():
    """Verifica que ambos retornen lo mismo para direcciones válidas."""
    from services.maps_service import validar_direccion as local_validate
    from services.maps_client import MapsClient
    
    test_addresses = ["Calle Ejemplo 123", "Paseo de la Estación 45"]
    
    for address in test_addresses:
        local_result = local_validate(address)
        remote_result = MapsClient().validar_direccion(address)
        assert local_result == remote_result
```

#### 5.3 Feature flag para rollback

```python
# blueprints/api.py (o admin endpoint)
@admin_required
def toggle_maps_service():
    current = config.USE_MAPS_MICROSERVICE
    config.USE_MAPS_MICROSERVICE = not current
    return {"status": "toggled", "now_using_microservice": not current}
```

---

### **Fase 6: Deployment e Integración (2-3 horas)**

#### 6.1 Docker Compose para stack completo

```yaml
# docker-compose.extended.yml
services:
  app:
    build: .
    ports:
      - "5000:5000"
    environment:
      - MAPS_MICROSERVICE_URL=http://maps-service:5001
      - USE_MAPS_MICROSERVICE=true
    depends_on:
      - maps-service
      - redis
      - sql-server
  
  maps-service:
    build: ./maps-microservice
    ports:
      - "5001:5001"
    environment:
      - GOOGLE_MAPS_API_KEY=${GOOGLE_MAPS_API_KEY}
    healthcheck:
      test: curl --fail http://localhost:5001/health || exit 1
      interval: 10s
      timeout: 5s
      retries: 3
```

#### 6.2 Endpoint `/health` en microservicio

```python
@app.route('/health')
def health():
    return {"status": "ok", "service": "maps-microservice"}, 200
```

#### 6.3 Documentación y README

```markdown
# Maps Microservice

## Deployment

### Local dev
\`\`\`bash
cd maps-microservice
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python main.py
\`\`\`

### Docker
\`\`\`bash
docker build -t maps-microservice:latest .
docker run -p 5001:5001 -e GOOGLE_MAPS_API_KEY=... maps-microservice:latest
\`\`\`

### Environment Variables
- `GOOGLE_MAPS_API_KEY`: (required)
- `FLASK_ENV`: development|production (default: production)
- `LOG_LEVEL`: DEBUG|INFO|WARNING (default: INFO)

## API Endpoints

See `docs/api.md` for full OpenAPI spec.
```

---

## 3. Tareas Concretas (Orden de Ejecución)

| # | Tarea | Duración est. | Bloqueadores | Notas |
|---|-------|---------------|--------------|-------|
| 1.1 | Diseñar schemas JSON de request/response | 1h | Ninguno | Use Pydantic para validación |
| 1.2 | Crear estructura territory config | 1h | 1.1 | Ej: tarancon.json |
| 1.3 | Definir endpoints en spec/OpenAPI (opcional) | 1h | 1.1, 1.2 | Ayuda a documentar |
| 2.1 | Scaffolding del proyecto microservicio | 30m | Ninguno | Usar Flask |
| 2.2 | Implementar endpoints base | 2h | 2.1, 1.1 | POST /validate-address, /geocode, GET /territories |
| 2.3 | Extraer y adaptar lógica de maps_service.py | 1.5h | 2.2 | Refactorizar para parametrizar territory |
| 2.4 | Dockerfile y .env.example | 30m | 2.3 | Usar alpine/slim base image |
| 3.1 | Fixtures de mocking (conftest.py) | 1h | 2.4 | Mock Google Maps requests |
| 3.2 | Tests unitarios de validadores | 1.5h | 3.1 | Cobertura mínima 80% |
| 4.1 | MapsClient en monolito | 1h | 3.2 | Wrapper HTTP sobre microservicio |
| 4.2 | Reemplazar imports en controllers | 1.5h | 4.1 | registro.py, pedido.py |
| 4.3 | Feature flag USE_MAPS_MICROSERVICE | 30m | 4.2 | Default: false (mantiene maps_service) |
| 5.1 | Tests de paridad local vs remoto | 1h | 4.3 | Verifica que retornen lo mismo |
| 5.2 | Integración en docker-compose.yml | 30m | 5.1 | Agregar servicio maps-service |
| 6.1 | Documentación de deployment | 1h | 5.2 | README, API spec, guía operacional |
| **TOTAL** | | **~17-18 horas** | | Pasos 1-4 críticos; 5-6 adicionales |

---

## 4. Puntos de Atención

### 4.1 Manejo de errores
- ¿Qué pasa si el microservicio no responde? → Fallback a maps_service local (feature flag)
- ¿Timeout? → Reintentar con backoff exponencial (tenacity)
- ¿Rate limit Google Maps? → Implementar en ambos (local + micro)

### 4.2 Latencia
- Llamada HTTP extra: +50-100ms esperado
- Evaluar si es tolerable para el flujo de registro (síncrono)
- Considerar caché en Redis si hay hot paths

### 4.3 Versionado de API
- `/api/v1/` desde el inicio para permitir cambios futuros
- Schema registry para cambios incompatibles

### 4.4 Autenticación inter-servicios (futuro)
- Por ahora: API sin auth (puerto 5001 interno)
- Considerar JWT o API key si se expone externamente

### 4.5 Tests en el monolito
- Los tests actuales mockan directamente `services.maps_service.validar_direccion`
- Necesitarán adaptarse si migramos a MapsClient
- Alternativa: mantener mock en maps_client para no romper tests

---

## 5. Criterios de Éxito

✅ Microservicio desplegado e independiente (en Docker)  
✅ Monolito puede llamar al microservicio sin cambios de interfaz para el usuario  
✅ Feature flag permite rollback a maps_service local en < 2 minutos  
✅ Tests de ambos servicios pasan y verifican paridad  
✅ Documentación clara para future deployments  
✅ Reducción de acoplamiento: de 7/10 → 2/10 (interface HTTP, no importación)

---

## 6. Próximos Pasos Sugeridos

1. **Aprobación del plan** → Revisar con stakeholders (ops, devs)
2. **Crear rama** → `feature/maps-microservice-extraction`
3. **Ejecutar Fase 1** → Diseño de schemas (baja inversión, validar antes de código)
4. **Ejecutar Fases 2-3** → Microservicio + tests (puede hacerse en paralelo a refactoring monolito)
5. **Ejecutar Fases 4-5** → Integración y migration (cuidado: validar paridad antes de flip flag)
6. **Fase 6** → Deploy en staging, luego prod (una vez aprobado)

---

## Notas Finales

- **No eliminar `maps_service.py`** hasta estar 100% seguros de que funciona en remoto
- **Logs**: asegurarse que ambos servicios loguean en la misma salida (stdout/stderr) para observabilidad
- **Monitoreo**: agregar alertas en `/health` del microservicio
- **Rollback plan**: estar preparado para desactivar flag y volver a maps_service local en segundos

