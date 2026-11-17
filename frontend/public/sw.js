const CACHE = 'next-task-shell-v3';
const SHELL = ['/', '/manifest.webmanifest', '/icon.svg', '/offline.html'];

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((cache) => cache.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
  );
  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const path = new URL(event.request.url).pathname;
  if (event.request.method !== 'GET' || path.startsWith('/api/') || path.startsWith('/oauth/') ||
      path === '/mcp' || path.startsWith('/mcp/') || path.startsWith('/.well-known/')) return;
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(async () => (await caches.match(event.request)) || (await caches.match('/offline.html')))
  );
});

