import assert from 'node:assert/strict';
import test from 'node:test';
import { sourceModule } from './sourceModule.mjs';

const { blockerMention } = await import(sourceModule(new URL('../src/lib/blockerMention.ts', import.meta.url)));

test('blocker lookup requires a single hash at a word boundary outside code', () => {
  for (const [source, expected] of [['#', ''], ['#23', '23'], ['wait #name', 'name']]) {
    assert.equal(blockerMention(source, source.length, false)?.query, expected);
  }
  for (const source of ['# heading', '##title', 'text#name', '[[task:2]]', '\\#name']) {
    assert.equal(blockerMention(source, source.length, false), null);
  }
  assert.equal(blockerMention('#task', 5, true), null);
  assert.equal(blockerMention('# heading', 1, false), null);
});
