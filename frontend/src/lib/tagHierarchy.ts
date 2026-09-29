import type { Tag } from './api/types';

export interface HierarchicalTagResult {
  tag: Tag;
  depth: number;
}

function normalized(value: string): string {
  return value.trim().toLowerCase();
}

function sortByName(tags: Tag[]): Tag[] {
  return [...tags].sort((left, right) => left.name.localeCompare(right.name));
}

export function tagHierarchyPaths(tag: Tag, tags: Tag[]): string[] {
  const byId = new Map(tags.map((item) => [item.id, item]));

  function paths(current: Tag, seen: Set<number>): string[][] {
    if (seen.has(current.id)) return [[current.name]];
    const nextSeen = new Set(seen).add(current.id);
    if (!current.parents.length) return [[current.name]];

    return current.parents.flatMap((parent) => {
      const fullParent = byId.get(parent.id);
      if (!fullParent) return [[parent.name, current.name]];
      return paths(fullParent, nextSeen).map((path) => [...path, current.name]);
    });
  }

  return [...new Set(paths(tag, new Set()).map((path) => path.join(' › ')))].sort();
}

export function hierarchicalTagResults(tags: Tag[], search: string): HierarchicalTagResult[] {
  const byId = new Map(tags.map((tag) => [tag.id, tag]));
  const children = new Map<number, Tag[]>();

  for (const tag of tags) {
    for (const parent of tag.parents) {
      if (!byId.has(parent.id)) continue;
      children.set(parent.id, [...(children.get(parent.id) || []), tag]);
    }
  }
  for (const [parentId, items] of children) children.set(parentId, sortByName(items));

  const needle = normalized(search).replace(/^#/, '');
  let roots: Tag[];

  if (needle) {
    const matches = tags.filter((tag) => normalized(tag.name).includes(needle));
    const matchedIds = new Set(matches.map((tag) => tag.id));
    roots = matches.filter((tag) => !tag.ancestors.some((ancestor) => matchedIds.has(ancestor.id)));
    roots.sort((left, right) => {
      const leftExact = normalized(left.name) === needle ? 0 : 1;
      const rightExact = normalized(right.name) === needle ? 0 : 1;
      return leftExact - rightExact || left.name.localeCompare(right.name);
    });

    if (!roots.length) {
      return sortByName(
        tags.filter((tag) =>
          tagHierarchyPaths(tag, tags).some((path) => normalized(path).includes(needle))
        )
      ).map((tag) => ({ tag, depth: 0 }));
    }
  } else {
    roots = sortByName(
      tags.filter((tag) => !tag.parents.some((parent) => byId.has(parent.id)))
    );
  }

  const results: HierarchicalTagResult[] = [];
  const seen = new Set<number>();

  function append(tag: Tag, depth: number) {
    if (seen.has(tag.id)) return;
    seen.add(tag.id);
    results.push({ tag, depth });
    for (const child of children.get(tag.id) || []) append(child, depth + 1);
  }

  for (const root of roots) append(root, 0);
  return results;
}


export interface TagHierarchyRow {
  tag: Tag;
  depth: number;
  path: string;
  key: string;
  ancestorIds: number[];
  hasChildren: boolean;
}

export function tagHierarchyRows(tags: Tag[], search = ''): TagHierarchyRow[] {
  const byId = new Map(tags.map((tag) => [tag.id, tag]));
  const children = new Map<number, Tag[]>();

  for (const tag of tags) {
    for (const parent of tag.parents) {
      if (!byId.has(parent.id)) continue;
      children.set(parent.id, [...(children.get(parent.id) || []), tag]);
    }
  }
  for (const [parentId, items] of children) children.set(parentId, sortByName(items));

  const roots = sortByName(
    tags.filter((tag) => !tag.parents.some((parent) => byId.has(parent.id)))
  );
  const rows: TagHierarchyRow[] = [];

  function append(tag: Tag, ancestorIds: number[], pathNames: string[]) {
    if (ancestorIds.includes(tag.id)) return;
    const nextPathNames = [...pathNames, tag.name];
    const childTags = children.get(tag.id) || [];
    rows.push({
      tag,
      depth: ancestorIds.length,
      path: nextPathNames.join(' › '),
      key: [...ancestorIds, tag.id].join('-'),
      ancestorIds,
      hasChildren: childTags.length > 0
    });

    for (const child of childTags) {
      append(child, [...ancestorIds, tag.id], nextPathNames);
    }
  }

  for (const root of roots) append(root, [], []);

  const needle = normalized(search).replace(/^#/, '');
  if (!needle) return rows;
  return rows.filter(
    (row) =>
      normalized(row.tag.name).includes(needle) ||
      normalized(row.path).includes(needle)
  );
}
