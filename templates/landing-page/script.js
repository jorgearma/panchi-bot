/* ============================================================
   PANCHI-BOT LANDING — script.js
   Artisan Tech edition
   ============================================================ */
'use strict';

/* ============================================================
   NAV
   ============================================================ */
const navToggle = document.getElementById('navToggle');
const navLinks  = document.querySelector('.nav-links');
const mainNav   = document.getElementById('mainNav');

navToggle.addEventListener('click', () => {
  navLinks.classList.toggle('open');
  // Animate hamburger to X
  const spans = navToggle.querySelectorAll('span');
  if (navLinks.classList.contains('open')) {
    spans[0].style.transform = 'rotate(45deg) translate(5px, 5px)';
    spans[1].style.opacity = '0';
    spans[2].style.transform = 'rotate(-45deg) translate(5px, -5px)';
  } else {
    spans[0].style.transform = '';
    spans[1].style.opacity = '';
    spans[2].style.transform = '';
  }
});
document.querySelectorAll('.nav-links a').forEach(a => {
  a.addEventListener('click', () => {
    navLinks.classList.remove('open');
    const spans = navToggle.querySelectorAll('span');
    spans[0].style.transform = '';
    spans[1].style.opacity = '';
    spans[2].style.transform = '';
  });
});

// Nav background on scroll
let lastScroll = 0;
window.addEventListener('scroll', () => {
  const y = window.scrollY;
  mainNav.classList.toggle('scrolled', y > 40);
  lastScroll = y;
}, { passive: true });

