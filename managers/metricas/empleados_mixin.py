import statistics
from datetime import date, datetime, timedelta


class GestorMetricasEmpleadosMixin:
    def rendimiento_empleados(self, desde: date, hasta: date, rol: str | None = None) -> list[dict]:
        from models import Empleado, PickingItem, PickingPedido, Reparto, Rol

        s = self.session
        query = s.query(Empleado)
        if rol:
            query = query.join(Rol, Empleado.rol_id == Rol.id).filter(Rol.nombre == rol)
        else:
            query = query.filter(Empleado.activo == True)
        empleados = query.all()

        result = []
        for emp in empleados:
            rol_nombre = emp.rol.nombre if emp.rol else None
            horas = self._horas_trabajadas(emp.EmpleadoID, desde, hasta)
            ops = self._operaciones_empleado(emp.EmpleadoID, rol_nombre, desde, hasta)
            num_ops = len(ops)
            productividad = round(num_ops / horas, 2) if horas > 0 else 0

            if rol_nombre == 'picker' and ops:
                tiempos = [
                    round((op.completado_en - op.created_at).total_seconds() / 60)
                    for op in ops
                    if op.created_at and op.completado_en
                ]
                tiempo_medio = round(statistics.mean(tiempos)) if tiempos else None
            elif rol_nombre == 'repartidor' and ops:
                tiempos = [
                    round((op.hora_entrega_real - op.hora_salida).total_seconds() / 60)
                    for op in ops
                    if op.hora_salida and op.hora_entrega_real
                ]
                tiempo_medio = round(statistics.mean(tiempos)) if tiempos else None
            else:
                tiempo_medio = None

            if rol_nombre == 'picker':
                todos_items = (
                    s.query(PickingItem)
                    .join(PickingPedido, PickingItem.picking_id == PickingPedido.id)
                    .filter(
                        PickingPedido.empleado_id == emp.EmpleadoID,
                        PickingPedido.completado_en >= datetime.combine(
                            desde,
                            datetime.min.time(),
                        ),
                        PickingPedido.completado_en <= datetime.combine(
                            hasta,
                            datetime.max.time(),
                        ),
                    )
                    .all()
                )
                total_items = len(todos_items)
                inc = sum(1 for i in todos_items if i.estado in ('sin_stock', 'sustituido'))
                ratio_inc = round(inc * 100 / total_items) if total_items > 0 else 0
            else:
                todos_repartos = (
                    s.query(Reparto)
                    .filter(
                        Reparto.repartidor_id == emp.EmpleadoID,
                        Reparto.estado.in_(['entregado', 'no_entregado']),
                        Reparto.updated_at >= datetime.combine(desde, datetime.min.time()),
                        Reparto.updated_at <= datetime.combine(hasta, datetime.max.time()),
                    )
                    .all()
                )
                total_rep = len(todos_repartos)
                no_ent = sum(1 for r in todos_repartos if r.estado == 'no_entregado')
                ratio_inc = round(no_ent * 100 / total_rep) if total_rep > 0 else 0

            puntualidad_media = None
            try:
                from managers.gestor_empleado import GestorEmpleado

                ge = GestorEmpleado()
                punt_data = ge.puntualidad_empleado(emp.EmpleadoID, desde, hasta)
                puntualidad_media = punt_data.get('media_minutos_tarde')
            except Exception:
                pass

            result.append(
                {
                    'empleado_id': emp.EmpleadoID,
                    'nombre': emp.Nombre,
                    'rol': rol_nombre,
                    'operaciones_completadas': num_ops,
                    'horas_trabajadas': horas,
                    'productividad_operaciones_hora': productividad,
                    'tiempo_medio_operacion_min': tiempo_medio,
                    'ratio_incidencias_pct': ratio_inc,
                    'puntualidad_media_min': puntualidad_media,
                }
            )
        return result

    def comparativa_empleados(self, desde: date, hasta: date, rol: str) -> dict:
        empleados_data = self.rendimiento_empleados(desde, hasta, rol=rol)
        ranking = sorted(
            empleados_data,
            key=lambda x: x['productividad_operaciones_hora'],
            reverse=True,
        )
        for i, emp in enumerate(ranking):
            emp['posicion'] = i + 1

        con_ops = [e for e in empleados_data if e['operaciones_completadas'] > 0]
        if con_ops:
            media_prod = round(
                statistics.mean(e['productividad_operaciones_hora'] for e in con_ops),
                2,
            )
            tiempos = [
                e['tiempo_medio_operacion_min']
                for e in con_ops
                if e['tiempo_medio_operacion_min'] is not None
            ]
            media_tiempo = round(statistics.mean(tiempos)) if tiempos else None
            ratios = [e['ratio_incidencias_pct'] for e in con_ops]
            media_ratio = round(statistics.mean(ratios)) if ratios else None
        else:
            media_prod = media_tiempo = media_ratio = None

        return {
            'rol': rol,
            'periodo': {'desde': str(desde), 'hasta': str(hasta)},
            'ranking': ranking,
            'media_equipo': {
                'productividad_operaciones_hora': media_prod,
                'tiempo_medio_operacion_min': media_tiempo,
                'ratio_incidencias_pct': media_ratio,
            },
        }

    def ficha_empleado(self, empleado_id: int, desde: date, hasta: date) -> dict:
        from managers.gestor_empleado import GestorEmpleado
        from models import Ausencia, CheckIn, Empleado, Turno

        s = self.session
        emp = s.query(Empleado).filter(Empleado.EmpleadoID == empleado_id).first()
        if not emp:
            return {}
        rol_nombre = emp.rol.nombre if emp.rol else None

        turnos = (
            s.query(Turno)
            .filter(Turno.empleado_id == empleado_id, Turno.fecha >= desde, Turno.fecha <= hasta)
            .all()
        )
        dias_planificados = len(turnos)
        checkins = (
            s.query(CheckIn)
            .filter(CheckIn.empleado_id == empleado_id, CheckIn.fecha >= desde, CheckIn.fecha <= hasta)
            .all()
        )
        dias_trabajados = len(checkins)
        ausencias = (
            s.query(Ausencia)
            .filter(Ausencia.empleado_id == empleado_id, Ausencia.fecha >= desde, Ausencia.fecha <= hasta)
            .count()
        )
        tasa_asistencia = (
            round(dias_trabajados * 100 / dias_planificados) if dias_planificados > 0 else None
        )

        gestor_emp = GestorEmpleado()
        punt_data = gestor_emp.puntualidad_empleado(empleado_id, desde, hasta)

        horas = self._horas_trabajadas(empleado_id, desde, hasta)
        ops = self._operaciones_empleado(empleado_id, rol_nombre, desde, hasta)
        num_ops = len(ops)
        productividad = round(num_ops / horas, 2) if horas > 0 else 0
        if rol_nombre == 'picker' and ops:
            tiempos = [
                round((op.completado_en - op.created_at).total_seconds() / 60)
                for op in ops
                if op.created_at and op.completado_en
            ]
        elif rol_nombre == 'repartidor' and ops:
            tiempos = [
                round((op.hora_entrega_real - op.hora_salida).total_seconds() / 60)
                for op in ops
                if op.hora_salida and op.hora_entrega_real
            ]
        else:
            tiempos = []
        tiempo_medio = round(statistics.mean(tiempos)) if tiempos else None

        evolucion = self._evolucion_semanal(empleado_id, rol_nombre, desde, hasta)

        return {
            'empleado_id': empleado_id,
            'nombre': emp.Nombre,
            'rol': rol_nombre,
            'asistencia': {
                'dias_planificados': dias_planificados,
                'dias_trabajados': dias_trabajados,
                'ausencias': ausencias,
                'tasa_asistencia_pct': tasa_asistencia,
            },
            'puntualidad': punt_data,
            'rendimiento': {
                'operaciones_completadas': num_ops,
                'horas_trabajadas': horas,
                'productividad_operaciones_hora': productividad,
                'tiempo_medio_operacion_min': tiempo_medio,
            },
            'evolucion_semanal': evolucion,
        }

    def _evolucion_semanal(self, empleado_id: int, rol: str, desde: date, hasta: date) -> list[dict]:
        """Punto por semana natural (lunes-domingo) dentro del rango."""
        semanas = []
        lunes = desde - timedelta(days=desde.weekday())
        while lunes <= hasta:
            fin_semana = lunes + timedelta(days=6)
            ops = self._operaciones_empleado(empleado_id, rol, lunes, fin_semana)
            if ops:
                if rol == 'picker':
                    tiempos = [
                        round((op.completado_en - op.created_at).total_seconds() / 60)
                        for op in ops
                        if op.created_at and op.completado_en
                    ]
                else:
                    tiempos = [
                        round((op.hora_entrega_real - op.hora_salida).total_seconds() / 60)
                        for op in ops
                        if op.hora_salida and op.hora_entrega_real
                    ]
                tiempo_medio = round(statistics.mean(tiempos)) if tiempos else None
            else:
                tiempo_medio = None
            semanas.append(
                {
                    'semana_inicio': str(lunes),
                    'operaciones': len(ops),
                    'tiempo_medio_min': tiempo_medio,
                }
            )
            lunes += timedelta(weeks=1)
        return semanas

    def asistencia_periodo(self, desde: date, hasta: date) -> dict:
        from models import Ausencia, CheckIn, Empleado, Turno

        s = self.session
        rows = (
            s.query(Turno, CheckIn, Empleado)
            .join(Empleado, Turno.empleado_id == Empleado.EmpleadoID)
            .outerjoin(
                CheckIn,
                (CheckIn.empleado_id == Turno.empleado_id) & (CheckIn.fecha == Turno.fecha),
            )
            .outerjoin(
                Ausencia,
                (Ausencia.empleado_id == Turno.empleado_id) & (Ausencia.fecha == Turno.fecha),
            )
            .filter(Turno.fecha >= desde, Turno.fecha <= hasta)
            .all()
        )

        por_emp: dict = {}
        for turno, checkin, empleado in rows:
            eid = empleado.EmpleadoID
            if eid not in por_emp:
                por_emp[eid] = {
                    'empleado_id': eid,
                    'nombre': empleado.Nombre,
                    'dias_planificados': 0,
                    'dias_trabajados': 0,
                    'ausencias': 0,
                    'minutos_tarde': [],
                    'checkins_con_turno': 0,
                }
            por_emp[eid]['dias_planificados'] += 1
            if checkin:
                por_emp[eid]['dias_trabajados'] += 1
                if checkin.minutos_tarde is not None:
                    por_emp[eid]['minutos_tarde'].append(checkin.minutos_tarde)
                    por_emp[eid]['checkins_con_turno'] += 1
            else:
                por_emp[eid]['ausencias'] += 1

        por_empleado_list = []
        total_planificados = total_trabajados = 0
        total_puntuales = total_check = 0
        for eid, data in por_emp.items():
            total_planificados += data['dias_planificados']
            total_trabajados += data['dias_trabajados']
            min_tarde = data['minutos_tarde']
            tasa_puntualidad = None
            media_tarde = None
            if min_tarde:
                puntuales = sum(1 for m in min_tarde if m <= 5)
                total_puntuales += puntuales
                total_check += len(min_tarde)
                tasa_puntualidad = round(puntuales * 100 / len(min_tarde))
                media_tarde = round(statistics.mean(min_tarde), 1)
            tasa_asistencia = (
                round(data['dias_trabajados'] * 100 / data['dias_planificados'])
                if data['dias_planificados'] > 0
                else None
            )
            por_empleado_list.append(
                {
                    'empleado_id': eid,
                    'nombre': data['nombre'],
                    'dias_planificados': data['dias_planificados'],
                    'dias_trabajados': data['dias_trabajados'],
                    'ausencias': data['ausencias'],
                    'tasa_asistencia_pct': tasa_asistencia,
                    'tasa_puntualidad_pct': tasa_puntualidad,
                    'media_minutos_tarde': media_tarde,
                }
            )

        tasa_global_asistencia = (
            round(total_trabajados * 100 / total_planificados)
            if total_planificados > 0
            else None
        )
        tasa_global_puntualidad = (
            round(total_puntuales * 100 / total_check) if total_check > 0 else None
        )

        return {
            'tasa_asistencia_global_pct': tasa_global_asistencia,
            'tasa_puntualidad_global_pct': tasa_global_puntualidad,
            'por_empleado': por_empleado_list,
        }
