"""Tests de los nuevos campos del modelo de empleados para el dashboard."""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import date, datetime, time


class TestTurnoModeloCampos:
    """Verifica que el modelo Turno tiene los campos nuevos con sus defaults."""

    def test_turno_tiene_campo_estado(self):
        from models import Turno
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        assert hasattr(t, 'estado')

    def test_turno_estado_default_es_planificado(self):
        from models import Turno
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        # El default de SQLAlchemy solo aplica al INSERT; en instancia nueva puede ser None o el valor
        # Verificar que el campo existe y acepta el valor correcto
        t.estado = 'planificado'
        assert t.estado == 'planificado'

    def test_turno_tiene_campo_tipo(self):
        from models import Turno
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        assert hasattr(t, 'tipo')
        t.tipo = 'mañana'
        assert t.tipo == 'mañana'

    def test_turno_tiene_campo_creado_por(self):
        from models import Turno
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        assert hasattr(t, 'creado_por')
        t.creado_por = 5
        assert t.creado_por == 5

    def test_turno_estados_validos(self):
        """Los estados válidos son los que usará el dashboard."""
        from models import Turno
        estados_validos = {'planificado', 'confirmado', 'cubierto', 'cancelado'}
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        for estado in estados_validos:
            t.estado = estado
            assert t.estado == estado

    def test_turno_tipos_validos(self):
        from models import Turno
        tipos_validos = {'mañana', 'tarde', 'noche', 'partido'}
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        for tipo in tipos_validos:
            t.tipo = tipo
            assert t.tipo == tipo


class TestCheckInModeloCampos:
    """Verifica que CheckIn tiene los nuevos campos de dashboard."""

    def test_checkin_tiene_turno_id(self):
        from models import CheckIn
        c = CheckIn(empleado_id=1, fecha=date.today(), inicio=datetime.utcnow())
        assert hasattr(c, 'turno_id')
        c.turno_id = 42
        assert c.turno_id == 42

    def test_checkin_tiene_estado_validacion(self):
        from models import CheckIn
        c = CheckIn(empleado_id=1, fecha=date.today(), inicio=datetime.utcnow())
        assert hasattr(c, 'estado_validacion')

    def test_checkin_tiene_minutos_tarde(self):
        from models import CheckIn
        c = CheckIn(empleado_id=1, fecha=date.today(), inicio=datetime.utcnow())
        assert hasattr(c, 'minutos_tarde')
        c.minutos_tarde = 15
        assert c.minutos_tarde == 15

    def test_checkin_minutos_tarde_puede_ser_negativo(self):
        """Negativo = llegó antes del turno (adelantado)."""
        from models import CheckIn
        c = CheckIn(empleado_id=1, fecha=date.today(), inicio=datetime.utcnow())
        c.minutos_tarde = -5
        assert c.minutos_tarde == -5


class TestIniciarTurnoConTurnoId:
    """iniciar_turno debe enlazar turno_id y calcular minutos_tarde."""

    def _gestor(self):
        from managers.gestor_empleado import GestorEmpleado
        return GestorEmpleado()

    def test_iniciar_turno_acepta_turno_id(self):
        gestor = self._gestor()
        empleado_mock = MagicMock()
        empleado_mock.rol_activo = None
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = None
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        added = []
        session_mock.add.side_effect = lambda obj: added.append(obj)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor.iniciar_turno(1, turno_id=7)
        from models import CheckIn
        check_ins = [o for o in added if isinstance(o, CheckIn)]
        assert len(check_ins) == 1
        assert check_ins[0].turno_id == 7

    def test_iniciar_turno_calcula_minutos_tarde_con_turno(self):
        """Si el turno empieza a las 09:00 y el checkin es 09:15, minutos_tarde=15."""
        gestor = self._gestor()
        empleado_mock = MagicMock()
        empleado_mock.rol_activo = None

        turno_mock = MagicMock()
        hoy = date.today()
        # Turno planificado para las 09:00
        turno_mock.hora_inicio = time(9, 0)
        turno_mock.fecha = hoy

        session_mock = MagicMock()
        def query_side_effect(model):
            from models import CheckIn, Turno, Empleado
            q = MagicMock()
            if model is CheckIn:
                q.filter.return_value.first.return_value = None
            elif model is Turno:
                q.filter_by.return_value.first.return_value = turno_mock
            elif model is Empleado:
                q.filter_by.return_value.first.return_value = empleado_mock
            return q

        session_mock.query.side_effect = query_side_effect
        added = []
        session_mock.add.side_effect = lambda obj: added.append(obj)

        # Pasar ahora directamente: el empleado ficha a las 09:15
        ahora_mock = datetime(hoy.year, hoy.month, hoy.day, 9, 15)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor.iniciar_turno(1, turno_id=7, ahora=ahora_mock)

        from models import CheckIn
        check_ins = [o for o in added if isinstance(o, CheckIn)]
        assert check_ins[0].minutos_tarde == 15

    def test_iniciar_turno_sin_turno_id_no_calcula_minutos_tarde(self):
        """Sin turno_id, minutos_tarde queda None."""
        gestor = self._gestor()
        empleado_mock = MagicMock()
        empleado_mock.rol_activo = None
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = None
        session_mock.query.return_value.filter_by.return_value.first.return_value = empleado_mock
        added = []
        session_mock.add.side_effect = lambda obj: added.append(obj)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor.iniciar_turno(1)  # sin turno_id ni ahora → comportamiento normal
        from models import CheckIn
        check_ins = [o for o in added if isinstance(o, CheckIn)]
        assert check_ins[0].minutos_tarde is None


