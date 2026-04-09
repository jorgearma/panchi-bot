# Auditoría de `blueprints/auth.py`

> Auditoría técnica estricta. Fecha: 2026-04-07.
> Archivos analizados: `blueprints/auth.py`, `services/auth_service.py`, `managers/empleado/profile_roles_mixin.py` (método `limpiar_rol_activo`).

---

## 1. Rol del archivo

**Responsabilidad principal:** Routing HTTP para autenticación de empleados (`/auth/login`, `/auth/logout`, `/auth/manifest.json`) y definición de los decoradores de autorización `requiere_rol` y `requiere_autenticacion`.

**Qué debería hacer:** Recibir la petición, validar presencia de campos, delegar verificación de credenciales al servicio, gestionar la sesión Flask y devolver la respuesta HTTP.

**Qué no debería hacer:** Contener lógica de negocio, acceder a DB directamente, ni mutar estado de sesión dentro de decoradores de autorización.

**Dependencias clave:** `services/auth_service.py` (verificación de credenciales), `container.gestor_empleado` (limpieza de rol activo en logout).

**Nivel de criticidad:** Alto — controla acceso a todo el panel operativo.

---

## 2. Lo que hace bien

- Separación correcta: verificación de credenciales completamente delegada a `auth_service.login()` (línea 38).
- `session.clear()` antes de escribir nuevos datos de sesión (línea 45) — previene session fixation.
- Logging estructurado con `empleado_id` en logout (línea 63) y en el servicio (auth_service líneas 42, 46, 64).
- Soporte de contenido dual (JSON y form) en login sin duplicar lógica (líneas 29-36).
- `requiere_rol` y `requiere_autenticacion` redirigen GET no-JSON a login en lugar de devolver 401 (líneas 73-74, 92-93) — UX correcta.
- Logout limpia el `rol_activo` en DB para forzar check-in en el próximo turno (líneas 60-61).

---

## 3. Hallazgos

### Hallazgo 1

**Tipo:** errores / observabilidad
**Severidad:** Alta

**Problema:** En `auth_service.login()`, la excepción de DB se traga sin ningún log.

**Evidencia:**
```python
# auth_service.py líneas 36-39
try:
    empleado = _get_empleado_by_email(email)
except Exception:
    empleado = None
```

**Impacto real:** Una caída de SQL Server durante el login se presenta al usuario como "Credenciales incorrectas" y no genera ninguna alerta. El sistema aparenta funcionar cuando en realidad tiene la DB caída. Completamente invisible en producción.

**Recomendación mínima concreta:**
```python
except Exception as e:
    logger.error("AUTH_DB_ERROR email=%s: %s", email, e)
    return {'ok': False, 'error': 'Error interno, inténtalo de nuevo'}
```

---

### Hallazgo 2

**Tipo:** seguridad / diseño
**Severidad:** Media

**Problema:** `requiere_rol` muta el estado de sesión como efecto secundario de una comprobación de autorización.

**Evidencia:**
```python
# blueprints/auth.py líneas 76-78
if session.get('demo_mode') and session.get('empleado_id') != 0:
    session.pop('demo_mode', None)
if session.get('demo_mode') and not demo_ok:
    return jsonify({'error': 'No disponible en demo'}), 403
```

**Impacto real:** Un decorador de autorización con efectos secundarios es inesperado y dificulta el razonamiento: la primera request a cualquier ruta protegida puede alterar la sesión silenciosamente. Además, si un usuario real tiene `demo_mode` en sesión por un bug, se limpia sin log.

**Recomendación mínima concreta:** Mover la limpieza de `demo_mode` al punto donde el usuario inicia sesión real (en `login()`), no dentro del decorador de autorización.

---

### Hallazgo 3

**Tipo:** seguridad
**Severidad:** Media

**Problema:** `/auth/logout` acepta POST sin protección CSRF.

**Evidencia:** Línea 56 — ruta `POST /auth/logout` sin ningún token CSRF verificado.

**Impacto real:** Un atacante puede incluir un `<form action="/auth/logout" method="POST">` en cualquier página y provocar el logout de un usuario autenticado (CSRF logout). En un contexto operativo (cocina, repartidor, picker en turno) esto interrumpe el trabajo activo.

**Recomendación mínima concreta:** Si Flask-WTF está disponible, añadir `@csrf.exempt` explícito o proteger con token. Si no está disponible, validar el header `Referer` o añadir un token anti-CSRF mínimo.

---

### Hallazgo 4

**Tipo:** seguridad
**Severidad:** Media

**Problema:** No hay rate limiting ni protección anti-fuerza-bruta en `/auth/login`.

**Evidencia:** Línea 23 — ruta `POST /auth/login` sin ningún mecanismo de limitación de intentos.

