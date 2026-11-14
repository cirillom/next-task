import assert from 'node:assert/strict';
import test from 'node:test';
import { shellAssets } from '../i18n-shell.mjs';
test('offline and install metadata are generated from the registered catalogs', () => {
  const assets = shellAssets();
  assert.equal(JSON.parse(assets['manifest.en.webmanifest']).lang, 'en');
  assert.equal(JSON.parse(assets['manifest.pt-BR.webmanifest']).lang, 'pt-BR');
  assert.match(JSON.parse(assets['manifest.pt-BR.webmanifest']).description, /tarefas/);
  assert.match(assets['offline.html'], /Você está offline/);
  assert.match(assets['offline.html'], /You are offline/);
  assert.doesNotMatch(assets['offline.html'], /__[A-Z]+__/);
});
