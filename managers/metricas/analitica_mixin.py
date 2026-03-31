import statistics
from datetime import date, datetime


class GestorMetricasAnaliticaMixin:
    def resumen_periodo(self, desde: date, hasta: date) -> dict:
        from models import Pedido, Reparto
        from sqlalchemy import func

        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        completados = (
            s.query(Pedido)
            .filter(
                Pedido.Estado == 'entregado',
                Pedido.FechaCreacion >= desde_dt,
                Pedido.FechaCreacion <= hasta_dt,
            )
            .count()
        )

        cancelados = (
            s.query(Pedido)
            .filter(
                Pedido.Estado == 'cancelado',
                Pedido.FechaCreacion >= desde_dt,
                Pedido.FechaCreacion <= hasta_dt,
            )
            .count()
        )

        total_pedidos = completados + cancelados

        repartos = (
            s.query(Reparto)
            .filter(
                Reparto.updated_at >= desde_dt,
                Reparto.updated_at <= hasta_dt,
                Reparto.estado.in_(['entregado', 'no_entregado']),
            )
            .all()
        )
        entregados_r = sum(1 for r in repartos if r.estado == 'entregado')
        total_r = len(repartos)
        tasa_entrega = round(entregados_r * 100 / total_r) if total_r > 0 else None

        ratio_cancelacion = (
            round(cancelados * 100 / total_pedidos) if total_pedidos > 0 else None
        )

        tiempo_ciclo = self._tiempo_medio_ciclo_periodo(desde, hasta)

        rows_pago = (
            s.query(Pedido.forma_pago, func.count(Pedido.PedidoID))
            .filter(
                Pedido.Estado == 'entregado',
                Pedido.FechaCreacion >= desde_dt,
                Pedido.FechaCreacion <= hasta_dt,
            )
            .group_by(Pedido.forma_pago)
            .all()
        )
        pedidos_por_forma_pago = {fp: cnt for fp, cnt in rows_pago if fp}

        dias = (hasta - desde).days + 1

        return {
            'pedidos_completados': completados,
            'tasa_entrega_pct': tasa_entrega,
            'tiempo_medio_ciclo_min': tiempo_ciclo,
            'ratio_cancelacion_pct': ratio_cancelacion,
            'pedidos_por_forma_pago': pedidos_por_forma_pago,
            'dias_analizados': dias,
        }

    def metricas_pedidos(self, desde: date, hasta: date) -> dict:
        from models import HistorialEstadoPedido, Pedido
        from sqlalchemy import Date, func

        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        rows_dia = (
            s.query(
                func.cast(Pedido.FechaCreacion, Date).label('dia'),
                Pedido.Estado,
                func.count(Pedido.PedidoID),
            )
            .filter(
                Pedido.Estado.in_(['entregado', 'cancelado']),
                Pedido.FechaCreacion >= desde_dt,
                Pedido.FechaCreacion <= hasta_dt,
            )
            .group_by(func.cast(Pedido.FechaCreacion, Date), Pedido.Estado)
            .all()
        )
        dias_dict: dict = {}
        for dia, estado, cnt in rows_dia:
            key = str(dia)
            if key not in dias_dict:
                dias_dict[key] = {'fecha': key, 'completados': 0, 'cancelados': 0}
            if estado == 'entregado':
                dias_dict[key]['completados'] = cnt
            elif estado == 'cancelado':
                dias_dict[key]['cancelados'] = cnt
        throughput = sorted(dias_dict.values(), key=lambda x: x['fecha'])

        pares_fases = [
            ('confirmacion_a_preparacion', ['pagado', 'contra_reembolso'], 'en_preparacion'),
            ('preparacion', 'en_preparacion', 'preparado'),
            ('espera_repartidor', 'preparado', 'en_reparto'),
            ('reparto', 'en_reparto', 'entregado'),
        ]
        pedidos_entregados = (
            s.query(Pedido.PedidoID)
            .filter(
                Pedido.Estado == 'entregado',
                Pedido.FechaCreacion >= desde_dt,
                Pedido.FechaCreacion <= hasta_dt,
            )
            .all()
        )
        ids = [r.PedidoID for r in pedidos_entregados]

        tiempos_por_fase: dict = {}
        for nombre_fase, estado_a, estado_b in pares_fases:
            tiempos = []
            for pid in ids:
                if isinstance(estado_a, list):
                    registros = (
                        s.query(HistorialEstadoPedido)
                        .filter(
                            HistorialEstadoPedido.pedido_id == pid,
                            HistorialEstadoPedido.estado_nuevo.in_(estado_a + [estado_b]),
                        )
                        .order_by(HistorialEstadoPedido.cambiado_en)
                        .all()
                    )
                    mapa = {}
                    for r in registros:
                        if r.estado_nuevo not in mapa:
                            mapa[r.estado_nuevo] = r.cambiado_en
                    t_a = min((mapa[e] for e in estado_a if e in mapa), default=None)
                    t_b = mapa.get(estado_b)
                    if t_a and t_b:
                        tiempos.append(max(0, round((t_b - t_a).total_seconds() / 60)))
                else:
                    t = self._tiempo_entre_estados(pid, estado_a, estado_b)
                    if t is not None:
                        tiempos.append(t)
            tiempos_por_fase[nombre_fase] = (
                round(statistics.median(tiempos)) if tiempos else None
            )

        dist_rows = (
            s.query(Pedido.Estado, func.count(Pedido.PedidoID))
            .filter(
                Pedido.Estado.in_(self._ESTADOS_TERMINALES),
                Pedido.FechaCreacion >= desde_dt,
                Pedido.FechaCreacion <= hasta_dt,
            )
            .group_by(Pedido.Estado)
            .all()
        )
        distribucion = {e: c for e, c in dist_rows}

        return {
            'throughput_por_dia': throughput,
            'tiempo_medio_por_fase_min': tiempos_por_fase,
            'distribucion_estado_final': distribucion,
        }

    def metricas_picking(self, desde: date, hasta: date) -> dict:
        from models import PickingItem, PickingPedido, Producto
        from sqlalchemy import func

        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        pp_completados = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.completado_en >= desde_dt,
                PickingPedido.completado_en <= hasta_dt,
                PickingPedido.estado == 'completado',
            )
            .all()
        )
        pp_ids = [pp.id for pp in pp_completados]

        items = s.query(PickingItem).filter(PickingItem.picking_id.in_(pp_ids)).all()
        items_total = len(items)
        if items_total > 0:
            encontrados = sum(1 for i in items if i.estado == 'encontrado')
            sin_stock = sum(1 for i in items if i.estado == 'sin_stock')
            sustituidos = sum(1 for i in items if i.estado == 'sustituido')
            items_encontrados_pct = round(encontrados * 100 / items_total)
            items_sin_stock_pct = round(sin_stock * 100 / items_total)
            items_sustituidos_pct = round(sustituidos * 100 / items_total)
        else:
            items_encontrados_pct = items_sin_stock_pct = items_sustituidos_pct = None

        tiempo_medio_picking_min, tiempo_medio_espera_asignacion_min = self._picking_tiempos(
            desde_dt,
            hasta_dt,
        )

        top_sin_stock_rows = (
            s.query(
                PickingItem.pedido_detalle_id,
                Producto.Nombre,
                func.count(PickingItem.id).label('veces'),
            )
            .join(Producto, PickingItem.producto_sustituto_id == Producto.ProductoID, isouter=True)
            .join(PickingPedido, PickingItem.picking_id == PickingPedido.id)
            .filter(
                PickingItem.estado == 'sin_stock',
                PickingPedido.completado_en >= desde_dt,
                PickingPedido.completado_en <= hasta_dt,
            )
            .group_by(PickingItem.pedido_detalle_id, Producto.Nombre)
            .order_by(func.count(PickingItem.id).desc())
            .limit(10)
            .all()
        )
        top_productos_sin_stock = [
            {'pedido_detalle_id': pid, 'nombre': nombre, 'veces_sin_stock': veces}
            for pid, nombre, veces in top_sin_stock_rows
        ]

        return {
            'tiempo_medio_picking_min': tiempo_medio_picking_min,
            'tiempo_medio_espera_asignacion_min': tiempo_medio_espera_asignacion_min,
            'items_total': items_total,
            'items_encontrados_pct': items_encontrados_pct,
            'items_sin_stock_pct': items_sin_stock_pct,
            'items_sustituidos_pct': items_sustituidos_pct,
            'top_productos_sin_stock': top_productos_sin_stock,
        }

    def _picking_tiempos(self, desde_dt: datetime, hasta_dt: datetime):
        from models import PickingPedido

        s = self.session
        pickings_completados = (
            s.query(PickingPedido)
            .filter(
                PickingPedido.estado == 'completado',
                PickingPedido.completado_en >= desde_dt,
                PickingPedido.completado_en <= hasta_dt,
            )
            .all()
        )
        tiempos_picking = []
        tiempos_espera = []
        for pp in pickings_completados:
            if pp.created_at and pp.completado_en:
                mins = round((pp.completado_en - pp.created_at).total_seconds() / 60)
                tiempos_picking.append(mins)
            t = self._tiempo_entre_estados(pp.pedido_id, 'pagado', 'en_preparacion')
            if t is not None:
                tiempos_espera.append(t)
        tiempo_medio_picking = round(statistics.mean(tiempos_picking)) if tiempos_picking else None
        tiempo_espera_asig = round(statistics.mean(tiempos_espera)) if tiempos_espera else None
        return tiempo_medio_picking, tiempo_espera_asig

    def metricas_reparto(self, desde: date, hasta: date) -> dict:
        from models import Empleado, Reparto

        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        repartos = (
            s.query(Reparto)
            .filter(
                Reparto.updated_at >= desde_dt,
                Reparto.updated_at <= hasta_dt,
                Reparto.estado.in_(['entregado', 'no_entregado']),
            )
            .all()
        )

        total = len(repartos)
        entregados = [r for r in repartos if r.estado == 'entregado']
        tasa_exitosa = round(len(entregados) * 100 / total) if total > 0 else None

        con_salida = [r for r in entregados if r.hora_salida is not None]
        tiempos_entrega = []
        for r in con_salida:
            if r.hora_entrega_real and r.hora_salida:
                mins = round((r.hora_entrega_real - r.hora_salida).total_seconds() / 60)
                tiempos_entrega.append(mins)
        tiempo_medio_entrega = round(statistics.mean(tiempos_entrega)) if tiempos_entrega else None

        tiempos_espera_salida = []
        for r in con_salida:
            t = self._tiempo_entre_estados(r.pedido_id, 'preparado', 'en_reparto')
            if t is not None:
                tiempos_espera_salida.append(t)
        tiempo_espera_salida = (
            round(statistics.mean(tiempos_espera_salida)) if tiempos_espera_salida else None
        )

        por_empleado: dict = {}
        for r in repartos:
            eid = r.repartidor_id
            if not eid:
                continue
            if eid not in por_empleado:
                por_empleado[eid] = {
                    'entregas': 0,
                    'tiempos': [],
                    'total': 0,
                    'nombre': None,
                }
            por_empleado[eid]['total'] += 1
            if r.estado == 'entregado':
                por_empleado[eid]['entregas'] += 1
                if r.hora_salida and r.hora_entrega_real:
                    mins = round((r.hora_entrega_real - r.hora_salida).total_seconds() / 60)
                    por_empleado[eid]['tiempos'].append(mins)

        entregas_por_repartidor = []
        for eid, data in por_empleado.items():
            emp = s.query(Empleado).filter(Empleado.EmpleadoID == eid).first()
            nombre = emp.Nombre if emp else f'Empleado {eid}'
            tasa = round(data['entregas'] * 100 / data['total']) if data['total'] > 0 else None
            t_medio = round(statistics.mean(data['tiempos'])) if data['tiempos'] else None
            entregas_por_repartidor.append(
                {
                    'empleado_id': eid,
                    'nombre': nombre,
                    'entregas': data['entregas'],
                    'tiempo_medio_min': t_medio,
                    'tasa_exito_pct': tasa,
                }
            )
        entregas_por_repartidor.sort(key=lambda x: x['entregas'], reverse=True)

        return {
            'tiempo_medio_entrega_min': tiempo_medio_entrega,
            'tiempo_medio_espera_antes_salida_min': tiempo_espera_salida,
            'tasa_entrega_exitosa_pct': tasa_exitosa,
            'entregas_por_repartidor': entregas_por_repartidor,
        }

    def metricas_incidencias(self, desde: date, hasta: date) -> dict:
        from models import Empleado, PickingItem, PickingPedido, Reparto
        from sqlalchemy import func

        s = self.session
        desde_dt = datetime.combine(desde, datetime.min.time())
        hasta_dt = datetime.combine(hasta, datetime.max.time())

        items_inc = (
            s.query(PickingItem, PickingPedido)
            .join(PickingPedido, PickingItem.picking_id == PickingPedido.id)
            .filter(
                PickingItem.estado.in_(['sin_stock', 'sustituido']),
                PickingPedido.completado_en >= desde_dt,
                PickingPedido.completado_en <= hasta_dt,
            )
            .all()
        )

        repartos_fallidos = (
            s.query(Reparto)
            .filter(
                Reparto.estado == 'no_entregado',
                Reparto.updated_at >= desde_dt,
                Reparto.updated_at <= hasta_dt,
            )
            .all()
        )

        sin_stock = sum(1 for item, _ in items_inc if item.estado == 'sin_stock')
        sustitucion = sum(1 for item, _ in items_inc if item.estado == 'sustituido')
        entrega_fallida = len(repartos_fallidos)
        total = sin_stock + sustitucion + entrega_fallida

        por_emp_picking: dict = {}
        for item, pp in items_inc:
            if pp.empleado_id is None:
                continue
            eid = pp.empleado_id
            por_emp_picking[eid] = por_emp_picking.get(eid, 0) + 1

        por_emp_reparto: dict = {}
        for r in repartos_fallidos:
            if r.repartidor_id is None:
                continue
            por_emp_reparto[r.repartidor_id] = por_emp_reparto.get(r.repartidor_id, 0) + 1

        todos_eids = set(por_emp_picking) | set(por_emp_reparto)
        por_empleado_list = []
        for eid in todos_eids:
            emp = s.query(Empleado).filter(Empleado.EmpleadoID == eid).first()
            nombre = emp.Nombre if emp else f'Empleado {eid}'
            total_inc_emp = por_emp_picking.get(eid, 0) + por_emp_reparto.get(eid, 0)
            rol_emp = emp.rol.nombre if emp and emp.rol else 'picker'
            ops = self._operaciones_empleado(eid, rol_emp, desde, hasta)
            ratio = round(total_inc_emp * 100 / len(ops)) if ops else None
            por_empleado_list.append(
                {
                    'empleado_id': eid,
                    'nombre': nombre,
                    'total_incidencias': total_inc_emp,
                    'ratio_sobre_operaciones_pct': ratio,
                }
            )
        por_empleado_list.sort(key=lambda x: x['total_incidencias'], reverse=True)

        top_rows = (
            s.query(PickingItem.pedido_detalle_id, func.count(PickingItem.id).label('veces'))
            .join(PickingPedido, PickingItem.picking_id == PickingPedido.id)
            .filter(
                PickingItem.estado == 'sin_stock',
                PickingPedido.completado_en >= desde_dt,
                PickingPedido.completado_en <= hasta_dt,
            )
            .group_by(PickingItem.pedido_detalle_id)
            .order_by(func.count(PickingItem.id).desc())
            .limit(10)
            .all()
        )
        productos_mas_afectados = [
            {'pedido_detalle_id': pid, 'veces_sin_stock': veces} for pid, veces in top_rows
        ]

        return {
            'total': total,
            'por_tipo': {
                'sin_stock': sin_stock,
                'entrega_fallida': entrega_fallida,
                'sustitucion': sustitucion,
            },
            'por_empleado': por_empleado_list,
            'productos_mas_afectados': productos_mas_afectados,
        }
