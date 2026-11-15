import assert from 'node:assert/strict';
import test from 'node:test';
import { sourceModule } from './sourceModule.mjs';

const { CardDescriptionSaves } = await import(sourceModule(new URL('../src/lib/cardDescriptionSaves.ts', import.meta.url)));

test('keeps failed card changes across subscribers and ignores responses after account clearing', async () => {
  const requests = [];
  const saves = new CardDescriptionSaves((...args) => new Promise((resolve, reject) => requests.push({args, resolve, reject})), async () => null);
  const unsubscribe = saves.subscribe(() => {});
  const attempt = {id: 1, base: '- [ ] one', value: '- [x] one'};
  const first = saves.save(attempt);
  unsubscribe();
  requests[0].reject(new Error('offline'));
  await first;
  assert.deepEqual(saves.get(1).pending, attempt);
  assert.equal(saves.get(1).error.message, 'offline');
  const retry = saves.save(saves.get(1).pending);
  saves.clear();
  requests[1].resolve({id: 1, description: attempt.value});
  assert.equal(await retry, null);
  assert.equal(saves.get(1), undefined);
});