/* ---- SMOOTH SCROLL ---- */
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', e => {
    const target = document.querySelector(anchor.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

/* ============================================================
   SCROLL REVEAL
   ============================================================ */
const revealObserver = new IntersectionObserver((entries) => {
  entries.forEach((entry, i) => {
    if (entry.isIntersecting) {
      // Stagger children if they have data-reveal
      const el = entry.target;
      const delay = el.dataset.revealDelay || 0;
      setTimeout(() => {
        el.classList.add('revealed');
      }, Number(delay));
      revealObserver.unobserve(el);
    }
  });
}, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

document.querySelectorAll('[data-reveal]').forEach((el, i) => {
  // Auto-stagger siblings
  const parent = el.parentElement;
  const siblings = parent.querySelectorAll(':scope > [data-reveal]');
  if (siblings.length > 1) {
    const idx = Array.from(siblings).indexOf(el);
    el.dataset.revealDelay = idx * 120;
  }
  revealObserver.observe(el);
});

/* Phones use CSS entrance animation only — no JS float */

/* ============================================================
   3D TILT on cards
   ============================================================ */
document.querySelectorAll('[data-tilt]').forEach(card => {
  card.addEventListener('mousemove', (e) => {
    const rect = card.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    const rotateY = (x - 0.5) * 6;
    const rotateX = (y - 0.5) * -6;
    card.style.transform = `perspective(600px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-4px)`;
  });
  card.addEventListener('mouseleave', () => {
    card.style.transform = '';
  });
});

/* ============================================================
   DEMO SCENE CONTROLLER
   ============================================================ */
const TOTAL_SCENES = 3;
let currentScene = 0;

const prevBtn = document.getElementById('demoPrev');
const nextBtn = document.getElementById('demoNext');

function goToScene(n) {
  if (n < 0 || n >= TOTAL_SCENES) return;

  document.querySelectorAll('.scene').forEach((s, i) => {
    s.classList.toggle('active', i === n);
  });

  document.querySelectorAll('.scene-btn').forEach((btn, i) => {
    btn.classList.remove('active', 'done');
    if (i === n) btn.classList.add('active');
    if (i < n)  btn.classList.add('done');
  });

  document.querySelectorAll('.demo-dot').forEach((dot, i) => {
    dot.classList.toggle('active', i === n);
  });

  prevBtn.disabled = n === 0;
  nextBtn.textContent = '';
  nextBtn.innerHTML = n === TOTAL_SCENES - 1
    ? 'Ver de nuevo <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>'
    : 'Siguiente <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"/></svg>';

  currentScene = n;
  playScene(n);
}

prevBtn.addEventListener('click', () => {
  if (currentScene > 0) goToScene(currentScene - 1);
});
nextBtn.addEventListener('click', () => {
  if (currentScene < TOTAL_SCENES - 1) {
    goToScene(currentScene + 1);
  } else {
    goToScene(0);
  }
});
document.querySelectorAll('.scene-btn, .demo-dot').forEach(btn => {
  btn.addEventListener('click', () => goToScene(Number(btn.dataset.scene)));
});

/* ============================================================
   SCENE 1 — WhatsApp chat animation
   ============================================================ */
let scene1Timer = [];

function clearTimers(arr) { arr.forEach(clearTimeout); arr.length = 0; }

function activateStep(scenePrefix, n) {
  for (let i = 1; i <= 3; i++) {
    const el = document.querySelector(`.step-${scenePrefix}-${i}`);
    if (!el) continue;
    el.classList.toggle('active', i <= n);
  }
}

function playScene1() {
  clearTimers(scene1Timer);
  activateStep('1', 0);

  const chat = document.getElementById('chat1');
  const cursor = document.getElementById('typingCursor1');
  chat.innerHTML = '';
  cursor.textContent = '';
  cursor.className = '';

  scene1Timer.push(setTimeout(() => {
    activateStep('1', 1);
    typeInInput(cursor, 'Hola, quiero hacer un pedido 🍕', 55, () => {
      cursor.textContent = '';
      cursor.className = '';
      addBubble(chat, 'user', 'Hola, quiero hacer un pedido 🍕');
    });
  }, 200));

  scene1Timer.push(setTimeout(() => {
    activateStep('1', 2);
    showTypingIndicator(chat, () => {
      addBubble(chat, 'bot', '¡Hola Carlos! 👋 Me alegra verte por aquí.');
    });
  }, 1800));

  scene1Timer.push(setTimeout(() => {
    showTypingIndicator(chat, () => {
      addBubble(chat, 'bot', 'Aquí tienes tu enlace de menú personalizado:');
    });
  }, 3000));

  scene1Timer.push(setTimeout(() => {
    activateStep('1', 3);
    addLinkBubble(chat);
  }, 4200));
}

function typeInInput(el, text, speed, cb) {
  el.className = 'typing-cursor';
  let i = 0;
  const t = setInterval(() => {
    el.textContent = text.slice(0, ++i);
    el.classList.toggle('typing-cursor', i < text.length);
    if (i >= text.length) { clearInterval(t); if (cb) setTimeout(cb, 300); }
  }, speed);
}

function showTypingIndicator(chat, cb) {
  const indicator = document.createElement('div');
  indicator.className = 'wa-bubble wa-bubble-bot';
  indicator.innerHTML = '<span style="letter-spacing:2px;font-size:.85rem">●●●</span>';
  indicator.style.opacity = '.6';
  chat.appendChild(indicator);
  chat.scrollTop = chat.scrollHeight;
  setTimeout(() => { chat.removeChild(indicator); if (cb) cb(); }, 900);
}

function addBubble(chat, type, text) {
  const div = document.createElement('div');
  div.className = `wa-bubble wa-bubble-${type}`;
  div.innerHTML = `${text}<div class="wa-bubble-time">${getTime()}</div>`;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function addLinkBubble(chat) {
  const div = document.createElement('div');
  div.className = 'wa-bubble-link';
  div.innerHTML = `
    <div class="link-label">🔗 Enlace de menú</div>
    <div class="link-title">🍕 Panchi — Tu pedido</div>
    <div class="link-url">panchi.bot/menu/c4f2e...</div>
  `;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
}

function getTime() {
  const now = new Date();
  return `${now.getHours()}:${String(now.getMinutes()).padStart(2,'0')}`;
}

/* ============================================================
   SCENE 2 — Menu interaction
   ============================================================ */
let scene2Timer = [];
let cartItems = [];
let cartTotal = 0;

function playScene2() {
  clearTimers(scene2Timer);
  activateStep('2', 0);

  cartItems = [];
  cartTotal = 0;
  document.getElementById('cartCount').textContent = '0 artículos';
  document.getElementById('cartTotal').textContent = '€0.00';
  document.querySelectorAll('.item-add').forEach(btn => {
    btn.textContent = '+';
    btn.classList.remove('added');
  });
  document.querySelectorAll('.menu-item').forEach(item => item.classList.remove('selected'));

  const autoAdd = [
    { itemId: 'item2', btnData: { item: 'Cuatro quesos', price: 12.50 }, delay: 800 },
    { itemId: 'item3', btnData: { item: 'Refresco',      price: 2.50  }, delay: 2000 },
    { itemId: 'item4', btnData: { item: 'Cerveza',       price: 1.00  }, delay: 3200 },
  ];

  scene2Timer.push(setTimeout(() => activateStep('2', 1), 300));

  autoAdd.forEach(({ itemId, btnData, delay }) => {
    scene2Timer.push(setTimeout(() => {
      const item = document.getElementById(itemId);
      const btn  = item?.querySelector('.item-add');
      if (!item || !btn) return;
      item.classList.add('selected');
      btn.textContent = '✓';
      btn.classList.add('added');
      cartTotal = +(cartTotal + btnData.price).toFixed(2);
      cartItems.push(btnData.item);
      document.getElementById('cartCount').textContent = `${cartItems.length} artículo${cartItems.length > 1 ? 's' : ''}`;
      document.getElementById('cartTotal').textContent = `€${cartTotal.toFixed(2)}`;
    }, delay));
  });

  scene2Timer.push(setTimeout(() => {
    activateStep('2', 2);
    const cartBtn = document.getElementById('cartBtn');
    cartBtn.textContent = '✅ Pagar';
    cartBtn.style.background = '#0F7A3E';
  }, 4400));

  scene2Timer.push(setTimeout(() => {
    activateStep('2', 3);
    const cartBtn = document.getElementById('cartBtn');
    cartBtn.textContent = '✅ Ver pedido';
  }, 5600));
}

function resetScene2() {
  const cartBtn = document.getElementById('cartBtn');
  if (cartBtn) {
    cartBtn.textContent = 'Ver pedido';
    cartBtn.style.background = '';
  }
}

/* ============================================================
   SCENE 3 — Confirmation + tracking
   ============================================================ */
let scene3Timer = [];

function playScene3() {
  clearTimers(scene3Timer);
  activateStep('3', 0);

  const chat = document.getElementById('chat3');
  chat.innerHTML = '';

  ['ts1','ts2','ts3','ts4'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.classList.remove('done','active');
  });
  document.querySelectorAll('.track-line').forEach(l => l.classList.remove('done'));

  const confirmMsg = '✅ *Pedido confirmado* #1842\n\n🍕 Cuatro quesos ×1\n🥤 Refresco ×1\n🍺 Cerveza ×1\n\n*Total: €16.00*\nTiempo estimado: ⏱ 30 min';
  const trackStates = [
    { id: 'ts1', msg: '🔄 Estado: *EN PREPARACIÓN*', delay: 2200 },
    { id: 'ts2', msg: '✅ Estado: *PREPARADO* — ¡listo para entregar!', delay: 5000 },
    { id: 'ts3', msg: '🛵 Estado: *EN REPARTO* — el repartidor está en camino', delay: 8000 },
    { id: 'ts4', msg: '🎉 Estado: *ENTREGADO* — ¡Que aproveche!', delay: 11000 },
  ];

  scene3Timer.push(setTimeout(() => {
    activateStep('3', 1);
    addBubble(chat, 'bot', confirmMsg.replace(/\n/g, '<br/>'));
  }, 600));

  trackStates.forEach(({ id, msg, delay }, idx) => {
    scene3Timer.push(setTimeout(() => {
      if (idx === 0) activateStep('3', 2);
      if (idx === trackStates.length - 1) activateStep('3', 3);

      addBubble(chat, 'bot', msg);
      chat.scrollTop = chat.scrollHeight;

      const el = document.getElementById(id);
      if (el) {
        trackStates.slice(0, idx).forEach(prev => {
          const p = document.getElementById(prev.id);
          if (p) { p.classList.remove('active'); p.classList.add('done'); }
        });
        document.querySelectorAll('.track-line').forEach((line, li) => {
          if (li < idx) line.classList.add('done');
        });
        el.classList.add('active');
      }
    }, delay));
  });
}

/* ============================================================
   SCENE DISPATCHER
   ============================================================ */
function playScene(n) {
  if (n === 0) playScene1();
  if (n === 1) { resetScene2(); playScene2(); }
  if (n === 2) playScene3();
}

/* ============================================================
   INTERSECTION OBSERVER — auto-start demo
   ============================================================ */
const demoSection = document.getElementById('demo');
let demoStarted = false;

const demoObserver = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting && !demoStarted) {
      demoStarted = true;
      goToScene(0);
    }
  });
}, { threshold: 0.3 });

