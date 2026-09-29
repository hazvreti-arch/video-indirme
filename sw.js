const CACHE = 'vidora-v4.1-static';
const STATIC_ASSETS = [
  '/assets/app.css',
  '/assets/frontend.js',
  '/assets/tools.js',
  '/assets/settings.js',
  '/assets/library.js',
  '/assets/manifest.json',
  '/assets/icon.svg',
  '/assets/icon-192.png',
  '/assets/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys
          .filter(key => key !== CACHE)
          .map(key => caches.delete(key))
      ))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;

  const request = event.request;
  const isNavigation = request.mode === 'navigate' ||
    (request.headers.get('accept') || '').includes('text/html');

  // Always get HTML from the server so a deployment is visible immediately.
  if (isNavigation) {
    event.respondWith(
      fetch(request, { cache: 'no-store' })
        .catch(() => caches.match('/') )
    );
    return;
  }

  // Static assets: cache-first, then network fallback.
  event.respondWith(
    caches.match(request).then(cached => {
      if (cached) return cached;
      return fetch(request).then(response => {
        if (response && response.ok) {
          const copy = response.clone();
          caches.open(CACHE).then(cache => cache.put(request, copy));
        }
        return response;
      });
    })
  );
});
