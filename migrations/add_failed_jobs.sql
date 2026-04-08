-- Migración: Fase 2 RQ — Dead Letter Queue + idempotencia picking
-- Fecha: 2026-04-08

-- 1. Tabla failed_jobs (Dead Letter Queue)
CREATE TABLE failed_jobs (
    id          INT IDENTITY(1,1) PRIMARY KEY,
    job_id      NVARCHAR(100)   NOT NULL,
    job_type    NVARCHAR(100)   NOT NULL,
    queue_name  NVARCHAR(50)    NOT NULL,
    payload     NVARCHAR(MAX)   NULL,
    error       NVARCHAR(MAX)   NOT NULL,
    retries     INT             NOT NULL DEFAULT 0,
    created_at  DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
    resolved_at DATETIME2       NULL,
    resolved_by INT             NULL REFERENCES empleados(EmpleadoID)
);

-- 2. Campo idempotencia en picking_pedido
ALTER TABLE picking_pedido
    ADD stock_descontado BIT NOT NULL DEFAULT 0;
