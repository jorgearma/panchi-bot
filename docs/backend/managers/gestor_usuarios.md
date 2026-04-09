# GestorUsuarios

**Archivo:** `managers/gestor_usuarios.py`  
**Capa:** Manager (acceso a BD)  
**Tabla:** `usuarios`

## Responsabilidad

Único punto de acceso a la tabla `usuarios` en SQL Server. Los controllers nunca tocan SQLAlchemy directamente — siempre pasan por este gestor.

## Dependencias

| Dependencia | Uso |
|---|---|
| `database.get_db()` | Sesión SQLAlchemy (se obtiene en cada acceso via `self.session`) |
| `models.Usuario` | ORM de la tabla `usuarios` |
| `tenacity` | Reintentos automáticos ante fallos transitorios de conexión |

## Métodos

### `verificar_usuario(numero_cliente) → bool`

Comprueba si existe un usuario por su número de teléfono.

- **Reintentos:** 3 intentos, espera 1s entre ellos (`tenacity`)
- **Usado por:** `controllers/mensajes_registrados.py` — primer paso al recibir cualquier mensaje WhatsApp
- **Devuelve:** `True` si existe, `False` si no

```python
existe = gestor_usuarios.verificar_usuario("+34612345678")
```

---

### `obtener_usuario_completo(numero_cliente) → dict | None`

Recupera todos los datos del usuario dado su número.

- **Reintentos:** 3 intentos, espera 1s entre ellos (`tenacity`)
- **Usado por:** Controllers de pedido, para obtener el `id` antes de crear un pedido
- **Devuelve:** `{"id": ..., "nombre": ..., "numero": ..., "direccion": ...}` o `None` si no existe

```python
usuario = gestor_usuarios.obtener_usuario_completo("+34612345678")
# {"id": 42, "nombre": "Juan", "numero": "+34612345678", "direccion": "Calle Mayor 1"}
```

---

### `guardar_usuario(numero_cliente, nombre, direccion) → int`

Crea un nuevo usuario en la BD y devuelve su `id`.

- **Sin reintentos** — si falla hace rollback y relanza la excepción
- **Usado por:** `controllers/registro.py` — último paso de la máquina de estados de registro
- **Devuelve:** `id` del usuario recién creado

```python
usuario_id = gestor_usuarios.guardar_usuario("+34612345678", "Juan", "Calle Mayor 1")
```

## Flujo en el bot

```
WhatsApp → /webhook → RQ → worker.py
                              ↓
              controllers/mensajes_registrados.py
                              ↓
                  verificar_usuario(numero)
                       ↓              ↓
                   existe          no existe
                       ↓              ↓
               flujo pedido    controllers/registro.py
                                       ↓ (al confirmar dirección)
                               guardar_usuario(numero, nombre, direccion)
```

## Contrato con controllers

Este gestor **solo lanza excepciones** — no las maneja. El manejo de errores y la lógica de recuperación es responsabilidad de los controllers:

| Qué ocurre aquí | Quién lo maneja |
|---|---|
| `@retry` agota los 3 intentos → lanza `RetryError` | `controllers/mensajes_registrados.py` línea 69: captura `RetryError`, notifica al usuario y devuelve 500 |
| `guardar_usuario` falla → hace rollback y relanza | `controllers/registro.py` línea 99: captura la excepción y deja Redis en `CONFIRMANDO_DIRECCION` para que el usuario pueda reintentar |
| `obtener_usuario_completo` devuelve `None` | `controllers/mensajes_registrados.py` línea 64: loguea el aviso y notifica al usuario |

**No añadir manejo de errores en este archivo** — hacerlo duplicaría responsabilidades y rompería el contrato de capas definido en CLAUDE.md.

## Notas

- La sesión se obtiene con `self.session` (property), que llama a `get_db()` en cada acceso — no se cachea en el constructor.
- Los métodos con `@retry` protegen contra caídas transitorias de SQL Server; no eliminar esos decoradores.
