function turnosApp() {
  return {
    tab: 'hoy',

    empleados: [],
    resumen: null,
    cargandoHoy: false,
    error: null,
    segundosParaActualizar: 30,
    ticksSinceLoad: 0,
    _pollTimer: null,
    _tickTimer: null,

    turnos: [],
    histTotal: 0,
    histPagina: 1,
    histPages: 1,
    cargandoHistorial: false,
    historialCargado: false,
    histFiltros: { desde: '', hasta: '', rol: '' },

    planTurnos: [],
    planCargando: false,
    planCargado: false,

    semanaBase: null,
    _diasSemana: [],
    _semanaTurnos: {},
    _empleadosSemana: [],

    modalAbierto: false,
    modalModo: 'crear',
    turnoEdicion: null,
    form: { empleado_id: '', fecha: '', hora_inicio: '', hora_fin: '', tipo: '', notas: '' },
    formError: null,
    formGuardando: false,
    empleadosDisponibles: [],
    empleadosCargados: false,

    init() {
      this.cargarHoy();
      this._pollTimer = setInterval(() => {
        this.segundosParaActualizar--;
        if (this.segundosParaActualizar <= 0) {
          this.cargarHoy();
        }
      }, 1000);
      this._tickTimer = setInterval(() => {
        this.ticksSinceLoad++;
      }, 60000);
      this.semanaBase = this.lunes(new Date());
    },

    async cargarHoy() {
      this.cargandoHoy = true;
      this.error = null;
      try {
        const resp = await fetch('/dashboard/turnos/hoy');
        if (!resp.ok) throw new Error('Error ' + resp.status);
        const data = await resp.json();
        this.empleados = [...data.empleados].sort((a, b) => {
          if (a.tiene_turno !== b.tiene_turno) return a.tiene_turno ? -1 : 1;
          if (a.activo !== b.activo) return a.activo ? -1 : 1;
          return (a.nombre || '').localeCompare(b.nombre || '', 'es');
        });
        this.resumen = data.resumen;
        this.ticksSinceLoad = 0;
        this.segundosParaActualizar = 30;
      } catch (e) {
        this.error = 'No se pudo cargar los turnos de hoy. ' + e.message;
      } finally {
        this.cargandoHoy = false;
      }
    },

    async cargarHistorial() {
      this.cargandoHistorial = true;
      try {
        const params = new URLSearchParams();
        if (this.histFiltros.desde) params.set('desde', this.histFiltros.desde);
        if (this.histFiltros.hasta) params.set('hasta', this.histFiltros.hasta);
        if (this.histFiltros.rol) params.set('rol', this.histFiltros.rol);
        params.set('page', this.histPagina);
        params.set('per_page', 25);

        const resp = await fetch('/dashboard/turnos/historial?' + params.toString());
        if (!resp.ok) throw new Error('Error ' + resp.status);
        const data = await resp.json();
        this.turnos = data.turnos;
        this.histTotal = data.total;
        this.histPagina = data.page;
        this.histPages = data.pages;
        this.historialCargado = true;
      } catch (e) {
        this.error = 'No se pudo cargar el historial. ' + e.message;
      } finally {
        this.cargandoHistorial = false;
      }
    },

    formatMinutos(min) {
      if (min === null || min === undefined) return '—';
      const h = Math.floor(min / 60);
      const m = min % 60;
      if (h > 0) return `${h}h ${String(m).padStart(2, '0')}min`;
      return `${m}min`;
    },

    formatHora(iso) {
      if (!iso) return '—';
      const d = new Date(iso);
      return d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    },

    horaTurnoToDate(hora) {
      if (!hora) return null;
      const [h, m] = String(hora).split(':').map(Number);
      if (Number.isNaN(h) || Number.isNaN(m)) return null;
      const d = new Date();
      d.setHours(h, m, 0, 0);
      return d;
    },

    minutosRetraso(emp) {
      if (!emp || !emp.tiene_turno || !emp.check_in_inicio || !emp.turno_hora_inicio) return 0;
      if (typeof emp.minutos_tarde === 'number' && emp.minutos_tarde > 0) return emp.minutos_tarde;
      const inicioTurno = this.horaTurnoToDate(emp.turno_hora_inicio);
      const checkin = new Date(emp.check_in_inicio);
      if (!inicioTurno || Number.isNaN(checkin.getTime())) return 0;
      return Math.max(0, Math.floor((checkin - inicioTurno) / 60000));
    },

    isNoPresentado(emp) {
      if (!emp || !emp.tiene_turno || emp.check_in_inicio || !emp.turno_hora_inicio) return false;
      const inicioTurno = this.horaTurnoToDate(emp.turno_hora_inicio);
      if (!inicioTurno) return false;
      return new Date() >= inicioTurno;
    },

    formatISO(date) {
      const y = date.getFullYear();
      const m = String(date.getMonth() + 1).padStart(2, '0');
      const d = String(date.getDate()).padStart(2, '0');
      return `${y}-${m}-${d}`;
    },

    lunes(date) {
      const d = new Date(date);
      const day = d.getDay();
      const diff = day === 0 ? -6 : 1 - day;
      d.setDate(d.getDate() + diff);
      d.setHours(0, 0, 0, 0);
      return d;
    },

    diasSemana() {
      if (!this.semanaBase) return [];
      return Array.from({ length: 7 }, (_, i) => {
        const d = new Date(this.semanaBase);
        d.setDate(d.getDate() + i);
        return d;
      });
    },

    semanaLabel() {
      const dias = this.diasSemana();
      const lun = dias[0];
      const dom = dias[6];
      const DIAS = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
      const MESES = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];
      const labelLun = `${DIAS[lun.getDay()]} ${lun.getDate()}`;
      const labelDom = `${DIAS[dom.getDay()]} ${dom.getDate()}`;
      const mismoMes = lun.getMonth() === dom.getMonth();
      if (mismoMes) {
        return `${labelLun} — ${labelDom} ${MESES[dom.getMonth()]} ${dom.getFullYear()}`;
      }
      return `${labelLun} ${MESES[lun.getMonth()]} — ${labelDom} ${MESES[dom.getMonth()]} ${dom.getFullYear()}`;
    },

    esHoy(date) {
      const hoy = new Date();
      return date.getFullYear() === hoy.getFullYear()
          && date.getMonth() === hoy.getMonth()
          && date.getDate() === hoy.getDate();
    },

    cellTurnos(empleadoId, dia) {
      const semana = this._semanaTurnos[String(empleadoId)] || {};
      return semana[this.formatISO(dia)] || [];
    },

    turnosDelDia(dia) {
      const fecha = this.formatISO(dia);
      return this.planTurnos.filter(t => t.fecha === fecha);
    },

    resumenRolesDia(dia) {
      const turnos = this.turnosDelDia(dia);
      return {
        pickers: turnos.filter(t => t.rol === 'picker').length,
        repartidores: turnos.filter(t => t.rol === 'repartidor').length,
      };
    },

    turnosEmpleadoSemana(empleadoId) {
      return this.planTurnos.filter(t => String(t.empleado_id) === String(empleadoId)).length;
    },

    inicialesEmpleado(nombre) {
      if (!nombre) return '—';
      const partes = String(nombre).trim().split(/\s+/).filter(Boolean);
      return partes.slice(0, 2).map(p => p[0].toUpperCase()).join('');
    },

    semanaTurnos() {
      const mapa = {};
      for (const t of this.planTurnos) {
        const eid = String(t.empleado_id);
        if (!mapa[eid]) mapa[eid] = {};
        if (!mapa[eid][t.fecha]) mapa[eid][t.fecha] = [];
        mapa[eid][t.fecha].push(t);
      }
      return mapa;
    },

    empleadosSemana() {
      const vistos = new Set();
      const lista = [];
      for (const t of this.planTurnos) {
        if (!vistos.has(t.empleado_id)) {
          vistos.add(t.empleado_id);
          lista.push({ id: t.empleado_id, nombre: t.empleado });
        }
      }
      lista.sort((a, b) => a.nombre.localeCompare(b.nombre));
      return lista;
    },

    cargar() {
      if (this.tab === 'hoy') this.cargarHoy();
      else if (this.tab === 'historial') this.cargarHistorial();
      else if (this.tab === 'plan') this.cargarPlan();
    },

    async cargarPlan() {
      this.planCargando = true;
      try {
        this._diasSemana = this.diasSemana();
        const desde = this.formatISO(this._diasSemana[0]);
        const hasta = this.formatISO(this._diasSemana[6]);
        const params = new URLSearchParams({ desde, hasta, per_page: 200 });
        const resp = await fetch('/dashboard/turnos/planificacion?' + params.toString());
        if (!resp.ok) throw new Error('Error ' + resp.status);
        const data = await resp.json();
        this.planTurnos = data.turnos || [];
        const idx = {};
        const emps = {};
        for (const t of this.planTurnos) {
          const eid = String(t.empleado_id);
          if (!idx[eid]) idx[eid] = {};
          if (!idx[eid][t.fecha]) idx[eid][t.fecha] = [];
          idx[eid][t.fecha].push(t);
          if (!emps[eid]) emps[eid] = { id: t.empleado_id, nombre: t.empleado, rol: t.rol };
        }
        this._semanaTurnos = idx;
        this._empleadosSemana = Object.values(emps).sort((a, b) => a.nombre.localeCompare(b.nombre, 'es'));
        this.planCargado = true;
      } catch (e) {
        this.error = 'No se pudo cargar el plan. ' + e.message;
      } finally {
        this.planCargando = false;
      }
    },

    async _cargarEmpleados() {
      if (this.empleadosCargados) return;
      try {
        const resp = await fetch('/dashboard/empleados');
        if (!resp.ok) throw new Error(resp.status);
        this.empleadosDisponibles = await resp.json();
        this.empleadosCargados = true;
      } catch (e) {
        this.formError = 'No se pudo cargar la lista de empleados.';
      }
    },

    async abrirModalCrear(empleadoId = null, fecha = null) {
      this.modalModo = 'crear';
      this.turnoEdicion = null;
      this.formError = null;
      this.form = {
        empleado_id: '',
        fecha: this.formatISO(new Date()),
        hora_inicio: '',
        hora_fin: '',
        tipo: '',
        notas: '',
      };
      await this._cargarEmpleados();
      if (empleadoId !== null) this.form.empleado_id = String(empleadoId);
      if (fecha !== null) this.form.fecha = fecha;
      this.modalAbierto = true;
    },

    sumarMinutos(date, minutos) {
      return new Date(date.getTime() + minutos * 60000);
    },

    formatHoraInput(date) {
      return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
    },

    async abrirModalCrearRapido(empleado) {
      const ahora = new Date();
      const inicio = this.sumarMinutos(ahora, 5);
      const fin = this.sumarMinutos(inicio, 240);

      await this.abrirModalCrear(empleado.id, this.formatISO(inicio));
      this.form.hora_inicio = this.formatHoraInput(inicio);
      this.form.hora_fin = this.formatHoraInput(fin);
      this.form.notas = this.form.notas || 'Alta rapida desde dashboard';
    },

    async abrirModalEditar(turno) {
      this.modalModo = 'editar';
      this.turnoEdicion = turno;
      this.formError = null;
      this.form = {
        empleado_id: turno.empleado_id,
        fecha: turno.fecha,
        hora_inicio: turno.hora_inicio || '',
        hora_fin: turno.hora_fin || '',
        tipo: turno.tipo || '',
        notas: turno.notas || '',
      };
      await this._cargarEmpleados();
      this.modalAbierto = true;
    },

    cerrarModal() {
      this.modalAbierto = false;
      this.formError = null;
    },

    async guardarTurno() {
      this.formError = null;
      this.formGuardando = true;
      try {
        let url;
        let body;
        if (this.modalModo === 'crear') {
          url = '/dashboard/turnos/crear';
          body = {
            empleado_id: parseInt(this.form.empleado_id),
            fecha: this.form.fecha,
            hora_inicio: this.form.hora_inicio,
            hora_fin: this.form.hora_fin,
            tipo: this.form.tipo || null,
            notas: this.form.notas || null,
          };
        } else {
          url = `/dashboard/turnos/${this.turnoEdicion.id}/editar`;
          body = {
            hora_inicio: this.form.hora_inicio,
            hora_fin: this.form.hora_fin,
            tipo: this.form.tipo,
            notas: this.form.notas,
          };
        }
        const resp = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await resp.json();
        if (!data.ok) { this.formError = data.error || 'Error al guardar.'; return; }
        this.cerrarModal();
        this.cargarPlan();
      } catch (e) {
        this.formError = 'Error de red. Inténtalo de nuevo.';
      } finally {
        this.formGuardando = false;
      }
    },

    async confirmarCancelar(turnoId) {
      if (!confirm('¿Cancelar este turno? Esta acción no se puede deshacer.')) return;
      try {
        const resp = await fetch(`/dashboard/turnos/${turnoId}/cancelar`, { method: 'POST' });
        const data = await resp.json();
        if (!data.ok) { alert(data.error || 'Error al cancelar.'); return; }
        this.cargarPlan();
      } catch (e) {
        alert('Error de red al cancelar el turno.');
      }
    },

    async confirmarEliminar(turnoId) {
      if (!confirm('¿Eliminar este turno de la base de datos? Esta acción no se puede deshacer.')) return;
      try {
        const resp = await fetch(`/dashboard/turnos/${turnoId}/eliminar`, { method: 'POST' });
        const data = await resp.json();
        if (!data.ok) { alert(data.error || 'Error al eliminar.'); return; }
        this.cargarPlan();
      } catch (e) {
        alert('Error de red al eliminar el turno.');
      }
    },
  };
}
