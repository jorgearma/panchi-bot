function picker(pickerId) {
  if (!pickerId) {
    const saved = localStorage.getItem('panchi_picker_id');
    if (saved) pickerId = parseInt(saved, 10);
  }

  return {
    pickerId: pickerId,
    pedidos: [],
    vistaActual: 'lista',
    ticketActual: null,
    navStack: [],
    cargando: false,
    finalizando: false,
    isOnline: true,
    offlineQueue: [],
    toast: { visible: false, msg: '', error: false },
    _toastTimer: null,
    _searchTimer: null,
    confirmarFinalizar: false,

    cola: [],
    colaTotal: 0,
    cogiendo: null,
    tabActiva: 'mis-pedidos',

    modalCantidad: {
      visible: false,
      item: null,
      cantidad: 1,
    },
    modalSinStock: {
      visible: false,
      item: null,
      motivo: 'sin_stock',
      sustituto: null,
      query: '',
      resultados: [],
      buscando: false,
    },

    get puedeVolver() {
      return this.navStack.length > 0;
    },

    get labelAnterior() {
      const prev = this.navStack[this.navStack.length - 1];
      if (!prev) return '';
      if (prev.vistaActual === 'lista') return prev.tabActiva === 'cola' ? 'Cola' : 'Mis pedidos';
      return 'Atrás';
    },

    get itemsOrdenados() {
      if (!this.ticketActual) return [];
      return [...this.ticketActual.items].sort((a, b) => {
        const ap = a.estado === 'pendiente' ? 0 : 1;
        const bp = b.estado === 'pendiente' ? 0 : 1;
        if (ap !== bp) return ap - bp;
        return (a.ubicacion || 'ZZZZ').localeCompare(b.ubicacion || 'ZZZZ');
      });
    },

    get primerPendiente() {
      if (!this.ticketActual) return null;
      return this.itemsOrdenados.find(i => i.estado === 'pendiente') ?? null;
    },

    get itemsCompletados() {
      if (!this.ticketActual) return 0;
      return this.ticketActual.items.filter(i => i.estado !== 'pendiente').length;
    },

    get progresoPorc() {
      if (!this.ticketActual || this.ticketActual.items_total === 0) return 0;
      return Math.round(this.itemsCompletados / this.ticketActual.items_total * 100);
    },

    async init() {
      if (!this.pickerId) return;
      localStorage.setItem('panchi_picker_id', this.pickerId);
      this.isOnline = navigator.onLine;
      window.addEventListener('online', () => {
        this.isOnline = true;
        this._flushQueue();
      });
      window.addEventListener('offline', () => {
        this.isOnline = false;
      });
      await Promise.all([this.recargar(), this.cargarCola()]);

      // Detectar modo demo para polling más rápido
      const esDemoMode = window.location.href.includes('/demo') || window.location.href.includes('/picker/demo');
      const pollingInterval = esDemoMode ? 5000 : 60000;

      setInterval(() => {
        if (this.vistaActual === 'lista') {
          this.recargar(true);
          this.cargarCola();
        }
      }, pollingInterval);
    },

    async recargar(silencioso = false) {
      if (!this.pickerId) return;
      if (!silencioso) this.cargando = true;
      const _cacheKey = `panchi_picker_pedidos_${this.pickerId}`;
      try {
        const _cached = JSON.parse(localStorage.getItem(_cacheKey) || 'null');
        if (_cached) {
          _cached.forEach(p => p.items.forEach(item => { item._guardando = false; }));
          this.pedidos = _cached;
          this.cargando = false;
        }
      } catch (_) {}
      try {
        const r = await fetch(`/picker/mis-pedidos?picker_id=${this.pickerId}`);
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        const data = await r.json();
        data.forEach(p => p.items.forEach(item => { item._guardando = false; }));
        this.pedidos = data;
        localStorage.setItem(_cacheKey, JSON.stringify(data));
        if (this.ticketActual) {
          const actualizado = data.find(p => p.picking_id === this.ticketActual.picking_id);
          if (actualizado && !this.ticketActual.items.some(i => i._guardando)) {
            actualizado.items.forEach(item => { item._guardando = false; });
            this.ticketActual = actualizado;
          }
        }
      } catch (_e) {
        this.mostrarToast('Error al cargar pedidos', true);
      } finally {
        this.cargando = false;
      }
    },

    async cargarCola() {
      const _cacheKey = `panchi_picker_cola_${this.pickerId}`;
      try {
        const _cached = JSON.parse(localStorage.getItem(_cacheKey) || 'null');
        if (_cached) {
          this.cola = _cached.cola || [];
          this.colaTotal = _cached.total || 0;
        }
      } catch (_) {}
      try {
        const r = await fetch('/picker/cola');
        if (r.ok) {
          const d = await r.json();
          this.cola = d.cola || [];
          this.colaTotal = d.total || 0;
          localStorage.setItem(_cacheKey, JSON.stringify(d));
        }
      } catch (_) {
        this.mostrarToast('Error al cargar la cola', true);
      }
    },

    async cogerPedido(pickingId) {
      if (this.cogiendo) return;
      this.cogiendo = pickingId;
      try {
        const r = await fetch(`/picker/cola/coger/${pickingId}`, { method: 'POST' });
        if (r.ok) {
          this.cola = this.cola.filter(p => p.picking_id !== pickingId);
          this.colaTotal = Math.max(0, this.colaTotal - 1);
          this.cargarCola();
          this.recargar(true);
        } else if (r.status === 409) {
          this.cola = this.cola.map(p =>
            p.picking_id === pickingId ? { ...p, ya_cogido: true } : p
          );
        }
      } catch (_) {
        this.mostrarToast('Error al coger el pedido', true);
      } finally {
        this.cogiendo = null;
      }
    },

    abrirTicket(pedido) {
      this.navStack.push({ vistaActual: this.vistaActual, tabActiva: this.tabActiva, ticketActual: this.ticketActual });
      this.ticketActual = pedido;
      this.vistaActual = 'ticket';
      window.scrollTo({ top: 0, behavior: 'instant' });
    },

    goBack() {
      const prev = this.navStack.pop();
      if (!prev) return;
      this.ticketActual = prev.ticketActual;
      this.vistaActual = prev.vistaActual;
      this.tabActiva = prev.tabActiva;
      window.scrollTo({ top: 0, behavior: 'instant' });
    },

    volverALista() {
      this.navStack = [];
      this.vistaActual = 'lista';
      this.ticketActual = null;
      this.recargar();
    },

    async marcarItem(item, nuevoEstado, extra = {}) {
      if (item._guardando) return;

      const estadoAnterior = item.estado;
      item.estado = nuevoEstado;
      item._guardando = true;

      if (extra.cantidad_encontrada !== undefined) {
        item.cantidad_encontrada = extra.cantidad_encontrada;
      }

      this._recalcularPendientes();

      if (!this.isOnline) {
        this.offlineQueue.push({ item_id: item.item_id, estado: nuevoEstado, estadoAnterior, extra });
        item._guardando = false;
        this.mostrarToast('Sin conexión — se enviará al reconectar');
        return;
      }

      await this._enviarEstado(item, nuevoEstado, estadoAnterior, extra);
    },

    async _enviarEstado(item, nuevoEstado, estadoAnterior, extra = {}, intentos = 0) {
      try {
        const r = await fetch(`/picker/item/${item.item_id}/estado`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ estado: nuevoEstado, ...extra }),
        });

        if (!r.ok) {
          if (r.status >= 500 && intentos < 2) {
            await new Promise(res => setTimeout(res, 600 * (intentos + 1)));
            return this._enviarEstado(item, nuevoEstado, estadoAnterior, extra, intentos + 1);
          }
          item.estado = estadoAnterior;
          item.cantidad_encontrada = null;
          this._recalcularPendientes();
          const data = await r.json().catch(() => ({}));
          this.mostrarToast(data.error || 'Error al actualizar', true);
        }
      } catch (_e) {
        if (intentos < 2) {
          await new Promise(res => setTimeout(res, 600 * (intentos + 1)));
          return this._enviarEstado(item, nuevoEstado, estadoAnterior, extra, intentos + 1);
        }
        item.estado = estadoAnterior;
        item.cantidad_encontrada = null;
        this._recalcularPendientes();
        this.mostrarToast('Sin conexión — intenta de nuevo', true);
      } finally {
        item._guardando = false;
      }
    },

    async _flushQueue() {
      if (!this.offlineQueue.length) return;
      const cola = [...this.offlineQueue];
      this.offlineQueue = [];

      for (const job of cola) {
        const item = this.ticketActual?.items.find(i => i.item_id === job.item_id);
        if (!item) continue;
        item.estado = job.estado;
        if (job.extra?.cantidad_encontrada !== undefined) {
          item.cantidad_encontrada = job.extra.cantidad_encontrada;
        }
        this._recalcularPendientes();
        await this._enviarEstado(item, job.estado, job.estadoAnterior, job.extra || {});
      }

      if (cola.length > 0) {
        const n = cola.length;
        this.mostrarToast(`${n} cambio${n > 1 ? 's' : ''} sincronizado${n > 1 ? 's' : ''} ✓`);
      }
    },

    _recalcularPendientes() {
      if (!this.ticketActual) return;
      const total = this.ticketActual.items_total || this.ticketActual.items.length;
      const pendientes = this.ticketActual.items.filter(i => i.estado === 'pendiente').length;
      const listos = total - pendientes;
      this.ticketActual.items_pendientes = pendientes;
      this.ticketActual.items_listos = listos;
      this.ticketActual.picking_completo = pendientes === 0 && total > 0;
      this.ticketActual.listo_para_finalizar = pendientes === 0;
      const enLista = this.pedidos.find(p => p.picking_id === this.ticketActual.picking_id);
      if (enLista) {
        enLista.items_pendientes = pendientes;
        enLista.items_listos = listos;
        enLista.picking_completo = pendientes === 0 && total > 0;
        enLista.listo_para_finalizar = pendientes === 0;
      }
    },

    abrirConfirmarFinalizar() {
      if (!this.ticketActual?.listo_para_finalizar || this.finalizando) return;
      this.confirmarFinalizar = true;
    },

    async finalizarPicking() {
      if (!this.ticketActual?.listo_para_finalizar || this.finalizando) return;
      this.finalizando = true;
      try {
        const r = await fetch(`/picker/picking/${this.ticketActual.picking_id}/finalizar`, { method: 'POST' });
        const data = await r.json().catch(() => ({}));
        if (r.ok) {
          this.recargar();
          setTimeout(() => this.volverALista(), 1500);
        } else {
          this.mostrarToast(data.error || 'Error al finalizar', true);
        }
      } catch (_e) {
        this.mostrarToast('Error inesperado al finalizar', true);
      } finally {
        this.finalizando = false;
      }
    },

    abrirModalCantidad(item) {
      this.modalCantidad = { visible: true, item, cantidad: item.cantidad };
    },

    cancelarModalCantidad() {
      this.modalCantidad = { visible: false, item: null, cantidad: 1 };
    },

    ajustarCantidad(delta) {
      const max = this.modalCantidad.item?.cantidad || 0;
      this.modalCantidad.cantidad = Math.max(0, Math.min(max, this.modalCantidad.cantidad + delta));
    },

    confirmarTodasCantidad() {
      this.modalCantidad.cantidad = this.modalCantidad.item?.cantidad || 0;
      this.confirmarCantidad();
    },

    confirmarCantidad() {
      const item = this.modalCantidad.item;
      const qty = this.modalCantidad.cantidad;
      if (!item) return;
      this.cancelarModalCantidad();
      if (qty === 0) {
        this.abrirModalSinStock(item);
        return;
      }
      this.marcarItem(item, 'encontrado', { cantidad_encontrada: qty });
    },

    abrirModalSinStock(item) {
      this.modalSinStock = {
        visible: true,
        item,
        motivo: 'sin_stock',
        sustituto: null,
        query: '',
        resultados: [],
        buscando: false,
      };
    },

    cancelarModalSinStock() {
      this.modalSinStock.visible = false;
    },

    confirmarSinStock() {
      const item = this.modalSinStock.item;
      if (!item) return;

      const extra = {
        cantidad_encontrada: 0,
        notas: this.modalSinStock.motivo,
      };

      let estado = 'sin_stock';
      if (this.modalSinStock.sustituto) {
        estado = 'sustituido';
        extra.producto_sustituto_id = this.modalSinStock.sustituto.id;
      }

      this.cancelarModalSinStock();
      this.marcarItem(item, estado, extra);
    },

    async buscarSustitutos(q) {
      clearTimeout(this._searchTimer);
      if (q.length < 2) {
        this.modalSinStock.resultados = [];
        return;
      }
      this._searchTimer = setTimeout(async () => {
        this.modalSinStock.buscando = true;
        try {
          const r = await fetch(`/picker/buscar-productos?q=${encodeURIComponent(q)}`);
          if (r.ok) {
            const data = await r.json();
            this.modalSinStock.resultados = data.filter(
              p => p.id !== this.modalSinStock.item?.producto_id
            );
          }
        } catch (_) {}
        finally {
          this.modalSinStock.buscando = false;
        }
      }, 300);
    },

    seleccionarSustituto(prod) {
      this.modalSinStock.sustituto = prod;
      this.modalSinStock.resultados = [];
      this.modalSinStock.query = '';
    },

    limpiarSustituto() {
      this.modalSinStock.sustituto = null;
    },

    mostrarToast(msg, error = false) {
      clearTimeout(this._toastTimer);
      this.toast = { visible: true, msg, error };
      this._toastTimer = setTimeout(() => { this.toast.visible = false; }, 3000);
    },

    formatMotivo(notas) {
      const labels = {
        sin_stock: 'Sin stock',
        dañado: 'Dañado',
        no_encuentro: 'No lo encontré',
      };
      return labels[notas] || notas;
    },

    formatHora(ts) {
      if (!ts) return '';
      return new Date(ts).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
    },

    formatMinutosDesde(ts) {
      if (!ts) return '';
      const fecha = new Date(ts);
      if (Number.isNaN(fecha.getTime())) return '';
      const diffMin = Math.max(0, Math.floor((Date.now() - fecha.getTime()) / 60000));
      if (diffMin < 1) return '< 1 min';
      if (diffMin === 1) return '1 min';
      if (diffMin < 60) return `${diffMin} min`;
      const horas = Math.floor(diffMin / 60);
      const mins = diffMin % 60;
      return mins === 0 ? `${horas} h` : `${horas} h ${mins} min`;
    },

    colorTiempoDesde(ts) {
      if (!ts) return 'text-slate-900';
      const fecha = new Date(ts);
      if (Number.isNaN(fecha.getTime())) return 'text-slate-900';
      const diffMin = Math.max(0, Math.floor((Date.now() - fecha.getTime()) / 60000));
      if (diffMin <= 5) return 'text-emerald-600';
      if (diffMin <= 8) return 'text-amber-500';
      return 'text-red-600';
    },
  };
}

if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => {
    navigator.serviceWorker
      .register('/picker/sw.js', { scope: '/picker' })
      .catch(err => console.warn('SW no registrado:', err));
  });
}