if (demoSection) demoObserver.observe(demoSection);

/* ============================================================
   CONTACT FORM
   ============================================================ */
const form      = document.getElementById('ctaForm');
const success   = document.getElementById('formSuccess');
const submitBtn = document.getElementById('formSubmit');

form.addEventListener('submit', e => {
  e.preventDefault();
  const name  = document.getElementById('formName').value.trim();
  const rest  = document.getElementById('formRestaurant').value.trim();
  const phone = document.getElementById('formPhone').value.trim();
  const email = document.getElementById('formEmail').value.trim();

  if (!name || !rest || !phone || !email) {
    document.querySelectorAll('.form-group input[required]').forEach(input => {
      if (!input.value.trim()) {
        input.style.borderColor = '#ef4444';
        input.addEventListener('input', () => input.style.borderColor = '', { once: true });
      }
    });
    return;
  }

  submitBtn.textContent = 'Enviando...';
  submitBtn.disabled = true;

  setTimeout(() => {
    submitBtn.style.display = 'none';
    success.style.display   = 'block';
  }, 1200);
});

/* ============================================================
   FAQ ACCORDION
   ============================================================ */
document.querySelectorAll('.faq-question').forEach(question => {
  question.addEventListener('click', () => {
    const item = question.closest('.faq-item');
    const isOpen = item.classList.contains('open');

    document.querySelectorAll('.faq-item.open').forEach(openItem => {
      if (openItem !== item) openItem.classList.remove('open');
    });

    item.classList.toggle('open', !isOpen);
  });
});

/* ============================================================
   Init
   ============================================================ */
window.addEventListener('DOMContentLoaded', () => {
  prevBtn.disabled = true;
});
