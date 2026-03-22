"""Tests para la lógica de fichaje en GestorEmpleado."""
import pytest
from datetime import datetime, date
from unittest.mock import patch, MagicMock, PropertyMock


class TestIniciarTurno:

    def test_crea_checkin_sin_rol_activo(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        empleado_mock = MagicMock()
        empleado_mock.rol_activo = None
        session_mock = MagicMock()
        # No hay check-in previo
        session_mock.query.return_value.filter.return_value.first.return_value = None
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.iniciar_turno(1)
        session_mock.add.assert_called()
        session_mock.commit.assert_called()

    def test_lanza_error_si_ya_hay_checkin_abierto(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        check_in_existente = MagicMock()
        check_in_existente.fin = None  # abierto
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = check_in_existente
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with pytest.raises(ValueError, match='ya_abierto'):
                gestor.iniciar_turno(1)

    def test_crea_tramo_si_tiene_rol_activo(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        empleado_mock = MagicMock()
        empleado_mock.rol_activo = 'picker'
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = None
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        added = []
        session_mock.add.side_effect = lambda obj: added.append(obj)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor.iniciar_turno(1)
        from models import TramoTurno
        tramos = [o for o in added if isinstance(o, TramoTurno)]
        assert len(tramos) == 1
        assert tramos[0].rol == 'picker'


class TestCerrarTurno:

    def test_lanza_error_si_no_hay_checkin(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = None
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with pytest.raises(ValueError, match='no_abierto'):
                gestor.cerrar_turno(1)

    def test_cierra_checkin_y_devuelve_resumen(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        ahora = datetime.utcnow()
        tramo_mock = MagicMock()
        tramo_mock.rol = 'picker'
        tramo_mock.inicio = ahora.replace(hour=9, minute=0)
        tramo_mock.fin = ahora.replace(hour=11, minute=0)
        check_in_mock = MagicMock()
        check_in_mock.fin = None
        check_in_mock.inicio = ahora.replace(hour=9, minute=0)
        check_in_mock.tramos = [tramo_mock]
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = check_in_mock
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.cerrar_turno(1)
        assert check_in_mock.fin is not None
        assert 'tramos' in result


class TestCheckinHoy:

    def test_devuelve_falso_si_no_hay_checkin(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = None
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.checkin_hoy(1)
        assert result['activo'] is False

    def test_devuelve_resumen_con_checkin_activo(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        ahora = datetime.utcnow()
        tramo_mock = MagicMock()
        tramo_mock.rol = 'picker'
        tramo_mock.inicio = ahora.replace(hour=9, minute=0)
        tramo_mock.fin = ahora.replace(hour=10, minute=0)
        check_in_mock = MagicMock()
        check_in_mock.fin = None
        check_in_mock.inicio = ahora.replace(hour=9, minute=0)
        check_in_mock.tramos = [tramo_mock]
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = check_in_mock
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.checkin_hoy(1)
        assert result['activo'] is True
        assert len(result['tramos']) == 1
        assert result['tramos'][0]['rol'] == 'picker'
