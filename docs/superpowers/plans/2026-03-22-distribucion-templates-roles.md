# Plan — Distribución de Templates y Flujo por Roles

**Objetivo:** definir una estructura clara para que cada perfil entre a su zona correcta tras login, evitando mezclar vistas operativas de empleados con paneles de supervisión y administración.

**Principio base:** separar por `zona funcional`, no solo por rol técnico. El empleado entra a una zona operativa personal; el manager/admin entra a una zona de control. Desde ahí se derivan las pantallas secundarias.

---

## Flujo recomendado

### 1. Login

- Todos entran por `/auth/login`.
- Después del login, el sistema decide la zona inicial según `session['rol']` y, si aplica, `rol_activo`.

### 2. Empleado operativo

- Si el usuario es `picker` o `repartidor`, o es polivalente con capacidades operativas:
  - entra primero en `/empleado/checkin` si todavía no ha iniciado turno o no tiene rol activo;
  - si ya tiene turno/rol activo, entra en `/empleado`.

### 3. Admin o manager

- Si el usuario es `admin` o `manager`, entra en `/dashboard`.
- Desde `/dashboard` debe poder navegar a:
  - monitor operativo;
  - dashboard de métricas;
  - dashboard/control de empleados.

---

## Distribución recomendada de zonas

### Zona 1: Hub del empleado

**Ruta base:** `/empleado`

**Responsabilidad:** ser la casa del trabajador operativo. No debe mostrar paneles globales de administración.

**Qué debe contener:**

- estado del turno;
- rol activo actual;
- selector de acción o cambio de rol;
- acceso a "Entrar como repartidor";
- acceso a "Entrar como picker";
- resumen de métricas personales del día;
- acceso a cerrar turno.

**Subrutas recomendadas:**

- `/empleado/checkin`
- `/empleado`
- `/empleado/picker`
- `/empleado/repartidor`
- `/empleado/metricas`

**Idea clave:** `/empleado` funciona como hub/launcher, y las vistas de trabajo real viven en subzonas concretas.

### Zona 2: Operación en vivo

**Responsabilidad:** ejecución del trabajo.

**Templates recomendados:**

- `templates/empleado/index.html`
  - hub principal del empleado.
- `templates/empleado/checkin.html`
  - selección de turno/rol antes de empezar.
- `templates/picker/index.html`
  - flujo de preparación.
- `templates/repartidor/index.html`
  - flujo de reparto.

**Regla:** el empleado no debería usar el dashboard admin para trabajar su operativa diaria.

### Zona 3: Control de negocio

**Ruta base:** `/dashboard`

**Responsabilidad:** supervisión y control, no ejecución directa del trabajo del empleado.

**Entradas recomendadas desde esta zona:**

- `/dashboard`
  - landing con tarjetas de acceso;
- `/dashboard/monitor`
  - monitor en vivo de operación;
- `/dashboard/metricas` o nueva página analítica;
- `/dashboard/empleados-control`
  - control de empleados;
- `/dashboard/empleados/<id>`
  - detalle individual.

---

## Mejor flujo de usuario

### Caso A: Empleado polivalente

1. Hace login.
2. Entra en `/empleado/checkin`.
3. Selecciona cómo empieza el turno:
   - entrar como `picker`;
   - entrar como `repartidor`.
4. El sistema guarda `rol_activo`.
5. Después entra al hub `/empleado`.
6. Desde el hub puede:
   - ir a su pantalla de trabajo;
   - cambiar de rol si no tiene tareas bloqueantes;
   - ver sus métricas del día;
   - cerrar turno.

### Caso B: Empleado con un solo rol

1. Hace login.
2. Si no tiene turno abierto, pasa por `/empleado/checkin`.
3. Después entra al hub `/empleado`.
4. Un CTA principal lo lleva a su herramienta:
   - "Entrar en picking";
   - "Entrar en reparto".

### Caso C: Admin o manager

1. Hace login.
2. Entra en `/dashboard`.
3. Ve tres accesos principales:
   - `Monitor de operación`;
   - `Métricas y analítica`;
   - `Control de empleados`.

---

## Reparto recomendado de templates

```text
templates/
  auth/
    login.html
  empleado/
    index.html                # hub personal del empleado
    checkin.html              # fichaje + selección de rol inicial
    estado.html               # opcional: resumen de turno/estado
  picker/
    index.html                # operativa picker
  repartidor/
    index.html                # operativa repartidor
    cierre.html               # cierre de caja / fin de reparto
  dashboard/
    index.html                # home de control
    monitor.html              # monitor en vivo
    metricas.html             # analítica y KPIs
    empleados.html            # listado/control de empleados
    empleado_detalle.html     # ficha individual
```

---

## Criterio de diseño importante

### Lo que conviene hacer

- usar `/empleado` como puerta única del personal operativo;
- usar `/dashboard` como puerta única de supervisión;
- separar "hacer trabajo" de "controlar la operación";
- permitir cambio de rol dentro del hub del empleado;
- reservar las métricas globales de negocio para manager/admin.

### Lo que conviene evitar

- meter opciones de admin dentro de `templates/empleado/*`;
- mandar a un empleado directamente al dashboard global;
- usar una sola plantilla con bloques condicionales gigantes para todos los roles;
- mezclar métricas personales del empleado con KPIs globales del negocio en la misma pantalla.

---

## Recomendación final

La mejor distribución para tu caso es esta:

- `empleado` = zona personal y operativa;
- `picker` y `repartidor` = herramientas especializadas de ejecución;
- `dashboard` = zona de supervisión y análisis;
- `admin/manager` entran siempre por `dashboard`;
- `picker/repartidor` entran siempre por `empleado`, y desde ahí eligen o cambian acción.

Así consigues un flujo natural:

**login -> zona correcta -> elección de acción -> pantalla especializada**

en lugar de:

**login -> pantalla mezclada con demasiadas opciones**

---

## Siguiente implementación sugerida

- [ ] convertir `templates/dashboard/index.html` en un landing con 3 tarjetas grandes;
- [ ] consolidar `templates/empleado/index.html` como hub de acciones del trabajador;
- [ ] crear `templates/dashboard/metricas.html`;
- [ ] crear `templates/dashboard/empleados.html`;
- [ ] añadir rutas HTML separadas para `control de empleados` y `detalle de empleado`;
- [ ] mantener las APIs JSON de métricas y empleados desacopladas de los templates.
