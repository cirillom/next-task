import assert from 'node:assert/strict';
import test from 'node:test';
import { createRequire } from 'node:module';
import { sourceModule } from './sourceModule.mjs';

const require = createRequire(import.meta.url);
const { EditorState } = require('@codemirror/state');
const { history, undo, redo } = require('@codemirror/commands');
const { markdownSource, markdownSourceState, sourceOffsets } = await import(sourceModule(new URL('../src/lib/markdownDocument.ts', import.meta.url)));

test('source positions and undo retain CRLF, mixed line endings and UTF-16 offsets', () => {
  const source = '😀\r\nA\nB\rC';
  assert.deepEqual(sourceOffsets(source), [0, 1, 2, 4, 5, 6, 7, 8, 9]);
  let state = EditorState.create({doc: source, extensions: [history(), markdownSourceState(source)]});
  const view = {get state() { return state; }, dispatch(transaction) { state = state.update(transaction).state; }};
  view.dispatch({changes: {from: 2, to: 5, insert: 'X\n'}});
  assert.equal(state.field(markdownSource), '😀X\nB\rC');
  assert.equal(undo(view), true);
  assert.equal(state.field(markdownSource), source);
  assert.equal(redo(view), true);
  assert.equal(state.field(markdownSource), '😀X\nB\rC');
});
