let mapaLeaflet = null;
let mapaMarkers = [];
let marcadorTienda = null;

function dashboard() {
  return {
    metricas: {},
    pedidos: [],
    picking: [],
    repartidores: { empleados: [], pedidos_sin_asignar: [] },
    alertas: [],
    eventos: [],
    busqueda: '',
    filtroEstado: '',
    quickFilter: 'todos',
    horaActual: '',
    lastUpdatedAt: null,
    empleadosModal: [],
    modalError: '',
    modalPicker: { visible: false, pedido_id: null, empleado_id: '' },
    modalRepartidor: { visible: false, pedido_id: null, empleado_id: '' },
    modalCancelacion: { visible: false, motivo: '' },
    modalReasignar: { visible: false, picking_id: null, empleado_id: '' },
    modalSustituir: {
      visible: false,
      item: null,
      busqueda: '',
      productos: [],
      productoSeleccionado: null,
      cantidadSustituir: 1,
    },
    panel: { visible: false, pedido: null },
    ui: { pickersCollapsed: {}, repartidoresCollapsed: {} },
    now: new Date(),
    toast: { visible: false, msg: '', error: false },

    filtrosRapidos: [
      { id: 'todos', label: 'Todos' },
      { id: 'urgentes', label: 'Urgentes' },
      { id: 'sin_picker', label: 'Sin cocinero' },
      { id: 'sin_repartidor', label: 'Sin repartidor' },
      { id: 'en_reparto', label: 'En reparto' },
      { id: 'incidencias', label: 'Incidencias' },
    ],

    get alertasError() {
      return this.alertas.filter(a => a.nivel === 'error');
    },

    pedidoPorId(pedidoId) {
      return this.pedidos.find(p => p.pedido_id === pedidoId) || null;
    },

    alertReason(alerta) {
      if (alerta.tipo === 'sin_repartidor') return 'Sin repartidor asignado';
      if (alerta.tipo === 'pedido_retrasado') return 'Sin cocinero asignado';
      return 'Incidencia operativa';
    },

    alertElapsed(alerta) {
      const pedido = this.pedidoPorId(alerta.pedido_id);
      const minutos = alerta.minutos ?? pedido?.minutos_en_estado ?? null;
      return this.formatMinutos(minutos);
    },

    alertSummaryHeadline() {
      if (!this.alertasError.length) return 'Sin incidencias criticas activas.';
      const principal = this.alertasError[0];
      if (principal.tipo === 'sin_repartidor') return 'Hay pedidos preparados bloqueados antes de salir a reparto.';
      if (principal.tipo === 'pedido_retrasado') return 'Hay pedidos acumulando retraso por encima del umbral operativo.';
      return 'Hay incidencias operativas que requieren decision inmediata.';
    },

    alertTopCategoryLabel() {
      if (!this.alertasError.length) return 'Sin riesgo';
      const principal = this.alertasError[0];
      if (principal.tipo === 'sin_repartidor') return 'Salida a reparto';
      if (principal.tipo === 'pedido_retrasado') return 'Retraso operativo';
      return 'Revision manual';
    },

    alertSeverityLabel(alerta) {
      if (alerta.tipo === 'sin_repartidor') return 'Critica';
      return 'Urgente';
    },

    alertSeverityClass(alerta) {
      if (alerta.tipo === 'sin_repartidor') return 'bg-red-100 text-red-700';
      return 'bg-amber-100 text-amber-700';
    },

    alertTypeLabel(alerta) {
      if (alerta.tipo === 'sin_repartidor') return 'Reparto';
      if (alerta.tipo === 'pedido_retrasado') return 'SLA';
      return 'Incidencia';
    },

    alertTitle(alerta) {
      if (alerta.tipo === 'sin_repartidor') return 'Sin repartidor asignado';
      if (alerta.tipo === 'pedido_retrasado') return 'Retraso operativo';
      return alerta.mensaje;
    },

    alertDetail(alerta) {
      if (alerta.tipo === 'sin_repartidor') return 'Sin repartidor asignado';
      if (alerta.tipo === 'pedido_retrasado') return 'Fuera de tiempo objetivo';
      return alerta.mensaje;
    },

    alertContextPrimary(alerta) {
      if (alerta.tipo === 'sin_repartidor') return 'Siguiente paso: asignar reparto';
      if (alerta.tipo === 'pedido_retrasado') return `Tiempo acumulado: ${this.formatMinutos(alerta.minutos)}`;
      return 'Revision necesaria';
    },

    alertContextSecondary(alerta) {
      const pedido = this.pedidoPorId(alerta.pedido_id);
      if (!pedido) return '';
      if (alerta.tipo === 'sin_repartidor') return pedido.direccion_entrega || '';
      return pedido.cliente_nombre || pedido.direccion_entrega || '';
    },

    alertActionLabel(alerta) {
      if (alerta.tipo === 'sin_repartidor') return 'Asignar repartidor';
      return 'Abrir pedido';
    },

    async resolverAlerta(alerta) {
      if (!alerta?.pedido_id) return;
      const pedido = this.pedidoPorId(alerta.pedido_id);
      if (alerta.tipo === 'sin_repartidor') {
        await this.abrirModalRepartidor(
          alerta.pedido_id,
          pedido?.reparto?.repartidor_nombre || null,
        );
        return;
      }
      this.abrirPedidoPorId(alerta.pedido_id);
    },

    get pedidosUrgentes() {
      return this.pedidos.filter(p => (p.minutos_en_estado || 0) > 30 || p.es_alerta);
    },

    get sinPicker() {
      return this.picking.filter(
        pk =>
          pk.tipo === 'sin_asignar' ||
          pk.tipo === 'sin_picker' ||
          (pk.estado_picking !== 'completado' && !pk.empleado?.nombre),
      );
    },

    get sinPickerOrdenados() {
      return [...this.sinPicker].sort(
        (a, b) =>
          new Date(a.fecha_creacion || 0).getTime() -
          new Date(b.fecha_creacion || 0).getTime(),
      );
    },

    get sinRepartidor() {
      return this.repartidores.pedidos_sin_asignar || [];
    },

    get sinRepartidorOrdenados() {
      return [...this.sinRepartidor].sort(
        (a, b) =>
          new Date(a.fecha_creacion || 0).getTime() -
          new Date(b.fecha_creacion || 0).getTime(),
      );
    },

    get pedidosEnCamino() {
      return this.pedidos.filter(p => p.reparto?.estado === 'en_camino').length;
    },

    get pickersEquipo() {
      const known = new Map();

      (this.repartidores.empleados || []).forEach(emp => {
        const rol = String(emp.rol || '').toLowerCase();
        if (rol.includes('picker')) {
          known.set(emp.empleado_id, {
            empleado_id: emp.empleado_id,
            nombre: emp.nombre,
            telefono: emp.telefono,
            pickings: [],
            pedidos_activos: 0,
            items_total: 0,
            items_completados: 0,
            items_pendientes: 0,
          });
        }
      });

      this.picking.forEach(pk => {
        if (!pk.empleado?.id) return;
        if (!known.has(pk.empleado.id)) {
          known.set(pk.empleado.id, {
            empleado_id: pk.empleado.id,
            nombre: pk.empleado.nombre,
            telefono: null,
            pickings: [],
            pedidos_activos: 0,
            items_total: 0,
            items_completados: 0,
            items_pendientes: 0,
          });
        }

        const picker = known.get(pk.empleado.id);
        const minutosActivos = this.workerMinutes(pk.iniciado_en || pk.fecha_creacion);
        picker.pickings.push({
          ...pk,
          minutos_activos: minutosActivos,
        });
        picker.pedidos_activos += 1;
        picker.items_total += pk.items_total || 0;
        picker.items_completados += pk.items_completados || 0;
        picker.items_pendientes += pk.items_pendientes || 0;
      });

      return [...known.values()]
        .map(picker => ({
          ...picker,
          carga: this.workerLoad('picker', picker.pedidos_activos),
          max_minutos_activo: Math.max(
            0,
            ...picker.pickings.map(pk => pk.minutos_activos || 0),
          ),
        }))
        .sort(
          (a, b) =>
            b.carga.score - a.carga.score ||
            b.max_minutos_activo - a.max_minutos_activo ||
            b.items_pendientes - a.items_pendientes ||
            a.nombre.localeCompare(b.nombre),
        );
    },

    get repartidoresEquipo() {
      return (this.repartidores.empleados || [])
        .filter(emp => {
          const rol = String(emp.rol || '').toLowerCase();
          return rol.includes('repart') || emp.pedidos_activos.length > 0;
        })
        .map(emp => ({
          ...emp,
          pedidos_activos: emp.pedidos_activos.map(r => ({
            ...r,
            minutos_activos: this.workerMinutes(r.hora_salida),
          })),
        }))
        .map(emp => ({
          ...emp,
          carga: this.workerLoad('repartidor', emp.pedidos_activos.length),
          max_minutos_activo: Math.max(
            0,
            ...emp.pedidos_activos.map(r => r.minutos_activos || 0),
          ),
        }))
        .sort(
          (a, b) =>
            b.carga.score - a.carga.score ||
            b.max_minutos_activo - a.max_minutos_activo ||
            a.nombre.localeCompare(b.nombre),
        );
    },

    get pedidosVisibles() {
      return this.pedidos
        .filter(p => !this.filtroEstado || p.estado === this.filtroEstado)
        .filter(p => this.matchesQuickFilter(p))
        .filter(p => this.matchesBusqueda(p))
        .sort((a, b) => b.pedido_id - a.pedido_id);
    },

    async init() {
      this.actualizarHora();
      setInterval(() => this.actualizarHora(), 1000);
      await this.cargarTodo();
      setInterval(() => this.cargarTodo(), 60000);
      setInterval(() => {
        this.now = new Date();
      }, 30000);
      this.$nextTick(() => this.iniciarMapa());
    },

    actualizarHora() {
      const ahora = new Date();
      this.horaActual = ahora.toLocaleTimeString('es-ES', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    },

    async cargarTodo() {
      await Promise.all([
        this.cargar('metricas', '/dashboard/metricas'),
        this.cargarPedidos(),
        this.cargar('picking', '/dashboard/picking'),
        this.cargar('repartidores', '/dashboard/repartidores'),
        this.cargar('alertas', '/dashboard/alertas'),
        this.cargar('eventos', '/dashboard/eventos'),
      ]);
      if (this.panel.visible && this.panel.pedido) {
        const actualizado = this.pedidos.find(
          p => p.pedido_id === this.panel.pedido.pedido_id,
        );
        this.panel.pedido = actualizado ?? null;
        if (!this.panel.pedido) this.panel.visible = false;
      }
      this.lastUpdatedAt = new Date();
      this.actualizarMapa();
    },

    async cargar(campo, url) {
      try {
        const r = await fetch(url);
        if (r.ok) this[campo] = await r.json();
      } catch (e) {}
    },

    async cargarPedidos() {
      try {
        const r = await fetch('/dashboard/pedidos-activos');
        if (r.ok) this.pedidos = await r.json();
      } catch (e) {}
    },

    matchesBusqueda(p) {
      if (!this.busqueda) return true;
      const needle = this.busqueda.toLowerCase();
      return [
        p.pedido_id,
        p.cliente_nombre,
        p.direccion_entrega,
        p.picking?.picker_nombre,
        p.reparto?.repartidor_nombre,
      ]
        .filter(Boolean)
        .some(v => String(v).toLowerCase().includes(needle));
    },

    matchesQuickFilter(p) {
      switch (this.quickFilter) {
        case 'urgentes':
          return this.prioridadPedidoValor(p) >= 3;
        case 'sin_picker':
          return !p.picking || !p.picking.picker_nombre;
        case 'sin_repartidor':
          return p.estado === 'preparado' && (!p.reparto || !p.reparto.repartidor_nombre);
        case 'en_reparto':
          return p.reparto?.estado === 'en_camino';
        case 'incidencias':
          return Boolean(p.es_alerta);
        default:
          return true;
      }
    },

    prioridadPedidoValor(p) {
      if (p.es_alerta) return 4;
      if ((p.minutos_en_estado || 0) > 30) return 3;
      if (p.estado === 'preparado' && (!p.reparto || !p.reparto.repartidor_nombre)) return 3;
      if (!p.picking && ['pagado', 'contra_reembolso'].includes(p.estado)) return 2;
      if (p.reparto?.estado === 'en_camino') return 2;
      return 1;
    },

    prioridadPedidoLabel(p) {
      const value = this.prioridadPedidoValor(p);
      if (value >= 4) return 'Crítico';
      if (value === 3) return 'Urgente';
      if (value === 2) return 'En curso';
      return 'Estable';
    },

    prioridadPedidoClass(p) {
      const value = this.prioridadPedidoValor(p);
      if (value >= 4) return 'bg-red-100 text-red-700';
      if (value === 3) return 'bg-amber-100 text-amber-700';
      if (value === 2) return 'bg-sky-100 text-sky-800';
      return 'bg-slate-100 text-slate-700';
    },

    filterClass(id) {
      const on = this.quickFilter === id;
      const map = {
        todos: on
          ? 'border-sky-300 bg-sky-100 text-sky-900 shadow-sm'
          : 'border-slate-200 bg-white/80 text-slate-600 hover:bg-slate-50',
        urgentes: on
          ? 'border-red-400 bg-red-100 text-red-900 shadow-sm'
          : 'border-red-200 bg-red-50/70 text-red-700 hover:bg-red-50',
        sin_picker: on
          ? 'border-purple-400 bg-purple-100 text-purple-900 shadow-sm'
          : 'border-purple-200 bg-purple-50/70 text-purple-700 hover:bg-purple-50',
        sin_repartidor: on
          ? 'border-purple-400 bg-purple-100 text-purple-900 shadow-sm'
          : 'border-purple-200 bg-purple-50/70 text-purple-700 hover:bg-purple-50',
        en_reparto: on
          ? 'border-orange-400 bg-orange-100 text-orange-900 shadow-sm'
          : 'border-orange-200 bg-orange-50/70 text-orange-700 hover:bg-orange-50',
        incidencias: on
          ? 'border-red-400 bg-red-100 text-red-900 shadow-sm'
          : 'border-red-200 bg-red-50/70 text-red-700 hover:bg-red-50',
      };
      return map[id] ??
        (on
          ? 'border-sky-300 bg-sky-100 text-sky-900 shadow-sm'
          : 'border-slate-200 bg-white/80 text-slate-600 hover:bg-slate-50');
    },

    filterCount(filterId) {
      return this.pedidos.filter(p => {
        switch (filterId) {
          case 'urgentes':
            return this.prioridadPedidoValor(p) >= 3;
          case 'sin_picker':
            return !p.picking || !p.picking.picker_nombre;
          case 'sin_repartidor':
            return p.estado === 'preparado' && (!p.reparto || !p.reparto.repartidor_nombre);
          case 'en_reparto':
            return p.reparto?.estado === 'en_camino';
          case 'incidencias':
            return Boolean(p.es_alerta);
          default:
            return true;
        }
      }).length;
    },

    lastUpdatedText() {
      if (!this.lastUpdatedAt) return 'Cargando datos...';
      const diffSec = Math.max(
        0,
        Math.round((Date.now() - this.lastUpdatedAt.getTime()) / 1000),
      );
      if (diffSec < 5) return 'Actualizado ahora';
      if (diffSec < 60) return `Actualizado hace ${diffSec}s`;
      const min = Math.round(diffSec / 60);
      return `Actualizado hace ${min} min`;
    },

    workerMinutes(iso) {
      if (!iso) return 0;
      return Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
    },

    workerLoad(tipo, activos) {
      if (activos <= 0) return { label: 'Libre', score: 0, summary: 'Sin carga ahora' };
      if (tipo === 'picker') {
        if (activos >= 4) return { label: 'Saturado', score: 3, summary: 'Demasiados pickings a la vez' };
        if (activos >= 3) return { label: 'Cargado', score: 2, summary: 'Necesita vigilancia' };
        return { label: 'Normal', score: 1, summary: 'Carga asumible' };
      }
      if (activos >= 3) return { label: 'Saturado', score: 3, summary: 'Ruta cargada' };
      if (activos >= 2) return { label: 'Cargado', score: 2, summary: 'Varias entregas activas' };
      return { label: 'Normal', score: 1, summary: 'Carga asumible' };
    },

    workerLoadTone(carga, tipo = 'picker') {
      if (!carga) return 'bg-slate-600 text-white';
      if (carga.score >= 3) return 'bg-red-600 text-white';
      if (carga.score === 2) return 'bg-amber-500 text-white';
      if (carga.score === 1) {
        return tipo === 'picker'
          ? 'bg-sky-600 text-white'
          : 'bg-orange-500 text-white';
      }
      return 'bg-emerald-600 text-white';
    },

    workerLoadBorder(carga, tipo) {
      if (!carga) return 'border-slate-200 bg-white';
      if (carga.score >= 3) {
        return 'border-red-200 bg-gradient-to-b from-white to-red-50/60 shadow-red-100/70';
      }
      if (carga.score === 2) {
        return 'border-amber-200 bg-gradient-to-b from-white to-amber-50/60 shadow-amber-100/70';
      }
      if (carga.score === 1) {
        return tipo === 'picker'
          ? 'border-sky-200 bg-gradient-to-b from-white to-sky-50/60 shadow-sky-100/70'
          : 'border-orange-200 bg-gradient-to-b from-white to-orange-50/60 shadow-orange-100/70';
      }
      return 'border-emerald-200 bg-gradient-to-b from-white to-emerald-50/60 shadow-emerald-100/70';
    },

    async asignarSiguienteAPicker(empleadoId) {
      const pendiente = this.sinPickerOrdenados[0];
      if (!pendiente) {
        this.mostrarToast('No hay pedidos pendientes de cocinero', true);
        return;
      }
      const pedidoId = pendiente.pedido_id;
      if (pendiente.picking_id) {
        await this.reasignarPicker(pendiente.picking_id, empleadoId);
        return;
      }
      const r = await fetch('/dashboard/picking/asignar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pedido_id: pedidoId, empleado_id: empleadoId }),
      });
      const data = await r.json();
      if (r.ok) {
        this.mostrarToast(data.mensaje || `Pedido #${pedidoId} asignado`);
        this.cargarTodo();
      } else {
        this.mostrarToast(data.error || 'No se pudo aceptar en cocina', true);
      }
    },

    async asignarSiguienteARepartidor(empleadoId) {
      const pendiente = this.sinRepartidorOrdenados[0];
      if (!pendiente) {
        this.mostrarToast('No hay pedidos pendientes de repartidor', true);
        return;
      }
      const r = await fetch('/dashboard/reparto/asignar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pedido_id: pendiente.pedido_id, empleado_id: empleadoId }),
      });
      const data = await r.json();
      if (r.ok) {
        this.mostrarToast(data.mensaje || `Pedido #${pendiente.pedido_id} asignado`);
        this.cargarTodo();
      } else {
        this.mostrarToast(data.error || 'No se pudo asignar el repartidor', true);
      }
    },

    isPickerCollapsed(empleadoId) {
      return this.ui.pickersCollapsed[empleadoId] ?? false;
    },

    togglePickerCollapse(empleadoId) {
      this.ui.pickersCollapsed[empleadoId] = !this.isPickerCollapsed(empleadoId);
    },

    isRepartidorCollapsed(empleadoId) {
      return this.ui.repartidoresCollapsed[empleadoId] ?? false;
    },

    toggleRepartidorCollapse(empleadoId) {
      this.ui.repartidoresCollapsed[empleadoId] = !this.isRepartidorCollapsed(empleadoId);
    },

    iniciarMapa() {
      const el = document.getElementById('mapa');
      if (!el || mapaLeaflet) return;
      mapaLeaflet = L.map('mapa').setView([40.0041, -2.9980], 14);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap',
        maxZoom: 18,
      }).addTo(mapaLeaflet);
      mapaLeaflet.on('popupopen', e => {
        const btn = e.popup.getElement()?.querySelector('[data-ir-pedido]');
        if (btn) {
          btn.onclick = () => {
            const id = parseInt(btn.dataset.irPedido);
            mapaLeaflet.closePopup();
            this.filtrarPorPedido(id);
          };
        }
      });
    },

    mapaColorPedido(p) {
      if (p.reparto) return '#f97316';
      if (p.estado === 'preparado') return '#22c55e';
      if (p.picking) return '#3b82f6';
      return '#9ca3af';
    },

    mapaColorEstado(estado) {
      const colores = {
        pagado: '#10b981',
        contra_reembolso: '#8b5cf6',
        en_preparacion: '#3b82f6',
        preparado: '#6366f1',
        en_reparto: '#f97316',
      };
      return colores[estado] || '#6b7280';
    },

    mapaEstadoCorto(estado) {
      const labels = {
        pagado: 'PAG',
        contra_reembolso: 'CR',
        en_preparacion: 'PICK',
        preparado: 'LISTO',
        en_reparto: 'REP',
      };
      return labels[estado] || '?';
    },

    actualizarMapa() {
      if (!mapaLeaflet) return;

      if (!marcadorTienda) {
        const iconTienda = L.divIcon({
          className: '',
          html: `<div style="background:#1f2937;color:#fff;border:2px solid #fff;border-radius:6px;width:34px;height:34px;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 5px rgba(0,0,0,.45);font-size:18px;">🏪</div>`,
          iconSize: [34, 34],
          iconAnchor: [17, 17],
        });
        marcadorTienda = L.marker([40.008778, -3.010905], { icon: iconTienda })
          .bindPopup('<b>Panchi</b><br>Punto de origen')
          .addTo(mapaLeaflet);
      }

      mapaMarkers.forEach(m => m.remove());
      mapaMarkers = [];

      const estadoLabel = {
        pagado: 'Pagado',
        contra_reembolso: 'Contra reembolso',
        en_preparacion: 'En cocina',
        preparado: 'Preparado',
        en_reparto: 'En reparto',
      };

      this.pedidos
        .filter(p => p.lat != null && p.lng != null)
        .forEach(p => {
          const color = this.mapaColorPedido(p);
          const icon = L.divIcon({
            className: '',
            html: `<div style="background:${color};color:#fff;border:3px solid rgba(255,255,255,0.9);border-radius:50%;width:36px;height:36px;display:flex;align-items:center;justify-content:center;box-shadow:0 2px 8px rgba(0,0,0,.3);font-size:11px;font-weight:900;letter-spacing:-0.5px;">${p.pedido_id}</div>`,
            iconSize: [36, 36],
            iconAnchor: [18, 18],
          });
          const label = estadoLabel[p.estado] || p.estado;
          const marker = L.marker([p.lat, p.lng], { icon })
            .bindPopup(`
              <div style="min-width:160px">
                <b style="font-size:14px">#${p.pedido_id}</b>
                <span style="margin-left:6px;background:${color};color:#fff;padding:1px 6px;border-radius:4px;font-size:11px">${label}</span><br>
                <span style="font-size:12px;color:#555">${p.direccion_entrega}</span><br>
                <b>${p.total.toFixed(2)}€</b>
                <button data-ir-pedido="${p.pedido_id}" style="margin-top:6px;width:100%;background:#1d4ed8;color:#fff;border:none;border-radius:4px;padding:4px 0;font-size:12px;cursor:pointer">
                  Ver en lista
                </button>
              </div>
            `)
            .addTo(mapaLeaflet);
          mapaMarkers.push(marker);
        });
    },

    async abrirModalPicker(pedido_id) {
      this.modalPicker = { visible: true, pedido_id, empleado_id: '' };
      this.modalError = '';
      const r = await fetch('/dashboard/empleados?operacion=true');
      this.empleadosModal = r.ok ? await r.json() : [];
    },

    async asignarCocinaEquipo(pedido_id) {
      const r = await fetch('/dashboard/picking/asignar-cocina', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pedido_id }),
      });
      const data = await r.json();
      if (r.ok) {
        this.mostrarToast(data.mensaje);
        this.cargarTodo();
      } else {
        this.mostrarToast(data.error || 'Error al aceptar en cocina', true);
      }
    },

    async confirmarAsignarPicker() {
      this.modalError = '';
      const r = await fetch('/dashboard/picking/asignar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pedido_id: this.modalPicker.pedido_id,
          empleado_id: parseInt(this.modalPicker.empleado_id),
        }),
      });
      const data = await r.json();
      if (r.ok) {
        this.modalPicker.visible = false;
        this.mostrarToast(data.mensaje);
        this.cargarTodo();
      } else {
        this.modalError = data.error;
      }
    },

    async completarPicking(picking_id) {
      const r = await fetch(`/dashboard/picking/${picking_id}/completar`, { method: 'POST' });
      const data = await r.json();
      if (r.ok) {
        this.mostrarToast(data.mensaje);
        this.cargarTodo();
      } else {
        this.mostrarToast(data.error, true);
      }
    },

    async abrirModalReasignar(picking_id) {
      this.modalReasignar = { visible: true, picking_id, empleado_id: '' };
      this.modalError = '';
      const r = await fetch('/dashboard/empleados?operacion=true');
      this.empleadosModal = r.ok ? await r.json() : [];
    },

    async confirmarReasignarPicker() {
      this.modalError = '';
      if (!this.modalReasignar.empleado_id) {
        this.modalError = 'Selecciona un cocinero';
        return;
      }
      await this.reasignarPicker(
        this.modalReasignar.picking_id,
        parseInt(this.modalReasignar.empleado_id),
      );
      if (!this.modalError) this.modalReasignar.visible = false;
    },

    async reasignarPicker(picking_id, nuevo_empleado_id) {
      const r = await fetch(`/dashboard/picking/${picking_id}/reasignar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ empleado_id: nuevo_empleado_id }),
      });
      const data = await r.json();
      if (!r.ok) {
        this.modalError = data.error || 'Error al reasignar';
        this.mostrarToast(data.error || 'Error al reasignar', true);
        return;
      }
      this.mostrarToast(data.mensaje);
      await this.cargar('picking', '/dashboard/picking');
      await this.cargarPedidos();
    },

    async desasignarPicker(picking_id) {
      if (!confirm('¿Quitar el cocinero de este pedido? Quedará sin asignar.')) return;
      await this.reasignarPicker(picking_id, null);
    },

    async abrirModalRepartidor(pedido_id, repartidorActual) {
      this.modalRepartidor = {
        visible: true,
        pedido_id,
        empleado_id: '',
        repartidor_actual: repartidorActual || null,
      };
      this.modalError = '';
      const r = await fetch('/dashboard/empleados?operacion=true');
      this.empleadosModal = r.ok ? await r.json() : [];
    },

    async confirmarAsignarRepartidor() {
      this.modalError = '';
      if (this.modalRepartidor.repartidor_actual) {
        const confirmado = confirm(
          `Este pedido ya tiene asignado a ${this.modalRepartidor.repartidor_actual}. ¿Quieres reasignarlo?`,
        );
        if (!confirmado) return;
      }
      const r = await fetch('/dashboard/reparto/asignar', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pedido_id: this.modalRepartidor.pedido_id,
          empleado_id: parseInt(this.modalRepartidor.empleado_id),
        }),
      });
      const data = await r.json();
      if (r.ok) {
        this.modalRepartidor.visible = false;
        this.mostrarToast(data.mensaje);
        this.cargarTodo();
      } else {
        this.modalError = data.error;
      }
    },

    async marcarSalida(reparto_id) {
      const r = await fetch(`/dashboard/reparto/${reparto_id}/salida`, { method: 'POST' });
      const data = await r.json();
      if (r.ok) {
        this.mostrarToast(data.mensaje);
        this.cargarTodo();
      } else {
        this.mostrarToast(data.error, true);
      }
    },

    async marcarEntregado(reparto_id) {
      const r = await fetch(`/dashboard/reparto/${reparto_id}/entregar`, { method: 'POST' });
      const data = await r.json();
      if (r.ok) {
        this.mostrarToast(data.mensaje);
        this.cargarTodo();
      } else {
        this.mostrarToast(data.error, true);
      }
    },

    puedeCancel(estado) {
      return ['Pendiente', 'enlace', 'confirmando-pago', 'contra_reembolso', 'en_preparacion', 'pagado'].includes(estado);
    },

    puedeModificarItems(estado) {
      return ['pagado', 'contra_reembolso', 'en_preparacion'].includes(estado);
    },

    abrirCancelacion() {
      this.modalCancelacion = { visible: true, motivo: '' };
      this.modalError = '';
    },

    async confirmarCancelacion() {
      this.modalError = '';
      const r = await fetch(`/dashboard/pedido/${this.panel.pedido.pedido_id}/cancelar`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ motivo: this.modalCancelacion.motivo }),
      });
      const data = await r.json();
      if (r.ok) {
        this.modalCancelacion.visible = false;
        this.cerrarPanel();
        this.mostrarToast(data.mensaje);
        this.cargarTodo();
      } else {
        this.modalError = data.error;
      }
    },

    async eliminarItem(item) {
      if (!confirm(`¿Eliminar "${item.nombre}" del pedido?`)) return;
      const r = await fetch(
        `/dashboard/pedido/${this.panel.pedido.pedido_id}/item/${item.detalle_id}/eliminar`,
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' },
      );
      const data = await r.json();
      if (r.ok) {
        this.mostrarToast(data.mensaje);
        this.cargarTodo();
      } else {
        this.mostrarToast(data.error, true);
      }
    },

    abrirSustituir(item) {
      this.modalSustituir = {
        visible: true,
        item,
        busqueda: '',
        productos: [],
        productoSeleccionado: null,
        cantidadSustituir: item.cantidad,
      };
      this.modalError = '';
    },

    async buscarProductosSustitucion() {
      if (!this.modalSustituir.busqueda.trim()) {
        this.modalSustituir.productos = [];
        return;
      }
      const r = await fetch(`/dashboard/productos?q=${encodeURIComponent(this.modalSustituir.busqueda)}`);
      this.modalSustituir.productos = r.ok ? await r.json() : [];
    },

    async confirmarSustitucion() {
      this.modalError = '';
      const { item, productoSeleccionado, cantidadSustituir } = this.modalSustituir;
      const r = await fetch(
        `/dashboard/pedido/${this.panel.pedido.pedido_id}/item/${item.detalle_id}/sustituir`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            producto_sustituto_id: productoSeleccionado.id,
            cantidad_a_sustituir: parseInt(cantidadSustituir),
          }),
        },
      );
      const data = await r.json();
      if (r.ok) {
        this.modalSustituir.visible = false;
        this.mostrarToast(data.mensaje);
        this.cargarTodo();
      } else {
        this.modalError = data.error;
      }
    },

    filtrarPorPedido(pedido_id) {
      this.filtroEstado = '';
      this.$nextTick(() => {
        const filas = document.querySelectorAll('tbody tr');
        filas.forEach(f => {
          if (f.textContent.includes('#' + pedido_id)) {
            f.scrollIntoView({ behavior: 'smooth', block: 'center' });
            f.classList.add('ring-2', 'ring-blue-400');
            setTimeout(() => f.classList.remove('ring-2', 'ring-blue-400'), 2500);
          }
        });
      });
    },

    abrirPedidoPorId(pedido_id) {
      const pedido = this.pedidos.find(p => p.pedido_id === pedido_id);
      if (pedido) {
        this.abrirPanel(pedido);
        return;
      }
      this.filtrarPorPedido(pedido_id);
    },

    abrirPanel(p) {
      this.panel = { visible: true, pedido: p };
    },

    cerrarPanel() {
      this.panel.visible = false;
    },

    panelMinutos(p) {
      if (!p?.fecha_creacion) return null;
      return Math.round(
        (new Date(p.fecha_creacion).getTime() + 20 * 60 * 1000 - Date.now()) / 60000,
      );
    },

    panelPrioridadClases(mins) {
      if (mins === null) return 'bg-gray-100 text-gray-500';
      if (mins > 8) return 'bg-green-100 text-green-700';
      if (mins >= 3) return 'bg-yellow-100 text-yellow-800';
      if (mins >= 0) return 'bg-orange-100 text-orange-700';
      return 'bg-red-100 text-red-700';
    },

    panelMinutosTexto(mins) {
      if (mins === null) return '';
      if (mins > 0) return mins + ' min';
      if (mins === 0) return '¡Ahora!';
      return '+' + Math.abs(mins) + ' min tarde';
    },

    panelPaymentLabel(p) {
      if (!p) return '—';
      return p.forma_pago === 'efectivo' ? 'Efectivo en entrega' : 'Online confirmado';
    },

    panelDeliveryLabel(estado) {
      return {
        asignado: 'Asignado',
        en_camino: 'En camino',
        entregado: 'Entregado',
        no_entregado: 'No entregado',
        cancelado: 'Cancelado',
      }[estado] || estado || 'sin reparto';
    },

    panelActionTitle(p) {
      if (!p) return 'Sin selección';
      if (!p.picking && ['pagado', 'contra_reembolso'].includes(p.estado)) return 'Asignar preparación';
      if (p.picking && p.picking.estado !== 'completado' && !p.picking.picker_nombre) return 'Aceptar en cocina';
      if (p.picking && p.picking.estado !== 'completado' && p.picking.picker_nombre) return 'Cerrar preparación';
      if (!p.reparto && p.estado === 'preparado') return 'Asignar reparto';
      if (p.reparto?.estado === 'asignado') return 'Mandar a calle';
      if (p.reparto?.estado === 'en_camino') return 'Confirmar entrega';
      if (p.reparto?.estado === 'entregado') return 'Pedido completado';
      return 'Seguimiento';
    },

    panelActionSummary(p) {
      if (!p) return '';
      if (!p.picking && ['pagado', 'contra_reembolso'].includes(p.estado)) {
        return 'El pedido está listo para entrar en cocina.';
      }
      if (p.picking && p.picking.estado !== 'completado' && !p.picking.picker_nombre) {
        return 'Existe preparación creada pero sin responsable asignado.';
      }
      if (p.picking && p.picking.estado !== 'completado' && p.picking.picker_nombre) {
        return `Cocina en curso con ${p.picking.picker_nombre}. Revisa si ya puede cerrarse.`;
      }
      if (!p.reparto && p.estado === 'preparado') {
        return 'El pedido ya está preparado y solo falta asignar un repartidor.';
      }
      if (p.reparto?.estado === 'asignado') {
        return 'El repartidor ya está asignado. El siguiente paso es marcar salida.';
      }
      if (p.reparto?.estado === 'en_camino') {
        return 'El pedido está en calle. Confirma la entrega solo cuando el repartidor lo haya cerrado.';
      }
      if (p.reparto?.estado === 'entregado') {
        return 'Flujo completado. Utiliza esta ficha para revisar trazabilidad o incidencias.';
      }
      return 'Usa esta ficha para revisar estado, tiempos y responsables del pedido.';
    },

    panelActionBadgeLabel(p) {
      if (!p) return '';
      if ((p.minutos_en_estado || 0) > 30 || p.es_alerta) return 'Urgente';
      if (p.reparto?.estado === 'en_camino' || p.picking?.estado === 'en_proceso') return 'Activo';
      if (p.reparto?.estado === 'entregado') return 'Cerrado';
      return 'Normal';
    },

    panelActionBadgeClass(p) {
      if (!p) return 'bg-slate-100 text-slate-600';
      if ((p.minutos_en_estado || 0) > 30 || p.es_alerta) return 'bg-red-100 text-red-700';
      if (p.reparto?.estado === 'entregado') return 'bg-emerald-100 text-emerald-700';
      if (p.reparto?.estado === 'en_camino' || p.picking?.estado === 'en_proceso') return 'bg-sky-100 text-sky-800';
      return 'bg-slate-100 text-slate-600';
    },

    panelActionTone(p) {
      if (!p) return 'text-slate-600';
      if ((p.minutos_en_estado || 0) > 30 || p.es_alerta) return 'text-red-700';
      if (p.reparto?.estado === 'entregado') return 'text-emerald-700';
      if (p.reparto?.estado === 'en_camino' || p.picking?.estado === 'en_proceso') return 'text-sky-800';
      return 'text-slate-700';
    },

    panelTimeline(p) {
      if (!p) return [];
      const steps = [
        {
          key: 'creado',
          label: 'Pedido recibido',
          done: Boolean(p.fecha_creacion),
          time: this.horaCorta(p.fecha_creacion),
          detail: 'Entrada inicial del pedido en la operación.',
          doneClass: 'bg-slate-900',
        },
        {
          key: 'picking_asignado',
          label: 'Cocinero asignado',
          done: Boolean(p.picking?.asignado_en),
          time: this.horaCorta(p.picking?.asignado_en),
          detail: p.picking?.picker_nombre
            ? `Responsable: ${p.picking.picker_nombre}`
            : 'Pendiente de responsable de cocina.',
          doneClass: 'bg-sky-600',
        },
        {
          key: 'picking_inicio',
          label: 'Cocina iniciada',
          done: Boolean(p.picking?.iniciado_en),
          time: this.horaCorta(p.picking?.iniciado_en),
          detail: p.picking?.iniciado_en
            ? `Lleva ${this.minutosDesde(p.picking?.iniciado_en)}`
            : 'Todavía no se ha iniciado la preparación.',
          doneClass: 'bg-sky-600',
        },
        {
          key: 'picking_fin',
          label: 'Cocina completada',
          done: Boolean(p.picking?.completado_en),
          time: this.horaCorta(p.picking?.completado_en),
          detail: p.picking?.completado_en
            ? 'Preparación terminada.'
            : 'Pendiente de cerrar preparación.',
          doneClass: 'bg-emerald-600',
        },
        {
          key: 'reparto_asignado',
          label: 'Repartidor asignado',
          done: Boolean(p.reparto?.asignado_en),
          time: this.horaCorta(p.reparto?.asignado_en),
          detail: p.reparto?.repartidor_nombre
            ? `Responsable: ${p.reparto.repartidor_nombre}`
            : 'Aún no tiene repartidor.',
          doneClass: 'bg-orange-500',
        },
        {
          key: 'salida',
          label: 'Salida a reparto',
          done: Boolean(p.reparto?.hora_salida),
          time: this.horaCorta(p.reparto?.hora_salida),
          detail: p.reparto?.hora_salida
            ? `En ruta desde hace ${this.minutosDesde(p.reparto?.hora_salida)}`
            : 'Pendiente de salida.',
          doneClass: 'bg-orange-500',
        },
        {
          key: 'entrega',
          label: 'Entrega confirmada',
          done: p.reparto?.estado === 'entregado',
          time: p.reparto?.estado === 'entregado' ? 'ok' : null,
          detail: p.reparto?.estado === 'entregado'
            ? 'Pedido entregado correctamente.'
            : 'Pendiente de confirmación final.',
          doneClass: 'bg-emerald-600',
        },
      ];

      return steps.map((step, index) => ({
        ...step,
        last: index === steps.length - 1,
      }));
    },

    horaCorta(iso) {
      if (!iso) return null;
      return new Date(iso).toLocaleTimeString('es-ES', {
        hour: '2-digit',
        minute: '2-digit',
      });
    },

    minutosDesde(iso) {
      if (!iso) return null;
      const mins = Math.round((this.now - new Date(iso)) / 60000);
      if (mins < 60) return mins + ' min';
      const h = Math.floor(mins / 60);
      const m = mins % 60;
      return m > 0 ? `${h}h ${m}min` : `${h}h`;
    },

    minutosDesdeCreacion(p) {
      if (!p?.fecha_creacion) return 0;
      return Math.round((this.now - new Date(p.fecha_creacion)) / 60000);
    },

    mostrarToast(msg, error = false) {
      this.toast = { visible: true, msg, error };
      setTimeout(() => {
        this.toast.visible = false;
      }, 3000);
    },

    formatMinutos(min) {
      if (min === null || min === undefined) return '—';
      if (min < 60) return min + 'min';
      return Math.floor(min / 60) + 'h ' + (min % 60) + 'min';
    },

    formatTimestamp(ts) {
      if (!ts) return '';
      const d = new Date(ts);
      return d.toLocaleTimeString('es-ES', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      });
    },

    estadoLabel(estado) {
      const labels = {
        Pendiente: 'Pendiente',
        enlace: 'Enlace',
        enlace2: 'Confirmación',
        'confirmando-pago': 'Pago...',
        pagado: 'Pago OK',
        contra_reembolso: 'Efectivo',
        en_preparacion: 'Cocina',
        preparado: 'Listo',
        en_reparto: 'En ruta',
        entregado: 'Entregado',
        cancelado: 'Cancelado',
        reembolsado: 'Reembolsado',
      };
      return labels[estado] || estado;
    },

    nivelEmoji(nivel) {
      return { error: '🔴', warning: '🟡', info: '🔵' }[nivel] || '⚪';
    },

    badgePedidoDinamLabel(p) {
      if (p.estado === 'preparado') {
        return p.reparto?.repartidor_nombre ? 'Listo para salir' : 'Sin repartidor';
      }
      if (p.estado === 'en_preparacion' && (!p.picking || !p.picking.picker_nombre)) {
        return 'Sin cocinero';
      }
      return this.estadoLabel(p.estado);
    },

    badgePedidoDinamClass(p) {
      if (p.estado === 'preparado') {
        return p.reparto?.repartidor_nombre
          ? 'bg-emerald-500 text-white'
          : 'bg-purple-500 text-white';
      }
      if (p.estado === 'en_preparacion' && (!p.picking || !p.picking.picker_nombre)) {
        return 'bg-purple-500 text-white';
      }
      return this.badgePedidoClass(p.estado);
    },

    badgePedidoClass(estado) {
      const m = {
        pagado: 'bg-amber-400 text-amber-900',
        contra_reembolso: 'bg-amber-400 text-amber-900',
        en_preparacion: 'bg-blue-500 text-white',
        preparado: 'bg-emerald-500 text-white',
        en_reparto: 'bg-orange-500 text-white',
        entregado: 'bg-slate-200 text-slate-500',
        cancelado: 'bg-red-600 text-white',
        reembolsado: 'bg-red-200 text-red-700',
        'confirmando-pago': 'bg-yellow-100 text-yellow-800',
        enlace: 'bg-gray-100 text-gray-600',
        enlace2: 'bg-gray-100 text-gray-600',
        Pendiente: 'bg-gray-100 text-gray-600',
      };
      return m[estado] || 'bg-gray-100 text-gray-600';
    },

    badgePickingClass(estado) {
      const m = {
        pendiente: 'bg-gray-100 text-gray-600',
        en_proceso: 'bg-blue-100 text-blue-800',
        completado: 'bg-green-100 text-green-800',
        con_incidencias: 'bg-red-100 text-red-700',
        cancelado: 'bg-red-100 text-red-700',
      };
      return m[estado] || 'bg-gray-100 text-gray-600';
    },

    badgeRepartoClass(estado) {
      const m = {
        pendiente: 'bg-gray-100 text-gray-600',
        asignado: 'bg-yellow-100 text-yellow-800',
        en_camino: 'bg-orange-100 text-orange-800',
        entregado: 'bg-green-100 text-green-800',
        no_entregado: 'bg-red-100 text-red-700',
        cancelado: 'bg-red-100 text-red-700',
      };
      return m[estado] || 'bg-gray-100 text-gray-600';
    },
  };
}