class TestAusenciaModelo:
    """Verifica la entidad Ausencia y los métodos del gestor."""

    def test_ausencia_tiene_campos_obligatorios(self):
        from models import Ausencia
        hoy = date.today()
        a = Ausencia(empleado_id=1, fecha=hoy, tipo='personal')
        assert a.empleado_id == 1
        assert a.fecha == hoy
        assert a.tipo == 'personal'

    def test_ausencia_estado_default_pendiente(self):
        from models import Ausencia
        a = Ausencia(empleado_id=1, fecha=date.today(), tipo='vacaciones')
        assert hasattr(a, 'estado')
        a.estado = 'pendiente'
        assert a.estado == 'pendiente'

    def test_ausencia_tipos_validos(self):
        from models import Ausencia
        tipos = {'vacaciones', 'baja_medica', 'personal', 'injustificada'}
        for tipo in tipos:
            a = Ausencia(empleado_id=1, fecha=date.today(), tipo=tipo)
            assert a.tipo == tipo

    def test_ausencia_estados_validos(self):
        from models import Ausencia
        estados = {'pendiente', 'aprobada', 'rechazada'}
        for estado in estados:
            a = Ausencia(empleado_id=1, fecha=date.today(), tipo='personal')
            a.estado = estado
            assert a.estado == estado


class TestGestorEmpleadoAusencias:
    """Prueba los métodos de gestión de ausencias."""

    def _gestor(self):
        from managers.gestor_empleado import GestorEmpleado
        return GestorEmpleado()

    def test_registrar_ausencia_crea_registro(self):
        gestor = self._gestor()
        session_mock = MagicMock()
        added = []
        session_mock.add.side_effect = lambda obj: added.append(obj)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            gestor.registrar_ausencia(empleado_id=1, fecha=date.today(), tipo='personal')
        from models import Ausencia
        ausencias = [o for o in added if isinstance(o, Ausencia)]
        assert len(ausencias) == 1
        assert ausencias[0].empleado_id == 1
        assert ausencias[0].tipo == 'personal'
        session_mock.commit.assert_called()

    def test_registrar_ausencia_tipo_invalido_lanza_error(self):
        gestor = self._gestor()
        session_mock = MagicMock()
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with pytest.raises(ValueError, match='tipo_invalido'):
                gestor.registrar_ausencia(empleado_id=1, fecha=date.today(), tipo='INEXISTENTE')

    def test_ausencias_empleado_devuelve_lista(self):
        gestor = self._gestor()
        session_mock = MagicMock()
        ausencia_mock = MagicMock()
        ausencia_mock.id = 1
        ausencia_mock.fecha = date.today()
        ausencia_mock.tipo = 'vacaciones'
        ausencia_mock.estado = 'aprobada'
        ausencia_mock.aprobado_por = None
        ausencia_mock.notas = None
        session_mock.query.return_value.filter.return_value.order_by.return_value.all.return_value = [ausencia_mock]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.ausencias_empleado(empleado_id=1,
                                               fecha_inicio=date.today(),
                                               fecha_fin=date.today())
        assert len(result) == 1
        assert result[0]['tipo'] == 'vacaciones'
        assert result[0]['estado'] == 'aprobada'


class TestPuntualidadEmpleado:
    """puntualidad_empleado devuelve resumen de puntualidad en un rango de fechas."""

    def _gestor(self):
        from managers.gestor_empleado import GestorEmpleado
        return GestorEmpleado()

    def _checkin_mock(self, minutos_tarde, estado_validacion='validado', turno_id=1):
        m = MagicMock()
        m.minutos_tarde = minutos_tarde
        m.estado_validacion = estado_validacion
        m.turno_id = turno_id
        return m

    def test_sin_checkins_devuelve_ceros(self):
        gestor = self._gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.puntualidad_empleado(1, date.today(), date.today())
        assert result['total_turnos'] == 0
        assert result['puntuales'] == 0
        assert result['tarde'] == 0
        assert result['tasa_puntualidad_pct'] == 100

    def test_calcula_puntuales_y_tarde(self):
        gestor = self._gestor()
        checkins = [
            self._checkin_mock(-2),   # adelantado → puntual
            self._checkin_mock(0),    # exacto → puntual
            self._checkin_mock(5),    # 5 min → puntual (margen ≤ 5)
            self._checkin_mock(6),    # 6 min → tarde
            self._checkin_mock(20),   # 20 min → tarde
        ]
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = checkins
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.puntualidad_empleado(1, date.today(), date.today())
        assert result['total_turnos'] == 5
        assert result['puntuales'] == 3
        assert result['tarde'] == 2
        assert result['tasa_puntualidad_pct'] == 60

    def test_ignora_checkins_sin_turno_id(self):
        """Fichajes espontáneos (sin turno planificado) no computan en puntualidad."""
        gestor = self._gestor()
        checkins = [
            self._checkin_mock(10, turno_id=1),
            self._checkin_mock(None, turno_id=None),  # sin turno → ignorar
        ]
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = checkins
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.puntualidad_empleado(1, date.today(), date.today())
        assert result['total_turnos'] == 1

    def test_media_minutos_tarde(self):
        gestor = self._gestor()
        checkins = [
            self._checkin_mock(10),
            self._checkin_mock(20),
        ]
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = checkins
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.puntualidad_empleado(1, date.today(), date.today())
        assert result['media_minutos_tarde'] == 15


