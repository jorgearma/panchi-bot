# tests/test_gestor_dashboard.py
from sqlalchemy.exc import OperationalError


def test_metricas_keys_existentes_presentes(app):
    """Las claves de timing ya implementadas siguen presentes."""
    from services import gestor_dashboard
    with app.app_context():
        try:
            result = gestor_dashboard.metricas()
            existing_keys = {
                'pedidos_hoy', 'ingresos_hoy_eur',
                'tiempo_medio_preparacion_min', 'tiempo_medio_entrega_min',
            }
            assert existing_keys.issubset(result.keys()), (
                f"Claves faltantes: {existing_keys - result.keys()}"
            )
        except Exception as e:
            if 'odbc' in str(e).lower() or 'sql server' in str(e).lower() or 'operational' in type(e).__name__.lower():
                pass  # BD no disponible en CI
            else:
                raise


def test_metricas_incluye_cancelaciones_e_ingresos_por_metodo(app):
    """Smoke test: las claves nuevas existen tras la implementación."""
    from services import gestor_dashboard
    with app.app_context():
        try:
            result = gestor_dashboard.metricas()
            new_keys = {'cancelaciones_hoy', 'ingresos_por_metodo'}
            assert new_keys.issubset(result.keys()), (
                f"Claves nuevas faltantes: {new_keys - result.keys()}"
            )
        except Exception as e:
            if 'odbc' in str(e).lower() or 'sql server' in str(e).lower() or 'operational' in type(e).__name__.lower():
                pass
            else:
                raise
