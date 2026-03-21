"""Tests for database initialization and ORM models."""
import inspect
import database
from models import AuditLog


def test_conectar_bd1_incluye_audit_log(app):
    """AuditLog debe estar registrado en Base.metadata (modelo correcto)."""
    assert AuditLog.__tablename__ in database.Base.metadata.tables


def test_conectar_bd1_fuente_incluye_audit_log():
    """Verifica que conectar_bd1() incluye AuditLog en su código fuente.

    Usamos inspect.getsource() porque no hay SQL Server disponible en tests.
    Este test detecta si alguien elimina el import o el create_all de AuditLog.
    """
    source = inspect.getsource(database.conectar_bd1)
    assert 'AuditLog' in source, (
        "AuditLog debe estar en el código fuente de conectar_bd1() "
        "para que la tabla se cree en deploys limpios"
    )


def test_empleado_tiene_estado_operativo():
    """El modelo Empleado debe tener el campo estado_operativo."""
    import inspect
    from models import Empleado
    src = inspect.getsource(Empleado)
    assert 'estado_operativo' in src, "Falta columna estado_operativo en Empleado"


def test_modelo_turno_existe():
    """El modelo Turno debe existir con los campos requeridos."""
    import inspect
    from models import Turno
    src = inspect.getsource(Turno)
    for campo in ('empleado_id', 'fecha', 'hora_inicio', 'hora_fin'):
        assert campo in src, f"Falta campo {campo} en Turno"
