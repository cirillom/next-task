import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import { sourceModule } from './sourceModule.mjs';

const {
  urlBase64ToUint8Array,
  isIosLike,
  isStandaloneDisplay,
  pushSupportStatus,
  parseTaskHashTarget
} = await import(sourceModule(new URL('../src/lib/notifications.ts', import.meta.url)));

test('urlBase64ToUint8Array decodes unpadded VAPID keys cleanly', () => {
  const bytes = urlBase64ToUint8Array('SGVsbG8td29ybGRf');
  assert.deepEqual([...bytes], [...Buffer.from('Hello-world_')]);
});

test('pushSupportStatus handles HTTPS, iOS Home Screen, unsupported, denied, and granted states', () => {
  assert.equal(pushSupportStatus({ isSecureContext: false, hasServiceWorker: true, hasPushManager: true, permission: 'default', iosLike: false, standalone: false }), 'insecure');
  assert.equal(pushSupportStatus({ isSecureContext: true, hasServiceWorker: false, hasPushManager: false, permission: null, iosLike: true, standalone: false }), 'ios-install-required');
  assert.equal(pushSupportStatus({ isSecureContext: true, hasServiceWorker: true, hasPushManager: true, permission: 'default', iosLike: true, standalone: true }), 'default');
  assert.equal(pushSupportStatus({ isSecureContext: true, hasServiceWorker: true, hasPushManager: false, permission: 'default', iosLike: false, standalone: false }), 'unsupported');
  assert.equal(pushSupportStatus({ isSecureContext: true, hasServiceWorker: true, hasPushManager: true, permission: 'denied', iosLike: false, standalone: false }), 'denied');
  assert.equal(pushSupportStatus({ isSecureContext: true, hasServiceWorker: true, hasPushManager: true, permission: 'granted', iosLike: false, standalone: false }), 'granted');
  assert.equal(isIosLike({ userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)' }), true);
  assert.equal(isIosLike({ userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X)', platform: 'MacIntel', maxTouchPoints: 5 }), true);
  assert.equal(isStandaloneDisplay({ matchMedia: () => ({ matches: true }) }, {}), true);
});

test('parseTaskHashTarget extracts positive integer task IDs only from #/tasks?task=...', () => {
  assert.equal(parseTaskHashTarget('/#/tasks?task=42'), 42);
  assert.equal(parseTaskHashTarget('https://tasks.example.com/#/tasks?task=7'), 7);
  assert.equal(parseTaskHashTarget('#/tasks?task=0'), null);
  assert.equal(parseTaskHashTarget('#/tasks?task=abc'), null);
  assert.equal(parseTaskHashTarget('#/settings'), null);
});

test('service worker push displays notification and notificationclick routes safely', async () => {
  const swSource = readFileSync(new URL('../public/sw.js', import.meta.url), 'utf8');
  const listeners = new Map();
  const shown = [];
  const posted = [];
  const opened = [];
  let focused = false;
  let closed = false;

  const sandbox = {
    URL,
    caches: { open: async () => ({ addAll: async () => {}, put: async () => {} }), keys: async () => [], match: async () => undefined, delete: async () => true },
    fetch: async () => ({ clone: () => ({}) }),
    self: {
      location: { origin: 'https://tasks.example.com' },
      skipWaiting: () => {},
      registration: { showNotification: async (title, options) => { shown.push({ title, options }); } },
      clients: {
        claim: () => {},
        matchAll: async () => [],
        openWindow: async (url) => { opened.push(url); }
      },
      addEventListener: (name, fn) => listeners.set(name, fn)
    }
  };
  vm.runInNewContext(swSource, sandbox);

  let waitPromise;
  listeners.get('push')({
    data: { json: () => ({ title: 'Task due today', body: 'Due today: Taxes', url: '/#/tasks?task=9', tag: 'due:9' }) },
    waitUntil: (promise) => { waitPromise = promise; }
  });
  await waitPromise;
  assert.equal(shown.length, 1);
  assert.equal(shown[0].title, 'Task due today');
  assert.equal(shown[0].options.data.url, '/#/tasks?task=9');

  // When no open window matches, opens a new window
  listeners.get('notificationclick')({
    notification: { data: { url: '/#/tasks?task=9' }, close: () => { closed = true; } },
    waitUntil: (promise) => { waitPromise = promise; }
  });
  await waitPromise;
  assert.equal(closed, true);
  assert.deepEqual(opened, ['https://tasks.example.com/#/tasks?task=9']);

  // External / protocol-relative URLs are rejected back to /#/tasks
  sandbox.self.clients.matchAll = async () => [{
    url: 'https://tasks.example.com/#/next',
    focus: async () => { focused = true; },
    postMessage: (msg) => posted.push(msg)
  }];
  listeners.get('notificationclick')({
    notification: { data: { url: 'https://evil.example/phish' }, close: () => {} },
    waitUntil: (promise) => { waitPromise = promise; }
  });
  await waitPromise;
  assert.equal(focused, true);
  assert.equal(posted.length, 1);
  assert.equal(posted[0].type, 'notification-click');
  assert.equal(posted[0].url, '/#/tasks');
});
