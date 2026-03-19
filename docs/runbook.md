# Runbook — Panchi-Bot

## Arrancar
```bash
docker-compose up -d
```

## Reiniciar app sin downtime
```bash
docker-compose restart app
```

## Ver logs en tiempo real
```bash
docker-compose logs -f app
```

## Recuperar un pedido en estado incorrecto

Si un pedido se queda bloqueado (ej. `confirmando-pago` pero el pago se procesó):

1. Ir a `/dashboard` → seleccionar el pedido → cambiar estado manualmente.
2. Si el dashboard no permite la transición, ejecutar en SQL Server:

```sql
UPDATE Pedidos SET Estado = 'pagado' WHERE PedidoID = <id>;
INSERT INTO historial_estados_pedido (pedido_id, estado_anterior, estado_nuevo, notas)
VALUES (<id>, 'confirmando-pago', 'pagado', 'Corrección manual por operador');
```

## Redis caído
```bash
docker-compose restart redis
# El sistema devuelve 503 mientras Redis no está disponible.
```

## Twilio — mensaje no llega
1. Verificar en Twilio Console que el webhook apunta a `https://<dominio>/webhook`
2. Verificar `TWILIO_WHATSAPP_NUMBER` en `.env`
3. `docker-compose logs app | grep "TWILIO\|enviar_mensaje"`

## Monei — pago no confirma
1. Verificar que el webhook de Monei apunta a `https://<dominio>/webhook/monei`
2. Verificar `MONEI_WEBHOOK_SECRET` en `.env`
3. `docker-compose logs app | grep "webhook_monei\|MONEI"`

## Generar hash de contraseña para empleado
```python
from werkzeug.security import generate_password_hash
print(generate_password_hash("el-pin-del-empleado"))
# Copiar el resultado a la columna password_hash del empleado en SQL Server
```
