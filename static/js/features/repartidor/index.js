let mapaRep = null;
let mapaRepMarkers = [];
let marcadorTiendaRep = null;
let mapaCola = null;
let mapaColaMarkers = [];
let marcadorTiendaCola = null;

function repartidor(repartidorId) {
  if (!repartidorId) {
    const saved = localStorage.getItem('panchi_repartidor_id');
    if (saved) repartidorId = parseInt(saved, 10);
  }
  return {
    repartidorId,
    pedidos: [],
    vista: 'lista',
    actual: null,
    navStack: [],
    cargando: false,
    tabActiva: 'mis-entregas',
    cola: [],
    colaTotal: 0,
    cogiendo: null,
    procesando: false,
    historialAbierto: false,
    mostrarNoEntregar: false,
    now: new Date(),
    motivoSeleccionado: '',
    motivoLibre: '',
    motivosRapidos: [
      'Nadie en casa',
      'Dirección incorrecta',
      'Cliente no contesta',
      'Acceso imposible',
    ],
    toast: { visible: false, msg: '', error: false },

    holdProgress: 0,
    holdActive: false,
    _holdTimer: null,

    pedidosConocidos: new Set(),

    conexionOk: true,
    lastFetchTime: null,

    mapaVisible: false,
    mapaColaVisible: false,
    pedidoDestacado: null,

    pagoConfirmado: false,
    mostrarCobro: false,
    metodoCobro: '',
    importeDado: '',
    importeEfectivoMixto: '',
    importeTarjetaMixto: '',
    _resumeCobro: '',

    get puedeVolver() {
      return this.navStack.length > 0;
    },

    get labelAnterior() {
      const prev = this.navStack[this.navStack.length - 1];
      if (!prev) return '';
      if (prev.vista === 'lista') return prev.tabActiva === 'cola' ? 'Cola' : 'Mis entregas';
      if (prev.vista === 'pedido') return 'Pedido';
      return 'Atrás';
    },

    get pedidosActivos() {
      return this.pedidos
        .filter(p => ['asignado', 'en_camino'].includes(p.estado_reparto))
        .sort((a, b) =>
          this.calculateRemainingMinutes(a.fecha_creacion) -
          this.calculateRemainingMinutes(b.fecha_creacion)
        );
    },

    get pedidosEnReparto() {
      return this.pedidos
        .filter(p => p.estado_reparto === 'en_camino')
        .sort((a, b) =>
          this.calculateRemainingMinutes(a.fecha_creacion) -
          this.calculateRemainingMinutes(b.fecha_creacion)
        );
    },

    get pedidosEnTiendaConocidos() {
      return this.pedidos
        .filter(p => p.estado_reparto === 'asignado' && this.pedidosConocidos.has(p.reparto_id))
        .sort((a, b) =>
          this.calculateRemainingMinutes(a.fecha_creacion) -
          this.calculateRemainingMinutes(b.fecha_creacion)
        );
    },

    get pedidosNuevosEnCalle() {
      if (!this.pedidos.some(p => p.estado_reparto === 'en_camino')) return [];
      return this.pedidos
        .filter(p => p.estado_reparto === 'asignado' && !this.pedidosConocidos.has(p.reparto_id))
        .sort((a, b) =>
          this.calculateRemainingMinutes(a.fecha_creacion) -
          this.calculateRemainingMinutes(b.fecha_creacion)
        );
    },

    get pedidosHistorial() {
      return this.pedidos.filter(p => ['entregado', 'no_entregado'].includes(p.estado_reparto));
    },

    get motivoFinal() {
      return this.motivoLibre.trim() || this.motivoSeleccionado;
    },

    get needsCobro() {
      return this.actual?.pago?.estado !== 'pagado_online';
    },

    get canDeliver() {
      return !this.needsCobro || this.pagoConfirmado;
    },

    get resumeCobro() {
      return this._resumeCobro;
    },

    get cambioEfectivo() {
      const dado = parseFloat(this.importeDado);
      const total = this.actual?.pago?.importe || 0;
      if (isNaN(dado) || dado <= 0) return null;
      return parseFloat((dado - total).toFixed(2));
    },

    get totalMixtoCalculado() {
      const ef = parseFloat(this.importeEfectivoMixto) || 0;
      const tj = parseFloat(this.importeTarjetaMixto) || 0;
      return parseFloat((ef + tj).toFixed(2));
    },

    get mixtoValido() {
      const total = this.actual?.pago?.importe || 0;
      return this.totalMixtoCalculado > 0
        && Math.abs(this.totalMixtoCalculado - total) < 0.005;
    },

    get quickAmounts() {
      const total = this.actual?.pago?.importe || 0;
      const amounts = new Set();
      [5, 10, 20, 50, 100].forEach(bill => {
        let v = bill;
        while (v < total) v += bill;
        amounts.add(v);
      });
      return [...amounts].sort((a, b) => a - b).slice(0, 5);
    },

    async init() {
      if (!this.repartidorId) return;
      localStorage.setItem('panchi_repartidor_id', this.repartidorId);
      await Promise.all([this.recargar(), this.cargarCola()]);

      // Detectar modo demo para polling más rápido
      const esDemoMode = window.location.href.includes('/demo') || window.location.href.includes('/repartidor/demo');
      const pollingInterval = esDemoMode ? 2000 : 60000;

      setInterval(() => {
        if (this.vista === 'lista') {
          this.recargar(true, true);
          this.cargarCola();
        }
      }, pollingInterval);

      setInterval(() => {
        this.now = new Date();
      }, 30000);
    },

    async recargar(skipCache = false, silencioso = false) {
      if (!this.repartidorId) return;
      if (!silencioso) this.cargando = true;
      const _cacheKey = `panchi_rep_pedidos_${this.repartidorId}`;
      if (!skipCache) {
        try {
          const _cached = JSON.parse(localStorage.getItem(_cacheKey) || 'null');
          if (_cached) {
            this.pedidos = _cached;
            if (!_cached.some(p => p.estado_reparto === 'en_camino')) {
              _cached
                .filter(p => p.estado_reparto === 'asignado')
                .forEach(p => this.pedidosConocidos.add(p.reparto_id));
            }
            if (!silencioso) this.cargando = false;
          }
        } catch (_) {}
      }
      try {
        const r = await fetch(`/repartidor/mis-pedidos?repartidor_id=${this.repartidorId}`);
        if (r.ok) {
          this.pedidos = await r.json();
          localStorage.setItem(_cacheKey, JSON.stringify(this.pedidos));
          this.conexionOk = true;
          this.lastFetchTime = new Date();
          if (this.mapaVisible) this.actualizarMapaRepartidor();
          if (!this.pedidos.some(p => p.estado_reparto === 'en_camino')) {
            this.pedidos
              .filter(p => p.estado_reparto === 'asignado')
              .forEach(p => this.pedidosConocidos.add(p.reparto_id));
          }
          if (this.actual) {
            const updated = this.pedidos.find(p => p.reparto_id === this.actual.reparto_id);
            if (updated) this.actual = updated;
          }
        } else {
          this.conexionOk = false;
        }
      } catch {
        this.conexionOk = false;
      } finally {
        if (!silencioso) this.cargando = false;
      }
    },

    async cargarCola() {
      const _cacheKey = `panchi_rep_cola_${this.repartidorId}`;
      try {
        const _cached = JSON.parse(localStorage.getItem(_cacheKey) || 'null');
        if (_cached) {
          this.cola = _cached.cola || [];
          this.colaTotal = _cached.total || 0;
        }
      } catch (_) {}
      try {
        const r = await fetch('/repartidor/cola');
        if (r.ok) {
          const data = await r.json();
          this.cola = data.cola || [];
          this.colaTotal = data.total || 0;
          localStorage.setItem(_cacheKey, JSON.stringify(data));
          if (this.mapaColaVisible) this.actualizarMapaCola();
        } else {
          this.conexionOk = false;
        }
      } catch (_) {
        this.conexionOk = false;
      }
    },

    async cogerReparto(pedidoId) {
      if (this.cogiendo !== null) return;
      this.cogiendo = pedidoId;
      try {
        const r = await fetch(`/repartidor/cola/coger/${pedidoId}`, { method: 'POST' });
        if (r.ok) {
          this.cola = this.cola.map(p =>
            p.pedido_id === pedidoId ? { ...p, ya_cogido: true } : p
          );
          this.colaTotal = Math.max(0, this.colaTotal - 1);
          this.mostrarToast('Reparto cogido ✓');
          this.cargarCola();
          this.recargar(true, true);
        } else {
          const data = await r.json().catch(() => ({}));
          if (data.error === 'ya_cogido') {
            this.cola = this.cola.map(p =>
              p.pedido_id === pedidoId ? { ...p, ya_cogido: true } : p
            );
          } else {
            this.conexionOk = false;
          }
        }
      } catch (_) {
        this.conexionOk = false;
      }
      this.cogiendo = null;
    },

    abrirPedido(p) {
      this.navStack.push({ vista: this.vista, actual: this.actual, tabActiva: this.tabActiva });
      this.actual = p;
      this.vista = 'pedido';
      this.pagoConfirmado = false;
      this._resumeCobro = '';
      this.$nextTick(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    },

    abrirResumen(p) {
      this.navStack.push({ vista: this.vista, actual: this.actual, tabActiva: this.tabActiva });
      this.actual = p;
      this.vista = 'resumen';
      window.scrollTo({ top: 0, behavior: 'smooth' });
    },

    goBack() {
      const prev = this.navStack.pop();
      if (!prev) return;
      this.actual = prev.actual;
      this.vista = prev.vista;
      this.tabActiva = prev.tabActiva;
      this.$nextTick(() => window.scrollTo({ top: 0, behavior: 'instant' }));
    },

    volverALista() {
      this.navStack = [];
      this.vista = 'lista';
      this.actual = null;
      this.motivoSeleccionado = '';
      this.motivoLibre = '';
      this.mostrarNoEntregar = false;
      this.pagoConfirmado = false;
      this._resumeCobro = '';
      this.importeDado = '';
      this.importeEfectivoMixto = '';
      this.importeTarjetaMixto = '';
      this.metodoCobro = '';
      this._stopHold();
      this.recargar(true, true);
    },

    cerrarNoEntregar() {
      this.mostrarNoEntregar = false;
      this.motivoSeleccionado = '';
      this.motivoLibre = '';
    },

    cerrarCobro() {
      this.mostrarCobro = false;
    },

    resetCobro() {
      this.pagoConfirmado = false;
      this._resumeCobro = '';
      this.importeDado = '';
      this.importeEfectivoMixto = '';
      this.importeTarjetaMixto = '';
      this.metodoCobro = '';
      this.mostrarCobro = true;
    },

    confirmarCobro() {
      const importe = this.actual?.pago?.importe || 0;
      if (this.metodoCobro === 'efectivo') {
        const cambio = this.cambioEfectivo;
        if (cambio === null || cambio < 0) return;
        this._resumeCobro = cambio === 0
          ? `Efectivo ${importe.toFixed(2)} € (sin cambio)`
          : `Efectivo · cambio ${cambio.toFixed(2)} €`;
      } else if (this.metodoCobro === 'tarjeta') {
        this._resumeCobro = `Tarjeta ${importe.toFixed(2)} €`;
      } else if (this.metodoCobro === 'mixto') {
        if (!this.mixtoValido) return;
        const ef = parseFloat(this.importeEfectivoMixto).toFixed(2);
        const tj = parseFloat(this.importeTarjetaMixto).toFixed(2);
        this._resumeCobro = `Mixto · ${ef} € efectivo + ${tj} € tarjeta`;
      } else {
        return;
      }
      this.pagoConfirmado = true;
      this.mostrarCobro = false;
      this.mostrarToast('Cobro registrado ✓');
      this._persistirCobro();
    },

    async _persistirCobro() {
      try {
        await fetch(`/repartidor/reparto/${this.actual.reparto_id}/registrar-cobro`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            metodo_cobro: this.metodoCobro,
            importe_cobrado: this.actual?.pago?.importe || 0,
            cambio_devuelto: this.metodoCobro === 'efectivo' ? this.cambioEfectivo : null,
            importe_efectivo: this.metodoCobro === 'mixto' ? parseFloat(this.importeEfectivoMixto) : null,
            importe_tarjeta: this.metodoCobro === 'mixto' ? parseFloat(this.importeTarjetaMixto) : null,
          }),
        });
      } catch (_) {}
    },

    startHold() {
      if (this.procesando || !this.canDeliver) return;
      this.holdActive = true;
      this.holdProgress = 0;
      const startTime = Date.now();
      this._holdTimer = setInterval(() => {
        this.holdProgress = Math.min(100, ((Date.now() - startTime) / 1500) * 100);
        if (this.holdProgress >= 100) {
          this._stopHold();
          this.marcarEntregado();
        }
      }, 30);
    },

    _stopHold() {
      if (this._holdTimer) {
        clearInterval(this._holdTimer);
        this._holdTimer = null;
      }
      this.holdActive = false;
      this.holdProgress = 0;
    },

    resaltarTarjeta(reparto_id) {
      this.pedidoDestacado = reparto_id;
      this.$nextTick(() => {
        const el = document.getElementById('card-' + reparto_id);
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
      setTimeout(() => { this.pedidoDestacado = null; }, 2000);
    },

    toggleMapa() {
      this.mapaVisible = !this.mapaVisible;
      if (this.mapaVisible) {
        setTimeout(() => this.iniciarMapaRepartidor(), 50);
      }
    },

    iniciarMapaRepartidor() {
      const el = document.getElementById('mapa-rep');
      if (!el) return;
      if (!mapaRep) {
        mapaRep = L.map('mapa-rep', {
          tap: false,
          dragging: false,
          touchZoom: false,
          scrollWheelZoom: false,
          doubleClickZoom: false,
          zoomControl: false,
        }).setView([40.010049, -3.012543], 14);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
          attribution: '© <a href="https://www.openstreetmap.org/copyright">OSM</a> © <a href="https://carto.com/">CARTO</a>',
          maxZoom: 19,
        }).addTo(mapaRep);
      }
      mapaRep.invalidateSize();
      this.actualizarMapaRepartidor();
    },

    actualizarMapaRepartidor() {
      if (!mapaRep) return;

      if (!marcadorTiendaRep) {
        const iconTienda = L.divIcon({
          className: '',
          html: `
                  <div style="
                    width:8px;
                    height:8px;
                    background:#000;
                    border-radius:50%;
                    box-shadow:0 0 6px rgba(0,0,0,0.6);
                  "></div>
                `,
          iconSize: [32, 32],
          iconAnchor: [16, 16],
        });
        marcadorTiendaRep = L.marker([40.008778, -3.010905], { icon: iconTienda })
          .bindPopup('<br>Tienda')
          .addTo(mapaRep);
      }

      mapaRepMarkers.forEach(m => m.remove());
      mapaRepMarkers = [];

      const conCoordenadas = this.pedidosActivos.filter(p => p.lat != null && p.lng != null);
      conCoordenadas.forEach(p => {
        const mins = this.calculateRemainingMinutes(p.fecha_creacion);
        const color = mins > 8 ? '#16a34a' : mins >= 3 ? '#ca8a04' : mins >= 0 ? '#ea580c' : '#dc2626';
        const icon = L.divIcon({
          className: '',
          html: `<div style="background:${color};color:#fff;border:2px solid #fff;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 4px rgba(0,0,0,.4);font-size:10px;font-weight:900;">${String(p.pedido_id).slice(-3)}</div>`,
          iconSize: [26, 26],
          iconAnchor: [13, 13],
        });
        const marker = L.marker([p.lat, p.lng], { icon }).addTo(mapaRep);
        marker.on('click', () => this.resaltarTarjeta(p.reparto_id));
        mapaRepMarkers.push(marker);
      });
    },

    toggleMapaCola() {
      this.mapaColaVisible = !this.mapaColaVisible;
      if (this.mapaColaVisible) {
        this.$nextTick(() => setTimeout(() => this.iniciarMapaCola(), 50));
      }
    },

    iniciarMapaCola() {
      const el = document.getElementById('mapa-cola');
      if (!el) return;
      if (!mapaCola) {
        mapaCola = L.map('mapa-cola', {
          tap: false,
          dragging: false,
          touchZoom: false,
          scrollWheelZoom: false,
          doubleClickZoom: false,
          zoomControl: false,
        }).setView([40.010049, -3.012543], 14);
        L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
          attribution: '© <a href="https://www.openstreetmap.org/copyright">OSM</a> © <a href="https://carto.com/">CARTO</a>',
          maxZoom: 19,
        }).addTo(mapaCola);
      }
      mapaCola.invalidateSize();
      this.actualizarMapaCola();
    },

    actualizarMapaCola() {
      if (!mapaCola) return;

      if (!marcadorTiendaCola) {
        const iconTienda = L.divIcon({
          className: '',
          html: `
                  <div style="
                    width:8px;
                    height:8px;
                    background:#000;
                    border-radius:50%;
                    box-shadow:0 0 6px rgba(0,0,0,0.6);
                  "></div>
                `,
          iconSize: [32, 32],
          iconAnchor: [16, 16],
        });
        marcadorTiendaCola = L.marker([40.008778, -3.010905], { icon: iconTienda })
          .bindPopup('<br>Tienda')
          .addTo(mapaCola);
      }

      mapaColaMarkers.forEach(m => m.remove());
      mapaColaMarkers = [];
      const conCoordenadas = this.cola.filter(p => !p.ya_cogido && p.lat != null && p.lng != null);
      conCoordenadas.forEach(p => {
        const icon = L.divIcon({
          className: '',
          html: `<div style="background:#ea580c;color:#fff;border:2px solid #fff;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;box-shadow:0 1px 4px rgba(0,0,0,.4);font-size:10px;font-weight:900;">${String(p.pedido_id).slice(-3)}</div>`,
          iconSize: [26, 26],
          iconAnchor: [13, 13],
        });
        const marker = L.marker([p.lat, p.lng], { icon }).addTo(mapaCola);
        mapaColaMarkers.push(marker);
      });
    },

    mapsUrl(direccion) {
      return 'https://www.google.com/maps/dir/?api=1&destination='
        + encodeURIComponent((direccion || '') + ', Tarancón, España');
    },

    async salirYNavegar() {
      const ok = await this.marcarSalida();
      if (ok) this.volverALista();
    },

    async marcarSalida() {
      this.procesando = true;
      try {
        const r = await fetch(`/repartidor/reparto/${this.actual.reparto_id}/salida`, { method: 'POST' });
        const data = await r.json();
        if (r.ok) {
          this.actual.estado_reparto = 'en_camino';
          const repartoId = this.actual.reparto_id;
          const p = this.pedidos.find(p => p.reparto_id === repartoId);
          if (p) p.estado_reparto = 'en_camino';
          this.mostrarToast('¡En camino! Buena entrega 🛵');
          return true;
        } else {
          this.mostrarToast(data.error, true);
          return false;
        }
      } finally {
        this.procesando = false;
      }
    },

    async marcarEntregado() {
      this.procesando = true;
      try {
        const r = await fetch(`/repartidor/reparto/${this.actual.reparto_id}/entregar`, { method: 'POST' });
        const data = await r.json();
        if (r.ok) {
          this.mostrarToast('Pedido entregado ✓');
          const repartoId = this.actual.reparto_id;
          this.pedidos = this.pedidos.filter(p => p.reparto_id !== repartoId);
          this.volverALista();
        } else {
          this.mostrarToast(data.error, true);
        }
      } finally {
        this.procesando = false;
      }
    },

    async confirmarNoEntregado() {
      if (!this.motivoFinal) return;
      this.procesando = true;
      try {
        const r = await fetch(`/repartidor/reparto/${this.actual.reparto_id}/no-entregar`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ motivo: this.motivoFinal }),
        });
        const data = await r.json();
        if (r.ok) {
          this.mostrarToast('Registrado. El supervisor lo verá.');
          this.mostrarNoEntregar = false;
          await this.recargar(true, true);
          const updated = this.pedidos.find(p => p.reparto_id === this.actual?.reparto_id);
          if (updated) this.actual = updated;
          this.motivoSeleccionado = '';
          this.motivoLibre = '';
          this.navStack.push({ vista: this.vista, actual: this.actual, tabActiva: this.tabActiva });
          this.vista = 'resumen';
        } else {
          this.mostrarToast(data.error, true);
        }
      } finally {
        this.procesando = false;
      }
    },

    async corregirAEntregado() {
      this.procesando = true;
      try {
        const r = await fetch(`/repartidor/reparto/${this.actual.reparto_id}/entregar`, { method: 'POST' });
        const data = await r.json();
        if (r.ok) {
          this.mostrarToast('Corregido como entregado ✓');
          await this.recargar(true, true);
          const updated = this.pedidos.find(p => p.reparto_id === this.actual?.reparto_id);
          if (updated) this.actual = updated;
        } else {
          this.mostrarToast(data.error, true);
        }
      } finally {
        this.procesando = false;
      }
    },

    minutesTaken(p) {
      if (!p?.fecha_creacion || !p?.hora_entrega_real) return null;
      return Math.round((new Date(p.hora_entrega_real) - new Date(p.fecha_creacion)) / 60000);
    },

    wasOnTime(p) {
      const min = this.minutesTaken(p);
      if (min === null) return null;
      return min <= 20;
    },

    calculateRemainingMinutes(fechaCreacion) {
      if (!fechaCreacion) return 99;
      const promised = new Date(new Date(fechaCreacion).getTime() + 20 * 60 * 1000);
      return Math.round((promised - this.now) / 60000);
    },

    priorityColor(minutes) {
      if (minutes > 8) return 'bg-green-900 text-green-400';
      if (minutes >= 3) return 'bg-yellow-100 text-yellow-800';
      if (minutes >= 0) return 'bg-orange-900 text-orange-300';
      return 'bg-red-900 text-red-300';
    },

    priorityStroke(minutes) {
      if (minutes > 8) return '#4ade80';
      if (minutes >= 3) return '#fbbf24';
      if (minutes >= 0) return '#f97316';
      return '#f87171';
    },

    priorityTextColor(minutes) {
      if (minutes > 8) return 'text-green-400';
      if (minutes >= 3) return 'text-amber-400';
      if (minutes >= 0) return 'text-orange-400';
      return 'text-red-400';
    },

    formatRemaining(minutes) {
      if (minutes > 0) return minutes + ' min';
      if (minutes === 0) return '0 min';
      return '+' + Math.abs(minutes);
    },

    formatPromisedTime(fechaCreacion) {
      if (!fechaCreacion) return '--:--';
      const t = new Date(new Date(fechaCreacion).getTime() + 20 * 60 * 1000);
      return t.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    },

    formatHora(ts) {
      if (!ts) return '—';
      return new Date(ts).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    },

    formatFechaHora(ts) {
      if (!ts) return '—';
      const d = new Date(ts);
      const fecha = d.toLocaleDateString('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric' });
      const hora = d.toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
      return fecha + ' a las ' + hora;
    },

    mostrarToast(msg, error = false) {
      // toasts desactivados
    },

    badgePagoClass(estado) {
      return {
        pagado_online: 'bg-green-900 text-green-400',
        cobrar_efectivo: 'bg-yellow-900 text-yellow-300',
        cobrar_tarjeta: 'bg-blue-900 text-blue-300',
      }[estado] || 'bg-gray-700 text-gray-300';
    },

    badgePagoFondoClass(estado) {
      return {
        pagado_online: 'bg-green-950 border border-green-800 text-green-300',
        cobrar_efectivo: 'bg-yellow-950 border border-yellow-700 text-yellow-300',
        cobrar_tarjeta: 'bg-blue-950 border border-blue-800 text-blue-300',
      }[estado] || 'bg-gray-800 border border-gray-600 text-gray-200';
    },
  };
}

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/repartidor/sw.js', { scope: '/repartidor' })
      .catch(err => console.warn('SW registration failed:', err));
  });
}
