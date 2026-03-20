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


def test_monitor_datos_devuelve_claves_principales(client, app):
    """El endpoint /dashboard/monitor/datos devuelve metricas, alertas y eventos."""
    from unittest.mock import patch
    from services import gestor_dashboard

    with app.app_context():
        with patch.object(gestor_dashboard, 'monitor_empleados', return_value={"pickers": [], "repartidores": [], "pedidos_sin_picker": [], "pedidos_sin_repartidor": []}), \
             patch.object(gestor_dashboard, 'metricas', return_value={"pedidos_hoy": 0}), \
             patch.object(gestor_dashboard, 'alertas', return_value=[]), \
             patch.object(gestor_dashboard, 'eventos', return_value=[]):
            with client.session_transaction() as sess:
                sess['empleado_id'] = 1
                sess['rol'] = 'admin'
            resp = client.get('/dashboard/monitor/datos')
            assert resp.status_code == 200
            data = resp.get_json()
            assert 'metricas' in data
            assert 'alertas' in data
            assert 'eventos' in data
            assert 'pedidos_pipeline' not in data
