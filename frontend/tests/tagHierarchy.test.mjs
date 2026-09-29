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
const { hierarchicalTagResults, tagHierarchyPaths } = await import(moduleUrl);

const summary = (id, name) => ({ id, name, color: null });
const tag = (id, name, parents = [], ancestors = []) => ({
  id,
  name,
  color: null,
  workspace_id: 1,
  description: null,
  parents,
  children: [],
  ancestors
});

const project = tag(1, 'Project');
const homelab = tag(
  2,
  'Homelab',
  [summary(1, 'Project')],
  [summary(1, 'Project')]
);
const infrastructure = tag(3, 'Infrastructure');
const maintenance = tag(
  4,
  'Server Maintenance',
  [summary(2, 'Homelab'), summary(3, 'Infrastructure')],
  [summary(1, 'Project'), summary(2, 'Homelab'), summary(3, 'Infrastructure')]
);
const personal = tag(5, 'Personal');
const nextTask = tag(
  6,
  'Next-task',
  [summary(1, 'Project')],
  [summary(1, 'Project')]
);
const tags = [project, homelab, infrastructure, maintenance, personal, nextTask];

test('builds hierarchy paths including multiple parents', () => {
  assert.deepEqual(tagHierarchyPaths(project, tags), ['Project']);
  assert.deepEqual(tagHierarchyPaths(homelab, tags), ['Project › Homelab']);
  assert.deepEqual(tagHierarchyPaths(maintenance, tags), [
    'Infrastructure › Server Maintenance',
    'Project › Homelab › Server Maintenance'
  ]);
});

test('search puts the matched root first and traverses descendants alphabetically by depth', () => {
  assert.deepEqual(
    hierarchicalTagResults(tags, 'project').map(({ tag, depth }) => [tag.name, depth]),
    [
      ['Project', 0],
      ['Homelab', 1],
      ['Server Maintenance', 2],
      ['Next-task', 1]
    ]
  );
});

test('searching a child keeps its subtree and direct depth relative to that match', () => {
  assert.deepEqual(
    hierarchicalTagResults(tags, 'homelab').map(({ tag, depth }) => [tag.name, depth]),
    [
      ['Homelab', 0],
      ['Server Maintenance', 1]
    ]
  );
  assert.deepEqual(
    hierarchicalTagResults(tags, '#personal').map(({ tag, depth }) => [tag.name, depth]),
    [['Personal', 0]]
  );
});
