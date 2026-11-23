import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import vm from 'node:vm';

test('service worker leaves private and protocol requests to the network', async () => {
  const handlers = {};
  const context = {
    self: { addEventListener: (name, handler) => { handlers[name] = handler; } },
    URL,
    fetch: () => Promise.resolve({ clone: () => ({}) }),
    caches: { open: async () => ({ put: async () => {} }) }
  };
  vm.runInNewContext(await readFile(new URL('../public/sw.js', import.meta.url), 'utf8'), context);
  for (const path of ['/api/auth/me', '/oauth/authorize?state=private', '/oauth/token', '/mcp',
    '/mcp/anything', '/.well-known/oauth-authorization-server']) {
    let intercepted = false;
    handlers.fetch({ request: { method: 'GET', url: `https://example.com${path}` },
      respondWith: () => { intercepted = true; } });
    assert.equal(intercepted, false, path);
  }
  let response;
  handlers.fetch({ request: { method: 'GET', url: 'https://example.com/icon.svg' },
    respondWith: promise => { response = promise; } });
  assert.ok(response);
  await response;
});

test('activation removes the old shell cache that could contain OAuth URLs', async () => {
  const handlers = {};
  const deleted = [];
  const context = {
    self: { addEventListener: (name, handler) => { handlers[name] = handler; }, clients: { claim() {} } },
    URL,
    caches: { keys: async () => ['next-task-shell-v2', 'next-task-shell-v3'],
      delete: async name => { deleted.push(name); } }
  };
  vm.runInNewContext(await readFile(new URL('../public/sw.js', import.meta.url), 'utf8'), context);
  let activation;
  handlers.activate({ waitUntil: promise => { activation = promise; } });
  await activation;
  assert.deepEqual(deleted, ['next-task-shell-v2']);
});
