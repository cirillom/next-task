import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/tagScope.ts', import.meta.url), 'utf8')
  .replace("import type { NextScope } from './api/types';\n\n", '');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }
}).outputText;
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`;
const { cleanTagScope, emptyTagScope, sameTagScope, withExcludedTags, withIncludedTags } = await import(moduleUrl);

test('restored Next scope drops stale and overlapping IDs without changing match mode', () => {
  const restored = cleanTagScope({
    include_tag_ids: [3, 1, 3, 99],
    exclude_tag_ids: [2, 3, 99],
    tag_match: 'any'
  }, new Set([1, 2, 3]));
  assert.deepEqual(restored, {
    include_tag_ids: [1, 3],
    exclude_tag_ids: [2],
    tag_match: 'any'
  });
});

test('moving a tag between Include and Exclude removes it from the opposite selection', () => {
  const included = withIncludedTags({
    include_tag_ids: [1], exclude_tag_ids: [2], tag_match: 'all'
  }, [1, 2]);
  assert.deepEqual(included.include_tag_ids, [1, 2]);
  assert.deepEqual(included.exclude_tag_ids, []);

  const excluded = withExcludedTags(included, [2]);
  assert.deepEqual(excluded.include_tag_ids, [1]);
  assert.deepEqual(excluded.exclude_tag_ids, [2]);
});

test('scope comparison ignores tag selection order and Clear resets match mode', () => {
  assert.equal(sameTagScope(
    { include_tag_ids: [2, 1], exclude_tag_ids: [], tag_match: 'any' },
    { include_tag_ids: [1, 2], exclude_tag_ids: [], tag_match: 'any' }
  ), true);
  assert.deepEqual(emptyTagScope(), {
    include_tag_ids: [], exclude_tag_ids: [], tag_match: 'all'
  });
});
