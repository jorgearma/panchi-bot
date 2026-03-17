// Panchi Reparto — Service Worker
// Bump CACHE_NAME en cada deploy para invalidar la caché anterior
const CACHE_NAME = 'panchi-reparto-v1';

// Recursos que se pre-cachean durante el install
const PRECACHE = [
  '/repartidor',
  'https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js',
];

// ---- Install: pre-cachear el shell y Alpine ----
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

// ---- Activate: eliminar cachés antiguas ----
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// ---- Fetch: estrategia por tipo de recurso ----
self.addEventListener('fetch', event => {
  const { request } = event;
  const url = new URL(request.url);

  // Solo interceptar GET
  if (request.method !== 'GET') return;

  // CDN externo (Alpine, Tailwind) — cache-first
  if (url.hostname !== self.location.hostname) {
    event.respondWith(cacheFirst(request));
    return;
  }

  // App shell del repartidor — network-first con fallback a caché
  if (url.pathname === '/repartidor') {
    event.respondWith(networkFirst(request));
    return;
  }

  // Endpoints de datos (/repartidor/mis-pedidos, etc.) — network only, sin caché
  // Las mutaciones (POST) ya se saltan por el guard de arriba
});

// ---- Estrategias ----

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return cached ?? new Response('Recurso no disponible sin conexión', { status: 503 });
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response('Sin conexión', { status: 503, statusText: 'Offline' });
  }
}
