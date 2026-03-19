"""Tests for database initialization and ORM models."""
import inspect
import database
from models import AuditLog


def test_conectar_bd1_incluye_audit_log(app):
    """AuditLog debe estar registrado en Base.metadata (modelo correcto)."""
    assert AuditLog.__tablename__ in database.Base.metadata.tables


def test_conectar_bd1_fuente_incluye_auditlog():
    """Verificar que el código fuente de conectar_bd1 incluye AuditLog en create_all."""
    source = inspect.getsource(database.conectar_bd1)
    assert 'AuditLog' in source, (
        "AuditLog debe estar en el código fuente de conectar_bd1() "
        "para que la tabla se cree en deploys limpios"
    )
