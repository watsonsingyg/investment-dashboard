/**
 * Pipeline PWA · Service Worker
 * 缓存策略：静态资源 Cache First · API Network First
 */
const CACHE_NAME = 'pipeline-v1';
const STATIC_ASSETS = [
  '/',
  '/login',
  '/static/base.css',
  '/static/base.js',
  '/static/toast.js',
  '/static/auth.js',
  '/static/manifest.json',
];

// ── Install: 预缓存核心静态资源 ──
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch(() => {});
    })
  );
  self.skipWaiting();
});

// ── Activate: 清理旧缓存 ──
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
      );
    })
  );
  self.clients.claim();
});

// ── Fetch ──
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // 跳过非 GET 请求
  if (event.request.method !== 'GET') return;

  // API 请求：Network First
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(event.request));
    return;
  }

  // 静态资源：Cache First
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(cacheFirst(event.request));
    return;
  }

  // 页面：Network First with cache fallback
  event.respondWith(networkFirst(event.request));
});

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
  } catch (e) {
    return new Response('Offline', { status: 503 });
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
  } catch (e) {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ error: '网络不可用' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}
