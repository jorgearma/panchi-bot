;(function () {
  'use strict';

  // ─── Module state ────────────────────────────────────────────────
  var _item      = null;
  var _category  = null;
  var _editLineId = null;   // null = "add new" mode, string = "edit existing" mode
  var _qty       = 0;
  // { 'Tomate': true = incluido, false = quitado }
  var _ingState  = {};

  // ─── DOM refs (assigned in init) ─────────────────────────────────
  var overlay, sheet, imgWrap, imgEl,
      nameEl, priceEl, descEl,
      ingrSection, chipsEl,
      qtyEl, decBtn, incBtn,
      ctaBtn, ctaTextEl, ctaPriceEl,
      inCartNotice, inCartQtyEl;

  // ─── Tiny ID generator ───────────────────────────────────────────
  function genId() {
    return Math.random().toString(36).slice(2) + Date.now().toString(36);
  }

  // ─── Build and inject modal HTML ─────────────────────────────────
  function init() {
    var tpl =
      '<div class="pm-overlay" id="pm-overlay"></div>' +
      '<div class="pm-sheet" id="pm-sheet" role="dialog" aria-modal="true">' +
      '  <div class="pm-handle"></div>' +
      '  <div class="pm-image-wrap" id="pm-image-wrap">' +
      '    <img id="pm-img" src="" alt="">' +
      '    <div class="pm-image-placeholder" id="pm-img-ph">🍽️</div>' +
      '    <div class="pm-image-gradient"></div>' +
      '    <button class="pm-close" id="pm-close" type="button" aria-label="Cerrar">✕</button>' +
      '  </div>' +
      '  <div class="pm-body" id="pm-body">' +
      '    <p class="pm-name"  id="pm-name"></p>' +
      '    <p class="pm-price" id="pm-price"></p>' +
      '    <p class="pm-description" id="pm-desc"></p>' +
      '    <div class="pm-in-cart-notice" id="pm-in-cart-notice">' +
      '      🛒 Ya tienes <strong id="pm-in-cart-qty">0</strong> en el carrito — esto añade una línea nueva' +
      '    </div>' +
      '    <div class="pm-ingredients-section" id="pm-ing-section">' +
      '      <p class="pm-ingredients-title">Personaliza tu pedido — toca para quitar</p>' +
      '      <div class="pm-chips" id="pm-chips"></div>' +
      '    </div>' +
      '  </div>' +
      '  <div class="pm-footer">' +
      '    <div class="pm-stepper-row">' +
      '      <span class="pm-stepper-label">Cantidad</span>' +
      '      <div class="pm-stepper">' +
      '        <button class="pm-stepper-btn dec" id="pm-dec" type="button">−</button>' +
      '        <span  class="pm-stepper-qty"      id="pm-qty">1</span>' +
      '        <button class="pm-stepper-btn inc" id="pm-inc" type="button">+</button>' +
      '      </div>' +
      '    </div>' +
      '    <button class="pm-cta" id="pm-cta" type="button">' +
      '      <span id="pm-cta-text">Añadir al carrito</span>' +
      '      <span id="pm-cta-price"></span>' +
      '    </button>' +
      '  </div>' +
      '</div>';

    var frag = document.createRange().createContextualFragment(tpl);
    document.body.appendChild(frag);

    overlay       = document.getElementById('pm-overlay');
    sheet         = document.getElementById('pm-sheet');
    imgWrap       = document.getElementById('pm-image-wrap');
    imgEl         = document.getElementById('pm-img');
    nameEl        = document.getElementById('pm-name');
    priceEl       = document.getElementById('pm-price');
    descEl        = document.getElementById('pm-desc');
    ingrSection   = document.getElementById('pm-ing-section');
    chipsEl       = document.getElementById('pm-chips');
    qtyEl         = document.getElementById('pm-qty');
    decBtn        = document.getElementById('pm-dec');
    incBtn        = document.getElementById('pm-inc');
    ctaBtn        = document.getElementById('pm-cta');
    ctaTextEl     = document.getElementById('pm-cta-text');
    ctaPriceEl    = document.getElementById('pm-cta-price');
    inCartNotice  = document.getElementById('pm-in-cart-notice');
    inCartQtyEl   = document.getElementById('pm-in-cart-qty');

    overlay.addEventListener('click', close);
    document.getElementById('pm-close').addEventListener('click', close);
    decBtn.addEventListener('click', function () { setQty(_qty - 1); });
    incBtn.addEventListener('click', function () { setQty(_qty + 1); });
    ctaBtn.addEventListener('click', confirm);

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') close();
    });

    // Swipe down to close
    var swipeStartY = 0;
    sheet.addEventListener('touchstart', function (e) {
      swipeStartY = e.touches[0].clientY;
    }, { passive: true });
    sheet.addEventListener('touchend', function (e) {
      if (e.changedTouches[0].clientY - swipeStartY > 80) close();
    }, { passive: true });
  }

  // ─── Open (add-new mode) ─────────────────────────────────────────
  function open(item, category) {
    if (!window.menuData || !window.menuData[category] || !window.menuData[category][item]) return;

    _item      = item;
    _category  = category;
    _editLineId = null;
    _qty       = 1;

    _populate(window.menuData[category][item]);

    // Show "already in cart" notice if applicable
    var existingQty = _totalQtyForItem(item);
    if (existingQty > 0) {
      inCartQtyEl.textContent = existingQty + (existingQty === 1 ? ' ud' : ' uds');
      inCartNotice.classList.add('visible');
    } else {
      inCartNotice.classList.remove('visible');
    }

    _show();
  }

  // ─── Open (edit mode) ────────────────────────────────────────────
  function openEdit(lineId) {
    var line = (window.cartItems || []).find(function (ci) { return ci.lineId === lineId; });
    if (!line) return;
    if (!window.menuData || !window.menuData[line.category] || !window.menuData[line.category][line.itemName]) return;

    _item       = line.itemName;
    _category   = line.category;
    _editLineId = lineId;
    _qty        = line.qty;

    _populate(window.menuData[line.category][line.itemName], line.removed);
    inCartNotice.classList.remove('visible');
    _show();
  }

  // ─── Populate modal fields ────────────────────────────────────────
  function _populate(prod, existingRemoved) {
    var precio  = parseFloat(prod.Precio);
    var ingStr  = (prod.ingredientes || '').trim();
    var imagen  = prod.Imagen || '';

    // Image
    imgWrap.classList.remove('no-img');
    imgEl.src = '';
    if (imagen) {
      imgEl.onerror = function () { imgWrap.classList.add('no-img'); };
      imgEl.onload  = function () { imgWrap.classList.remove('no-img'); };
      imgEl.src     = imagen;
    } else {
      imgWrap.classList.add('no-img');
    }
    imgEl.alt = _item;

    nameEl.textContent  = _item;
    priceEl.textContent = precio.toFixed(2).replace('.', ',') + ' €';
    descEl.textContent  = ingStr;

    // Ingredient chips — show when 2+ comma-separated ingredients
    var ingList = ingStr
      ? ingStr.split(',').map(function (s) { return s.trim(); }).filter(Boolean)
      : [];

    if (ingList.length >= 2) {
      ingrSection.classList.add('visible');
      chipsEl.innerHTML = '';
      var savedRemoved = existingRemoved || [];
      _ingState = {};
      ingList.forEach(function (ing) {
        var included   = savedRemoved.indexOf(ing) === -1;
        _ingState[ing] = included;
        chipsEl.appendChild(_buildChip(ing, included));
      });
    } else {
      ingrSection.classList.remove('visible');
      _ingState = {};
    }

    renderControls(precio);
    document.getElementById('pm-body').scrollTop = 0;
  }

  // ─── Show / close ────────────────────────────────────────────────
  function _show() {
    overlay.classList.add('open');
    sheet.classList.add('open');
    document.body.style.overflow = 'hidden';
  }

  function close() {
    if (!sheet) return;
    overlay.classList.remove('open');
    sheet.classList.remove('open');
    document.body.style.overflow = '';
    _item = null;
  }

  // ─── Chip ────────────────────────────────────────────────────────
  function _buildChip(ing, included) {
    var chip = document.createElement('button');
    chip.type      = 'button';
    chip.className = 'pm-chip' + (included ? '' : ' removed');
    chip.dataset.ing = ing;
    _renderChip(chip, ing, included);
    chip.addEventListener('click', function () {
      _ingState[ing] = !_ingState[ing];
      chip.className = 'pm-chip' + (_ingState[ing] ? '' : ' removed');
      _renderChip(chip, ing, _ingState[ing]);
    });
    return chip;
  }

  function _renderChip(chip, ing, included) {
    chip.innerHTML =
      '<span class="pm-chip-icon">' + (included ? '✓' : '✕') + '</span>' +
      _esc(ing);
  }

  // ─── Stepper ─────────────────────────────────────────────────────
  function setQty(n) {
    _qty = Math.max(0, n);
    var precio = parseFloat(window.menuData[_category][_item].Precio);
    renderControls(precio);
  }

  function renderControls(precio) {
    qtyEl.textContent = _qty;
    decBtn.disabled   = _qty <= 0;

    var total = precio * _qty;
    var isEdit = _editLineId !== null;

    if (_qty > 0) {
      ctaBtn.disabled = false;
      ctaBtn.classList.remove('pm-cta-remove');
      ctaTextEl.textContent  = isEdit ? 'Actualizar pedido' : 'Añadir al carrito';
      ctaPriceEl.textContent = total.toFixed(2).replace('.', ',') + ' €';
    } else if (isEdit) {
      // Edit mode at qty=0 → allow removal
      ctaBtn.disabled = false;
      ctaBtn.classList.add('pm-cta-remove');
      ctaTextEl.textContent  = 'Quitar del carrito';
      ctaPriceEl.textContent = '';
    } else {
      // Add mode at qty=0 → disabled
      ctaBtn.disabled = true;
      ctaBtn.classList.remove('pm-cta-remove');
      ctaTextEl.textContent  = 'Selecciona cantidad';
      ctaPriceEl.textContent = '';
    }
  }

  // ─── Confirm ─────────────────────────────────────────────────────
  function confirm() {
    if (!_item) return;

    if (!window.cartItems) window.cartItems = [];

    var removed = Object.keys(_ingState).filter(function (k) { return !_ingState[k]; });

    if (_editLineId !== null) {
      // Edit mode
      var idx = window.cartItems.findIndex(function (ci) { return ci.lineId === _editLineId; });
      if (idx !== -1) {
        if (_qty === 0) {
          window.cartItems.splice(idx, 1);  // remove line
        } else {
          window.cartItems[idx] = {
            lineId:   _editLineId,
            itemName: _item,
            category: _category,
            qty:      _qty,
            removed:  removed,
          };
        }
      }
    } else {
      // Add mode — always push a new line item
      if (_qty > 0) {
        window.cartItems.push({
          lineId:   genId(),
          itemName: _item,
          category: _category,
          qty:      _qty,
          removed:  removed,
        });
      }
    }

    _updateBadge(_item);
    if (typeof window.updateCartBar === 'function') window.updateCartBar();
    close();
  }

  // ─── Helpers ─────────────────────────────────────────────────────
  function _totalQtyForItem(itemName) {
    if (!window.cartItems) return 0;
    return window.cartItems
      .filter(function (ci) { return ci.itemName === itemName; })
      .reduce(function (s, ci) { return s + ci.qty; }, 0);
  }

  function _updateBadge(itemName) {
    var total = _totalQtyForItem(itemName);
    var badge = document.getElementById('badge-' + itemName);
    if (!badge) return;
    if (total > 0) {
      badge.textContent = total;
      badge.classList.add('visible');
    } else {
      badge.classList.remove('visible');
    }
  }

  function _esc(str) {
    return str
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ─── Public API ──────────────────────────────────────────────────
  window.openProductModal     = open;
  window.openProductModalEdit = openEdit;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
