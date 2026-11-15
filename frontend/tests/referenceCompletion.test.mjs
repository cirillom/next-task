import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';
import { sourceModule } from './sourceModule.mjs';

const require = createRequire(import.meta.url);
const { EditorState } = require('@codemirror/state');
const { CompletionContext } = require('@codemirror/autocomplete');
const { markdown, markdownLanguage } = require('@codemirror/lang-markdown');
const { referenceCompletionSource } = await import(sourceModule(new URL('../src/lib/referenceCompletion.ts', import.meta.url)));
const context = source => new CompletionContext(EditorState.create({doc: source, extensions: [markdown({base: markdownLanguage})]}), source.length, false);

test('reference completions insert canonical IDs and keep server-filtered results', async t => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify([{kind: 'task', id: 7, label: 'Meeting', paths: []}])));
  const result = await referenceCompletionSource(context('[[Meet'));
  assert.equal(result.filter, false);
  assert.equal(result.options[0].apply, '[[task:7]]');
  assert.equal(await referenceCompletionSource(context('`[[Meet`')), null);
  assert.equal(await referenceCompletionSource(context('\\[[Meet')), null);
});

test('a response for an older query cannot replace the current suggestions', async t => {
  let finish;
  t.mock.method(globalThis, 'fetch', () => new Promise(resolve => {finish = resolve;}));
  const state = EditorState.create({doc: '[[Meet', selection: {anchor: 6}, extensions: [markdown({base: markdownLanguage})]});
  const view = {state};
  const result = referenceCompletionSource(new CompletionContext(state, 6, false, view));
  while (!finish) await new Promise(resolve => setTimeout(resolve, 10));
  view.state = EditorState.create({doc: '[[Other', selection: {anchor: 7}});
  finish(new Response(JSON.stringify([{kind: 'task', id: 7, label: 'Meeting', paths: []}])));
  assert.equal(await result, null);
});
