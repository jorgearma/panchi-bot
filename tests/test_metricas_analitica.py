# tests/test_metricas_analitica.py
from datetime import date, timedelta
from unittest.mock import patch
import pytest


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, rol='manager'):
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = rol


class TestAnaliticaAuth:
    def test_sin_sesion_redirige(self, client):
        resp = client.get('/metricas/analitica/resumen')
        assert resp.status_code in (302, 401)


class TestAnaliticaFechasDefault:
    def test_sin_params_usa_7_dias(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.resumen_periodo',
                   return_value={}) as mock_rp:
            client.get('/metricas/analitica/resumen')
        args = mock_rp.call_args[0]
        desde, hasta = args[0], args[1]
        assert hasta == date.today()
        assert (hasta - desde).days == 6  # 7 días inclusive


class TestAnaliticaResumen:
    def test_devuelve_200_y_ok(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.resumen_periodo', return_value={'dias_analizados': 7}):
            resp = client.get('/metricas/analitica/resumen')
        assert resp.status_code == 200
        assert resp.get_json()['ok'] is True


class TestAnaliticaComparativaRolRequerido:
    def test_sin_rol_devuelve_400(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.comparativa_empleados', return_value={}):
            resp = client.get('/metricas/analitica/comparativa')
        assert resp.status_code == 400

    def test_con_rol_devuelve_200(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.comparativa_empleados',
                   return_value={'rol': 'picker', 'ranking': [], 'media_equipo': {}}):
            resp = client.get('/metricas/analitica/comparativa?rol=picker')
        assert resp.status_code == 200


class TestAnaliticaEmpleadoFicha:
    def test_devuelve_200_con_id(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.ficha_empleado',
                   return_value={'empleado_id': 7}):
            resp = client.get('/metricas/analitica/empleado/7')
        assert resp.status_code == 200


class TestAnaliticaEmpleadosRolOpcional:
    def test_sin_rol_llama_con_none(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.rendimiento_empleados',
                   return_value=[]) as mock_re:
            client.get('/metricas/analitica/empleados')
        _, kwargs = mock_re.call_args
        assert kwargs.get('rol') is None

    def test_con_rol_lo_pasa(self, client):
        _login(client)
        with patch('blueprints.metricas_analitica.gestor_metricas.rendimiento_empleados',
                   return_value=[]) as mock_re:
            client.get('/metricas/analitica/empleados?rol=picker')
        _, kwargs = mock_re.call_args
        assert kwargs.get('rol') == 'picker'
