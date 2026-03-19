"""Tests for database initialization and ORM models."""
import database
from models import AuditLog


def test_conectar_bd1_incluye_audit_log(app):
    """AuditLog debe estar en la lista de tablas que conectar_bd1 crea."""
    assert AuditLog.__tablename__ in database.Base.metadata.tables
