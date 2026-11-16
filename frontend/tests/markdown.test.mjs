import assert from 'node:assert/strict';
import test from 'node:test';
import { sourceModule } from './sourceModule.mjs';
import { Marked } from 'marked';

const { checklistOffsets, editChecklist, parsedFootnotes, parsedHighlights, parsedInlineMath, parsedReferences } = await import(sourceModule(new URL('../src/lib/markdown.ts', import.meta.url)));

test('maps footnote references to matching definitions and leaves code literal', () => {
  const source = 'Text[^a] and again[^a]\r\n\r\n`[^a]`\r\n\r\n[^a]: Example';
  const result = parsedFootnotes(source);
  assert.deepEqual(result.references.map(ref => ref.id), ['1', '1']);
  assert.equal(source.slice(result.positions.get('a')), '[^a]: Example');
});

test('maps duplicate, nested, quoted and ordered tasks to their exact UTF-16 characters', () => {
  const source = '😀\r\n\r\n> - [ ] same\r\n>   - [X] same\r\n\r\n1. [ ] same\r\n\r\n```\r\n- [ ] example\r\n```\r\n';
  const offsets = [...checklistOffsets(source).values()];
  assert.deepEqual(offsets.map(offset => source.slice(offset - 1, offset + 2)), ['[ ]', '[X]', '[ ]']);
  const updated = editChecklist(source, source, offsets[1], false);
  assert.equal(updated, source.slice(0, offsets[1]) + ' ' + source.slice(offsets[1] + 1));
  assert.equal(editChecklist(updated, source, offsets[0], true), null);
  assert.equal(editChecklist(source, source, offsets[1], true), source);
});

test('does not treat escaped markers or code as tasks', () => {
  const source = '- \\[ ] escaped\n- `[ ]` code\n\n    - [ ] indented code\n';
  assert.equal(checklistOffsets(source).size, 0);
  assert.equal(editChecklist(source, source, 3, true), null);
});

test('parser disagreement disables every mapping instead of guessing', () => {
  const source = '- [ ] first\n- [ ] second\n';
  const tokens = new Marked().lexer('- [x] first\n- [ ] second\n');
  assert.equal(checklistOffsets(source, tokens).size, 0);
});

test('footnotes and reference definitions do not move checklist offsets', () => {
  const source = '- [ ] task with [link][ref] and note[^n]\n\n[ref]: https://example.com\n[^n]: Footnote\n';
  const offsets = [...checklistOffsets(source).values()];
  assert.deepEqual(offsets, [3]);
  assert.equal(editChecklist(source, source, offsets[0], true), source.replace('[ ]', '[x]'));
});

test('reference tokens exclude escaped references and code examples', () => {
  const source = '[[task:7]] [[tag:42|My tag]] `[[task:9]]` \\[[task:10]]\n\n```\n[[task:11]]\n```';
  assert.deepEqual(parsedReferences(source), [
    {kind: 'task', id: 7, raw: '[[task:7]]', alias: null},
    {kind: 'tag', id: 42, raw: '[[tag:42|My tag]]', alias: 'My tag'}
  ]);
});

test('highlight markers remain literal inside escaped and code text', () => {
  assert.deepEqual(parsedHighlights('==visible== `==code==` \\==escaped==\n\n```\n==fenced==\n```'), ['==visible==']);
});

test('math tokenization leaves currency, escapes and code examples literal', () => {
  const source = 'cost $5 and $10, $x^2$ and \\$y$ and `$z$`';
  assert.deepEqual(parsedInlineMath(source), [{raw: '$x^2$', source: 'x^2', display: false}]);
});
