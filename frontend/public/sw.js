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
  if (event.request.method !== 'GET' || new URL(event.request.url).pathname.startsWith('/api/')) return;
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

self.addEventListener('push', (event) => {
  let data = {};
  if (event.data) {
    try {
      data = event.data.json();
    } catch {
      const text = event.data.text();
      if (text) data = { body: text };
    }
  }
  const title = typeof data.title === 'string' && data.title ? data.title : 'Next Task';
  const rawUrl = typeof data.url === 'string' ? data.url : '/#/tasks';
  const url = rawUrl.startsWith('/') && !rawUrl.startsWith('//') ? rawUrl : '/#/tasks';
  const options = {
    body: typeof data.body === 'string' ? data.body : '',
    icon: '/icon.svg',
    badge: '/icon.svg',
    tag: typeof data.tag === 'string' && data.tag ? data.tag : 'next-task',
    data: { url }
  };
  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const rawUrl =
    event.notification.data && typeof event.notification.data.url === 'string'
      ? event.notification.data.url
      : '/#/tasks';
  const path = rawUrl.startsWith('/') && !rawUrl.startsWith('//') ? rawUrl : '/#/tasks';
  const targetUrl = new URL(path, self.location.origin).href;

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async (clients) => {
      for (const client of clients) {
        try {
          if (new URL(client.url).origin !== self.location.origin) continue;
          if ('focus' in client) await client.focus();
          client.postMessage({ type: 'notification-click', url: path });
          return;
        } catch {
          // Try the next open window or open a new one.
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(targetUrl);
    })
  );
});
