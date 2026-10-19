import type { NextScope } from './api/types';

export function emptyTagScope(): NextScope {
  return { include_tag_ids: [], exclude_tag_ids: [], tag_match: 'all' };
}

function tagIds(value: unknown, validIds?: ReadonlySet<number>): number[] {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((id): id is number =>
    Number.isInteger(id) && id > 0 && (!validIds || validIds.has(id))
  ))].sort((left, right) => left - right);
}

export function cleanTagScope(value: Partial<NextScope> | null, validIds?: ReadonlySet<number>): NextScope {
  const include = tagIds(value?.include_tag_ids, validIds);
  const included = new Set(include);
  return {
    include_tag_ids: include,
    exclude_tag_ids: tagIds(value?.exclude_tag_ids, validIds).filter((id) => !included.has(id)),
    tag_match: value?.tag_match === 'any' ? 'any' : 'all'
  };
}

export function withIncludedTags(scope: NextScope, ids: number[]): NextScope {
  const include = tagIds(ids);
  const added = new Set(include.filter((id) => !scope.include_tag_ids.includes(id)));
  return cleanTagScope({
    ...scope,
    include_tag_ids: include,
    exclude_tag_ids: scope.exclude_tag_ids.filter((id) => !added.has(id))
  });
}

export function withExcludedTags(scope: NextScope, ids: number[]): NextScope {
  const exclude = tagIds(ids);
  const added = new Set(exclude.filter((id) => !scope.exclude_tag_ids.includes(id)));
  return cleanTagScope({
    ...scope,
    include_tag_ids: scope.include_tag_ids.filter((id) => !added.has(id)),
    exclude_tag_ids: exclude
  });
}

export function sameTagScope(left: NextScope, right: NextScope): boolean {
  return JSON.stringify(cleanTagScope(left)) === JSON.stringify(cleanTagScope(right));
}
