import type { Tag } from './api/types';

function normalized(value: string): string {
  return value.trim().toLowerCase();
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

export function filterTagsByHierarchy(tags: Tag[], search: string): Tag[] {
  const needle = normalized(search).replace(/^#/, '');
  if (!needle) return tags;

  return tags.filter((tag) => {
    if (normalized(tag.name).includes(needle)) return true;
    return tagHierarchyPaths(tag, tags).some((path) => normalized(path).includes(needle));
  });
}
