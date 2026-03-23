# Spec: PROJECT_MAP.md

**Fecha:** 2026-03-23
**Estado:** Aprobado por usuario

## Objetivo

Crear un archivo `PROJECT_MAP.md` en la raíz del repositorio que sirva como referencia técnica completa del proyecto panchi-bot, válida tanto para onboarding de nuevos desarrolladores como para consulta diaria del equipo existente.

## Audiencia

Doble audiencia: nuevos desarrolladores (onboarding) y desarrolladores existentes (referencia técnica profunda).

## Enfoque

Top-down: visión general → arquitectura → flujos → entry points → dependencias → code smells con análisis técnico completo.

## Secciones del documento

### 1. Visión General
Descripción del sistema y tabla de tecnologías usadas.

### 2. Cómo Ejecutar el Proyecto
- Requisitos previos (ODBC Driver 18, spaCy model)
- Setup local paso a paso
- Docker Compose
- Tests
- ngrok para desarrollo local

### 3. Estructura de Carpetas
Árbol con descripción de cada directorio.

### 4. Arquitectura del Sistema
- Diagrama ASCII de 5 capas (blueprints → controllers → managers → services → externos)
- Rol de Redis (3 usos distintos documentados)
- Separación flujo bot vs flujo dashboard

### 5. Entry Points
- App factory `create_app()` en `main.py`
- Tabla completa de 11 blueprints con rutas y propósito

### 6. Flujo Completo de la Aplicación
- 6.1 Registro de usuario nuevo (máquina de estados Redis)
- 6.2 Pedido completo happy path (pago online)
- 6.3 Pago en efectivo (contra reembolso)
- 6.4 Flujo operativo (picking → reparto)
- 6.5 Diagrama de estados completo del pedido

### 7. Variables de Entorno
Tabla completa con todas las variables, descripción y condición de requerimiento.

### 8. Dependencias Importantes
Tabla con versión, propósito y riesgo de cada dependencia crítica.

### 9. Posibles Problemas y Code Smells
9 problemas identificados, cada uno con: descripción del problema → riesgo concreto → sugerencia de solución:

1. `gestor_dashboard.py` God Object (121 KB)
2. `gestor_metricas.py` sobredimensionado (48 KB)
3. Threading manual sin pool ni error handling
4. Ruta typo `/webhoo/monei` activa en producción
5. Ausencia de CI/CD
6. `openai` en requirements.txt sin uso
7. Sin rate limiting en `/webhook`
8. Lógica de negocio en `blueprints/api.py`
9. Acoplamiento a SQL Server / ODBC Driver del SO

## Decisiones de diseño

- **No se incluye** lista exhaustiva de todos los archivos (evitar duplicar lo que git ya provee)
- **Se incluyen** los detalles no obvios que requieren leer múltiples archivos para entender (ej: Redis con 3 roles distintos)
- **Code smells** documentados con análisis técnico completo (problema + riesgo + sugerencia) en lugar de lista simple
- El diagrama de estados usa ASCII art para ser renderizable en cualquier editor
