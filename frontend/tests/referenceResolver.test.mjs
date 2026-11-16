import assert from 'node:assert/strict';
import test from 'node:test';
import { sourceModule } from './sourceModule.mjs';

const { resolveReference, clearReferenceResolver } = await import(sourceModule(new URL('../src/lib/referenceResolver.ts', import.meta.url)));

test('deduplicates a render pass and splits requests into bounded batches', async t => {
  const batches = [];
  t.mock.method(globalThis, 'fetch', async (_path, init) => {
    const {items} = JSON.parse(init.body);
    batches.push(items);
    return new Response(JSON.stringify(items.map(item => ({...item, label: `Item ${item.id}`, paths: []}))));
  });
  const inputs = [...Array.from({length: 105}, (_, index) => ({kind: 'task', id: index + 1})), {kind: 'task', id: 1}];
  const results = await Promise.all(inputs.map(resolveReference));
  assert.deepEqual(batches.map(batch => batch.length), [100, 5]);
  assert.equal(results[0].label, 'Item 1');
  assert.equal(results[105].label, 'Item 1');
});

test('account clearing discards a response already in flight', async t => {
  let finish;
  t.mock.method(globalThis, 'fetch', () => new Promise(resolve => {finish = resolve;}));
  const result = resolveReference({kind: 'tag', id: 1});
  await new Promise(resolve => setTimeout(resolve, 0));
  clearReferenceResolver();
  finish(new Response(JSON.stringify([{kind: 'tag', id: 1, label: 'Private', paths: []}])));
  assert.equal(await result, null);
});