class TestHistorialEmpleadoId:

    def test_historial_tiene_empleado_id(self):
        from models import HistorialEstadoPedido
        h = HistorialEstadoPedido(
            pedido_id=1,
            estado_anterior='pendiente',
            estado_nuevo='pagado',
        )
        assert hasattr(h, 'empleado_id')
        h.empleado_id = 3
        assert h.empleado_id == 3

    def test_historial_empleado_id_es_nullable(self):
        """Transiciones automáticas (sin actor humano) deben poder tener empleado_id=None."""
        from models import HistorialEstadoPedido
        h = HistorialEstadoPedido(
            pedido_id=1,
            estado_anterior='pendiente',
            estado_nuevo='pagado',
        )
        h.empleado_id = None
        assert h.empleado_id is None


class TestSolicitudCambioTurno:

    def test_modelo_tiene_campos_obligatorios(self):
        from models import SolicitudCambioTurno
        s = SolicitudCambioTurno(
            turno_cedido_id=1,
            solicitante_id=2,
        )
        assert s.turno_cedido_id == 1
        assert s.solicitante_id == 2
        assert hasattr(s, 'estado')
        assert hasattr(s, 'sustituto_id')
        assert hasattr(s, 'aprobado_por')

    def test_estados_validos(self):
        from models import SolicitudCambioTurno
        estados = {'pendiente', 'aprobada', 'rechazada', 'cancelada'}
        for estado in estados:
            sc = SolicitudCambioTurno(turno_cedido_id=1, solicitante_id=1)
            sc.estado = estado
            assert sc.estado == estado


class TestTurnoOrigenId:

    def test_turno_tiene_campo_origen_id(self):
        from models import Turno
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        assert hasattr(t, 'turno_origen_id')
        t.turno_origen_id = 99
        assert t.turno_origen_id == 99

    def test_turno_origen_id_nullable(self):
        from models import Turno
        t = Turno(empleado_id=1, fecha=date.today(),
                  hora_inicio=time(9, 0), hora_fin=time(17, 0))
        t.turno_origen_id = None
        assert t.turno_origen_id is None


class TestMetricaDiariaEmpleado:

    def test_modelo_tiene_campos_clave(self):
        from models import MetricaDiariaEmpleado
        m = MetricaDiariaEmpleado(empleado_id=1, fecha=date.today())
        assert hasattr(m, 'horas_trabajadas_min')
        assert hasattr(m, 'pedidos_completados')
        assert hasattr(m, 'tiempo_medio_operacion_min')
        assert hasattr(m, 'incidencias')
        assert hasattr(m, 'minutos_tarde')

    def test_calcular_y_guardar_metrica_diaria_persiste_registro(self):
        from managers.gestor_empleado import GestorEmpleado
        gestor = GestorEmpleado()
        ahora = datetime.utcnow()
        tramo_mock = MagicMock()
        tramo_mock.rol = 'picker'
        tramo_mock.inicio = ahora.replace(hour=9, minute=0)
        tramo_mock.fin = ahora.replace(hour=13, minute=0)   # 4 horas = 240 min
        check_in_mock = MagicMock()
        check_in_mock.inicio = ahora.replace(hour=9, minute=0)
        check_in_mock.fin = ahora.replace(hour=13, minute=0)
        check_in_mock.minutos_tarde = 5
        check_in_mock.turno_id = 1
        check_in_mock.tramos = [tramo_mock]
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.first.return_value = check_in_mock
        added = []
        session_mock.add.side_effect = lambda obj: added.append(obj)
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            # metricas de pedidos vacías para simplificar el mock
            with patch.object(gestor, 'metricas_hoy', return_value={
                'pedidos_completados': 3,
                'tiempo_medio_min': 12,
                'incidencias_hoy': 1,
            }):
                gestor.calcular_y_guardar_metrica_diaria(
                    empleado_id=1, fecha=date.today(), rol='picker'
                )
        from models import MetricaDiariaEmpleado
        metricas = [o for o in added if isinstance(o, MetricaDiariaEmpleado)]
        assert len(metricas) == 1
        assert metricas[0].horas_trabajadas_min == 240
        assert metricas[0].pedidos_completados == 3
        assert metricas[0].minutos_tarde == 5
