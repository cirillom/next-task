import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import ts from 'typescript';

const source = readFileSync(new URL('../src/lib/tagHierarchy.ts', import.meta.url), 'utf8')
  .replace("import type { Tag } from './api/types';\n\n", '');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 }
}).outputText;
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString('base64')}`;
const { filterTagsByHierarchy, tagHierarchyPaths } = await import(moduleUrl);

const tag = (id, name, parents = []) => ({
  id,
  name,
  color: null,
  workspace_id: 1,
  description: null,
  parents,
  children: [],
  ancestors: []
});

const project = tag(1, 'Project');
const homelab = tag(2, 'Homelab', [{ id: 1, name: 'Project', color: null }]);
const infrastructure = tag(3, 'Infrastructure');
const maintenance = tag(4, 'Server Maintenance', [
  { id: 2, name: 'Homelab', color: null },
  { id: 3, name: 'Infrastructure', color: null }
]);
const personal = tag(5, 'Personal');
const tags = [project, homelab, infrastructure, maintenance, personal];

test('builds hierarchy paths including multiple parents', () => {
  assert.deepEqual(tagHierarchyPaths(project, tags), ['Project']);
  assert.deepEqual(tagHierarchyPaths(homelab, tags), ['Project › Homelab']);
  assert.deepEqual(tagHierarchyPaths(maintenance, tags), [
    'Infrastructure › Server Maintenance',
    'Project › Homelab › Server Maintenance'
  ]);
});

test('search matches tag names and ancestor path context', () => {
  assert.deepEqual(filterTagsByHierarchy(tags, 'server').map((item) => item.id), [4]);
  assert.deepEqual(filterTagsByHierarchy(tags, 'homelab').map((item) => item.id), [2, 4]);
  assert.deepEqual(filterTagsByHierarchy(tags, 'project').map((item) => item.id), [1, 2, 4]);
  assert.deepEqual(filterTagsByHierarchy(tags, '#personal').map((item) => item.id), [5]);
});
