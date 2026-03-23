# tests/test_metricas_operacion.py
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, rol='manager'):
    with client.session_transaction() as sess:
        sess['empleado_id'] = 1
        sess['rol'] = rol


class TestMetricasOperacionAuth:
    def test_sin_sesion_redirige(self, client):
        resp = client.get('/metricas/operacion/resumen')
        assert resp.status_code in (302, 401)

    def test_rol_picker_no_accede(self, client):
        _login(client, rol='picker')
        resp = client.get('/metricas/operacion/resumen')
        assert resp.status_code in (302, 403)


class TestMetricasOperacionResumen:
    def test_devuelve_200_y_ok(self, client):
        _login(client)
        datos = {
            'pedidos_activos': 5, 'empleados_en_turno': 3,
            'cola_picking_count': 1, 'cola_reparto_count': 0,
            'entregados_hoy': 10, 'tasa_entrega_hoy_pct': 90,
            'tiempo_medio_ciclo_hoy_min': 25,
        }
        with patch('blueprints.metricas_operacion.gestor_metricas.resumen_operacion', return_value=datos):
            resp = client.get('/metricas/operacion/resumen')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['ok'] is True
        assert 'pedidos_activos' in data['data']

    def test_estructura_respuesta(self, client):
        _login(client)
        with patch('blueprints.metricas_operacion.gestor_metricas.resumen_operacion', return_value={}):
            resp = client.get('/metricas/operacion/resumen')
        body = resp.get_json()
        assert 'ok' in body
        assert 'data' in body


class TestMetricasOperacionAsistencia:
    def test_devuelve_lista(self, client):
        _login(client)
        with patch('blueprints.metricas_operacion.gestor_metricas.asistencia_hoy', return_value=[{'empleado_id': 1}]):
            resp = client.get('/metricas/operacion/asistencia')
        assert resp.status_code == 200
        assert isinstance(resp.get_json()['data'], list)


class TestMetricasOperacionColas:
    def test_devuelve_dict_con_colas(self, client):
        _login(client)
        colas = {'cola_picking': [], 'cola_reparto': []}
        with patch('blueprints.metricas_operacion.gestor_metricas.colas_detalle', return_value=colas):
            resp = client.get('/metricas/operacion/colas')
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert 'cola_picking' in data
        assert 'cola_reparto' in data


class TestMetricasOperacionPedidosEstado:
    def test_devuelve_dict(self, client):
        _login(client)
        with patch('blueprints.metricas_operacion.gestor_metricas.pedidos_por_estado',
                   return_value={'en_preparacion': 4}):
            resp = client.get('/metricas/operacion/pedidos-estado')
        assert resp.status_code == 200


class TestMetricasOperacionAlertas:
    def test_devuelve_lista(self, client):
        _login(client)
        with patch('blueprints.metricas_operacion.gestor_metricas.alertas_tiempo_real', return_value=[]):
            resp = client.get('/metricas/operacion/alertas')
        assert resp.status_code == 200
        assert isinstance(resp.get_json()['data'], list)
