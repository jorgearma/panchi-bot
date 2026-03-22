# tests/test_gestor_metricas.py
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import date, datetime


def _make_gestor():
    from managers.gestor_metricas import GestorMetricas
    return GestorMetricas()


class TestResumenOperacion:
    def test_devuelve_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        # pedidos_activos: query count
        session_mock.query.return_value.filter.return_value.count.return_value = 5
        session_mock.query.return_value.filter_by.return_value.count.return_value = 3
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.resumen_operacion()
        claves = {
            'pedidos_activos', 'empleados_en_turno', 'cola_picking_count',
            'cola_reparto_count', 'entregados_hoy', 'tasa_entrega_hoy_pct',
            'tiempo_medio_ciclo_hoy_min'
        }
        assert claves == set(result.keys())

    def test_valores_son_numericos(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.count.return_value = 0
        session_mock.query.return_value.filter_by.return_value.count.return_value = 0
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.resumen_operacion()
        for v in result.values():
            assert isinstance(v, (int, float)) or v is None


class TestAsistenciaHoy:
    def test_devuelve_lista(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        # Simular JOIN: query devuelve tuplas (Turno, CheckIn|None, Empleado)
        turno_mock = MagicMock()
        turno_mock.inicio = datetime(2026, 3, 22, 9, 0)
        turno_mock.fin = datetime(2026, 3, 22, 17, 0)
        empleado_mock = MagicMock()
        empleado_mock.EmpleadoID = 7
        empleado_mock.Nombre = 'Ana García'
        empleado_mock.rol = MagicMock()
        empleado_mock.rol.nombre = 'picker'
        checkin_mock = MagicMock()
        checkin_mock.inicio = datetime(2026, 3, 22, 9, 8)
        checkin_mock.minutos_tarde = 8
        checkin_mock.fin = None
        row = (turno_mock, checkin_mock, empleado_mock)
        session_mock.query.return_value.join.return_value.outerjoin.return_value.filter.return_value.all.return_value = [row]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.asistencia_hoy()
        assert isinstance(result, list)
        assert result[0]['empleado_id'] == 7
        assert result[0]['activo'] is True
        assert result[0]['ausente'] is False
        assert result[0]['minutos_tarde'] == 8

    def test_sin_checkin_es_ausente(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        turno_mock = MagicMock()
        turno_mock.inicio = datetime(2026, 3, 22, 9, 0)
        turno_mock.fin = datetime(2026, 3, 22, 17, 0)
        empleado_mock = MagicMock()
        empleado_mock.EmpleadoID = 9
        empleado_mock.Nombre = 'Pedro'
        empleado_mock.rol = MagicMock()
        empleado_mock.rol.nombre = 'repartidor'
        row = (turno_mock, None, empleado_mock)
        session_mock.query.return_value.join.return_value.outerjoin.return_value.filter.return_value.all.return_value = [row]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.asistencia_hoy()
        assert result[0]['ausente'] is True
        assert result[0]['activo'] is False


class TestColasDetalle:
    def test_estructura_devuelta(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        pp_mock = MagicMock()
        pp_mock.PedidoID = 2341
        pp_mock.pedido = MagicMock()
        pp_mock.pedido.detalles = [MagicMock(), MagicMock(), MagicMock()]
        session_mock.query.return_value.filter.return_value.all.return_value = [pp_mock]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.colas_detalle()
        assert 'cola_picking' in result
        assert 'cola_reparto' in result


class TestPedidosPorEstado:
    def test_devuelve_dict_de_conteos(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        from models import Pedido
        session_mock.query.return_value.filter.return_value.group_by.return_value.all.return_value = [
            ('en_preparacion', 4),
            ('preparado', 2),
        ]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.pedidos_por_estado()
        assert isinstance(result, dict)


class TestAlertasTiempoReal:
    def _gestor_vacio(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        session_mock.query.return_value.filter.return_value.count.return_value = 0
        return gestor, session_mock

    def test_sin_condiciones_lista_vacia(self):
        gestor, session_mock = self._gestor_vacio()
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.alertas_tiempo_real()
        assert result == []

    def test_cola_picking_alta_genera_alerta(self):
        gestor = _make_gestor()
        session_mock = MagicMock()

        def side_effect_count(*args, **kwargs):
            mock = MagicMock()
            # cola picking ≥3 → alerta
            mock.filter.return_value.count.return_value = 3
            mock.filter.return_value.all.return_value = []
            return mock

        session_mock.query.side_effect = side_effect_count
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            # Parchamos submétodos para aislar
            with patch.object(gestor, '_alertas_ausencia', return_value=[]):
                with patch.object(gestor, '_alertas_pedidos_bloqueados', return_value=[]):
                    with patch.object(gestor, '_alertas_repartidores_inactivos', return_value=[]):
                        with patch.object(gestor, '_alertas_colas', return_value=[
                            {'tipo': 'cola_picking_alta', 'severidad': 'alta',
                             'mensaje': '3 pedidos en cola', 'pedidos_afectados': []}
                        ]):
                            result = gestor.alertas_tiempo_real()
        assert any(a['tipo'] == 'cola_picking_alta' for a in result)

    def test_resultado_tiene_tipo_severidad_mensaje(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        session_mock.query.return_value.filter.return_value.count.return_value = 0
        alerta_fake = {'tipo': 'cola_picking_alta', 'severidad': 'alta',
                       'mensaje': 'test', 'pedidos_afectados': []}
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with patch.object(gestor, '_alertas_ausencia', return_value=[alerta_fake]):
                with patch.object(gestor, '_alertas_colas', return_value=[]):
                    with patch.object(gestor, '_alertas_pedidos_bloqueados', return_value=[]):
                        with patch.object(gestor, '_alertas_repartidores_inactivos', return_value=[]):
                            result = gestor.alertas_tiempo_real()
        assert all({'tipo', 'severidad', 'mensaje'}.issubset(a.keys()) for a in result)


class TestResumenPeriodo:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.count.return_value = 10
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            desde = date(2026, 3, 15)
            hasta = date(2026, 3, 22)
            result = gestor.resumen_periodo(desde, hasta)
        claves = {
            'pedidos_completados', 'tasa_entrega_pct', 'tiempo_medio_ciclo_min',
            'ratio_cancelacion_pct', 'pedidos_por_forma_pago', 'dias_analizados'
        }
        assert claves == set(result.keys())

    def test_dias_analizados_correcto(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.count.return_value = 0
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.resumen_periodo(date(2026, 3, 15), date(2026, 3, 22))
        assert result['dias_analizados'] == 8  # inclusive

    def test_tasa_entrega_none_cuando_sin_datos(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.count.return_value = 0
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.resumen_periodo(date(2026, 3, 15), date(2026, 3, 22))
        assert result['tasa_entrega_pct'] is None


class TestMetricasPedidos:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_pedidos(date(2026, 3, 15), date(2026, 3, 22))
        assert 'throughput_por_dia' in result
        assert 'tiempo_medio_por_fase_min' in result
        assert 'distribucion_estado_final' in result

    def test_fases_presentes(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_pedidos(date(2026, 3, 15), date(2026, 3, 22))
        fases = result['tiempo_medio_por_fase_min']
        assert 'confirmacion_a_preparacion' in fases
        assert 'preparacion' in fases
        assert 'espera_repartidor' in fases
        assert 'reparto' in fases


class TestMetricasPicking:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        session_mock.query.return_value.filter.return_value.count.return_value = 0
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_picking(date(2026, 3, 15), date(2026, 3, 22))
        claves = {
            'tiempo_medio_picking_min', 'tiempo_medio_espera_asignacion_min',
            'items_total', 'items_encontrados_pct', 'items_sin_stock_pct',
            'items_sustituidos_pct', 'top_productos_sin_stock'
        }
        assert claves == set(result.keys())

    def test_porcentajes_suman_100_cuando_hay_items(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        # 10 items: 8 encontrado, 1 sin_stock, 1 sustituido
        items = []
        for _ in range(8):
            m = MagicMock(); m.estado = 'encontrado'; items.append(m)
        m1 = MagicMock(); m1.estado = 'sin_stock'; items.append(m1)
        m2 = MagicMock(); m2.estado = 'sustituido'; items.append(m2)
        session_mock.query.return_value.filter.return_value.all.return_value = items
        session_mock.query.return_value.filter.return_value.join.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with patch.object(gestor, '_picking_tiempos', return_value=(None, None)):
                result = gestor.metricas_picking(date(2026, 3, 15), date(2026, 3, 22))
        total = (result['items_encontrados_pct'] or 0) + (result['items_sin_stock_pct'] or 0) + (result['items_sustituidos_pct'] or 0)
        assert abs(total - 100) <= 1


class TestMetricasReparto:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_reparto(date(2026, 3, 15), date(2026, 3, 22))
        claves = {
            'tiempo_medio_entrega_min', 'tiempo_medio_espera_antes_salida_min',
            'tasa_entrega_exitosa_pct', 'entregas_por_repartidor'
        }
        assert claves == set(result.keys())

    def test_excluye_repartos_sin_hora_salida(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        r1 = MagicMock()
        r1.hora_salida = None  # debe excluirse
        r1.hora_entrega_real = datetime(2026, 3, 22, 14, 30)
        r1.estado = 'entregado'
        r2 = MagicMock()
        r2.hora_salida = datetime(2026, 3, 22, 14, 0)
        r2.hora_entrega_real = datetime(2026, 3, 22, 14, 30)
        r2.estado = 'entregado'
        r2.repartidor_id = 4
        r2.repartidor = MagicMock(); r2.repartidor.Nombre = 'Luis'
        session_mock.query.return_value.filter.return_value.all.return_value = [r1, r2]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_reparto(date(2026, 3, 15), date(2026, 3, 22))
        # Solo r2 tiene hora_salida → tiempo_medio debe calcularse sobre 1 reparto (30 min)
        assert result['tiempo_medio_entrega_min'] == 30


class TestRendimientoEmpleados:
    def test_devuelve_lista(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.rendimiento_empleados(date(2026, 3, 15), date(2026, 3, 22))
        assert isinstance(result, list)

    def test_productividad_cero_cuando_sin_horas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        emp = MagicMock()
        emp.EmpleadoID = 7
        emp.Nombre = 'Ana'
        emp.rol = MagicMock(); emp.rol.nombre = 'picker'
        session_mock.query.return_value.filter.return_value.all.return_value = [emp]
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with patch.object(gestor, '_horas_trabajadas', return_value=0.0):
                with patch.object(gestor, '_operaciones_empleado', return_value=[]):
                    result = gestor.rendimiento_empleados(date(2026, 3, 15), date(2026, 3, 22))
        assert result[0]['productividad_operaciones_hora'] == 0


class TestComparativaEmpleados:
    def test_requiere_rol(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.comparativa_empleados(date(2026, 3, 15), date(2026, 3, 22), 'picker')
        assert 'rol' in result
        assert result['rol'] == 'picker'
        assert 'ranking' in result
        assert 'media_equipo' in result

    def test_ranking_ordenado_por_productividad(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with patch.object(gestor, 'rendimiento_empleados', return_value=[
                {'empleado_id': 1, 'nombre': 'A', 'rol': 'picker',
                 'operaciones_completadas': 50, 'horas_trabajadas': 20,
                 'productividad_operaciones_hora': 2.5, 'tiempo_medio_operacion_min': 12,
                 'ratio_incidencias_pct': 3, 'puntualidad_media_min': 2},
                {'empleado_id': 2, 'nombre': 'B', 'rol': 'picker',
                 'operaciones_completadas': 80, 'horas_trabajadas': 20,
                 'productividad_operaciones_hora': 4.0, 'tiempo_medio_operacion_min': 9,
                 'ratio_incidencias_pct': 1, 'puntualidad_media_min': 0},
            ]):
                result = gestor.comparativa_empleados(date(2026, 3, 15), date(2026, 3, 22), 'picker')
        assert result['ranking'][0]['posicion'] == 1
        assert result['ranking'][0]['productividad_operaciones_hora'] == 4.0


class TestFichaEmpleado:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        emp_mock = MagicMock()
        emp_mock.EmpleadoID = 7
        emp_mock.Nombre = 'Ana'
        emp_mock.rol = MagicMock(); emp_mock.rol.nombre = 'picker'
        session_mock.query.return_value.filter.return_value.first.return_value = emp_mock
        session_mock.query.return_value.filter.return_value.all.return_value = []
        session_mock.query.return_value.join.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            with patch.object(gestor, '_horas_trabajadas', return_value=0.0):
                with patch.object(gestor, '_operaciones_empleado', return_value=[]):
                    from managers.gestor_empleado import GestorEmpleado
                    with patch.object(GestorEmpleado, 'puntualidad_empleado',
                                      return_value={'tasa_puntualidad_pct': 100, 'media_minutos_tarde': 0,
                                                    'tarde': 0, 'puntuales': 0}):
                        result = gestor.ficha_empleado(7, date(2026, 3, 15), date(2026, 3, 22))
        assert 'empleado_id' in result
        assert 'asistencia' in result
        assert 'puntualidad' in result
        assert 'rendimiento' in result
        assert 'evolucion_semanal' in result


class TestAsistenciaPeriodo:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.join.return_value.outerjoin.return_value.outerjoin.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.asistencia_periodo(date(2026, 3, 15), date(2026, 3, 22))
        assert 'tasa_asistencia_global_pct' in result
        assert 'tasa_puntualidad_global_pct' in result
        assert 'por_empleado' in result


class TestMetricasIncidencias:
    def test_claves_esperadas(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_incidencias(date(2026, 3, 15), date(2026, 3, 22))
        assert 'total' in result
        assert 'por_tipo' in result
        assert 'por_empleado' in result
        assert 'productos_mas_afectados' in result

    def test_tipos_presentes(self):
        gestor = _make_gestor()
        session_mock = MagicMock()
        session_mock.query.return_value.filter.return_value.all.return_value = []
        with patch.object(type(gestor), 'session', new_callable=PropertyMock, return_value=session_mock):
            result = gestor.metricas_incidencias(date(2026, 3, 15), date(2026, 3, 22))
        assert 'sin_stock' in result['por_tipo']
        assert 'entrega_fallida' in result['por_tipo']
        assert 'sustitucion' in result['por_tipo']
