import assert from 'node:assert/strict';
import test from 'node:test';
import { sourceModule } from './sourceModule.mjs';

const { DescriptionSaves } = await import(sourceModule(new URL('../src/lib/descriptionSaves.ts', import.meta.url)));
const tick = () => new Promise(resolve => setTimeout(resolve, 0));

test('serializes each task, coalesces edits, and keeps independent tasks separate', async () => {
  const requests = [];
  const queue = new DescriptionSaves((...args) => new Promise((resolve, reject) => requests.push({ args, resolve, reject })));
  queue.open(1, 'A');
  queue.open(2, 'B');
  queue.edit(1, 'A1'); queue.flush(1);
  queue.edit(1, 'A2'); queue.flush(1);
  queue.edit(2, 'B1'); queue.flush(2);
  assert.deepEqual(requests.map(r => r.args), [[1, 'A1', 'A'], [2, 'B1', 'B']]);
  requests[0].resolve(); await tick();
  assert.deepEqual(requests[2].args, [1, 'A2', 'A1']);
  assert.equal(queue.get(1).state, 'saving');
  requests[1].resolve(); requests[2].resolve(); await tick();
  assert.equal(queue.get(1).state, 'saved');
  assert.equal(queue.get(2).state, 'saved');
  assert.equal(queue.dirty(), false);
});

test('preserves failed drafts until explicit retry or reload and ignores old account responses', async () => {
  const requests = [];
  const queue = new DescriptionSaves((...args) => new Promise((resolve, reject) => requests.push({ args, resolve, reject })));
  queue.open(1, null);
  queue.edit(1, 'Local'); queue.flush(1);
  requests[0].reject(new Error('conflict')); await tick();
  assert.equal(queue.get(1).state, 'error');
  assert.equal(queue.open(1, 'Remote').value, 'Local');
  queue.flush(1);
  assert.equal(requests.length, 1);
  queue.resolve(1, 'Remote', true);
  assert.deepEqual(requests[1].args, [1, 'Local', 'Remote']);
  queue.clear(); queue.open(1, 'Another account');
  requests[1].resolve(); await tick();
  assert.equal(queue.get(1).value, 'Another account');
  assert.equal(queue.dirty(), false);
});

test('opening or flushing unchanged empty source does not rewrite it', () => {
  let calls = 0;
  const queue = new DescriptionSaves(async () => { calls++; });
  queue.open(1, ''); queue.flush(1);
  assert.equal(calls, 0);
});