**Impacto real:** Un atacante puede hacer intentos ilimitados de contraseña contra cualquier email conocido. `check_password_hash` de werkzeug es deliberadamente lento (bcrypt) pero no sustituye al rate limiting.

**Recomendación mínima concreta:** Añadir bloqueo temporal por IP o por email tras N intentos fallidos consecutivos (puede usarse el Redis ya disponible en el proyecto, patrón idéntico al `bloqueo:<phone>` del bot).

---

### Hallazgo 5

**Tipo:** diseño
**Severidad:** Baja

**Problema:** Import lazy innecesario de `Response` dentro de `manifest()`.

**Evidencia:**
```python
# blueprints/auth.py líneas 16-17
def manifest():
    from flask import Response
```

`Response` podría importarse en la línea 4 junto al resto de imports de Flask.

**Impacto real:** Ninguno en runtime, pero es incoherente con el resto del archivo y puede confundir sobre si hay una razón para el import tardío.

**Recomendación mínima concreta:** Mover `Response` al import de la línea 4.

---

### Hallazgo 6

**Tipo:** seguridad
**Severidad:** Baja

**Problema:** `session.permanent = True` (línea 49) sin conocer si `PERMANENT_SESSION_LIFETIME` está configurado en la app.

**Evidencia:** Línea 49 — `session.permanent = True`.

**Impacto real:** Si `PERMANENT_SESSION_LIFETIME` no está configurado explícitamente, Flask usa 31 días por defecto. Una sesión de empleado activa 31 días sin reautenticación puede ser excesiva en un contexto operativo donde los turnos duran horas.

**Recomendación mínima concreta:** Posible riesgo no confirmado — verificar que `config.py` establece `PERMANENT_SESSION_LIFETIME` con un valor razonable (p.ej. 12 horas).

---

## 4. Riesgos principales si no se toca

| Riesgo | Escenario concreto |
|--------|-------------------|
| DB caída invisible | SQL Server cae en hora punta; todos los logins fallan con "Credenciales incorrectas"; nadie recibe alerta; se tarda minutos en detectar |
| Brute force sin freno | Un atacante con una lista de emails de empleados puede probar contraseñas indefinidamente sin bloqueo |
| CSRF logout | Un enlace malicioso en un email desloguea a un picker o repartidor en medio de un turno |
| Sesiones eternas | Si `PERMANENT_SESSION_LIFETIME` no está configurado, las sesiones duran 31 días; un empleado que deja la empresa sigue con sesión válida si no se invalida manualmente |

---

## 5. Refactor mínimo recomendado

### Qué tocar primero (en orden de impacto)

1. **`auth_service.py` líneas 38-39** — Añadir log en el `except Exception` y devolver error diferenciado. Una línea de fix, impacto crítico en observabilidad.
2. **`requiere_rol` líneas 76-78** — Mover la limpieza de `demo_mode` al flujo de login real, no en el decorador.
3. **Rate limiting** — Implementar bloqueo temporal por email en Redis tras 5 intentos fallidos (patrón ya existe en el proyecto con `bloqueo:<phone>`).

### Qué NO tocar todavía

- La estructura de `requiere_rol` / `requiere_autenticacion` — funcionan correctamente para el resto de casos.
- El flujo de sesión de login — correcto y bien diseñado.
- La integración con `auth_service` — la separación es buena.

---

## 6. Tests que deberían existir

- `test_login_credenciales_incorrectas` — verifica que devuelve 401 con email válido y contraseña errónea.
- `test_login_db_caida` — mockea `_get_empleado_by_email` para lanzar excepción; verifica que devuelve error claro (no 500 sin log).
- `test_login_campos_vacios` — verifica 400 cuando `email` o `password` están vacíos.
- `test_logout_limpia_sesion` — verifica que `session` queda vacía tras POST a `/auth/logout`.
- `test_requiere_rol_sin_sesion_redirige` — GET sin sesión debe redirigir a `/auth/login`.
- `test_requiere_rol_sin_sesion_json` — petición JSON sin sesión debe devolver 401.
- `test_requiere_rol_rol_incorrecto` — sesión con rol `picker` intentando acceder a ruta de `manager` debe devolver 403.
- `test_requiere_rol_demo_no_disponible` — sesión demo en ruta sin `demo_ok=True` debe devolver 403.

---

## 7. Veredicto final

**Estado general del archivo:** Sólido para su responsabilidad de routing. La separación hacia `auth_service` es correcta. Los problemas son en el servicio dependiente (excepción silenciosa) y en seguridad operativa (sin rate limiting, sin CSRF).

**¿Bloquea crecimiento?** No.

**¿Bloquea testeo?** No — los decoradores son testeables con el app context de Flask estándar.

**¿Tiene riesgo operativo real?** Sí — la excepción de DB silenciosa en `auth_service` puede enmascarar una caída total de la base de datos durante el login, y la ausencia de rate limiting expone las cuentas de empleados a fuerza bruta.
