-- ─────────────────────────────────────────────────────────────
-- Usuario propio de la app (mínimo privilegio) en vez de `sa`.
--
-- Por qué: `sa` es sysadmin. Con una inyección SQL un atacante podría activar
-- xp_cmdshell y ejecutar comandos en el contenedor de SQL Server, leer otras BD,
-- crear logins... Con este usuario solo puede leer/escribir las tablas de SU BD.
--
-- La app NO necesita DDL en producción: conectar_bd1() (create_all) solo se
-- ejecuta con `python main.py` (desarrollo). Si hay que crear/alterar tablas → con sa.
--
-- Uso (desde el host; con read -s la contraseña no queda en el historial):
--   read -rs APP_PWD; export APP_PWD
--   docker compose exec -e APP_PWD sqlserver sh -c '/opt/mssql-tools18/bin/sqlcmd -No -b \
--     -S localhost -U sa -P "$SA_PASSWORD" -v DB=panchibot -i /scripts/crear_usuario_app.sql'
--   (sqlcmd lee $(APP_PWD) de la variable de entorno; $SA_PASSWORD es la del contenedor)
--   La contraseña debe cumplir la política de SQL Server (8+ caracteres, 3 tipos).
--
-- Después, en .env:  SQL_UID=panchi_app  ·  SQL_PWD=<APP_PWD>  ·  SQL_PWD_SA=<la de sa>
-- Idempotente: se puede volver a ejecutar (cambia la contraseña si el login ya existe).
-- ─────────────────────────────────────────────────────────────
SET NOCOUNT ON;

IF NOT EXISTS (SELECT 1 FROM sys.server_principals WHERE name = N'panchi_app')
    CREATE LOGIN panchi_app WITH PASSWORD = N'$(APP_PWD)', CHECK_POLICY = ON, DEFAULT_DATABASE = [$(DB)];
ELSE
    ALTER LOGIN panchi_app WITH PASSWORD = N'$(APP_PWD)';
GO

USE [$(DB)];
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'panchi_app')
    CREATE USER panchi_app FOR LOGIN panchi_app;
GO

-- Solo datos: SELECT / INSERT / UPDATE / DELETE en las tablas de esta BD
ALTER ROLE db_datareader ADD MEMBER panchi_app;
ALTER ROLE db_datawriter ADD MEMBER panchi_app;
GO

-- Comprobación
SELECT r.name AS rol
FROM sys.database_role_members m
JOIN sys.database_principals r ON r.principal_id = m.role_principal_id
JOIN sys.database_principals u ON u.principal_id = m.member_principal_id
WHERE u.name = N'panchi_app';
GO
