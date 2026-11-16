import { api } from './api/client';
import type { MarkdownReference } from './api/types';

export type ReferenceKey = Pick<MarkdownReference, 'kind' | 'id'>;
export const referenceNavigation = Symbol('markdown-reference-navigation');
const keyOf = (item: ReferenceKey) => `${item.kind}:${item.id}`;
let pending = new Map<string, { item: ReferenceKey; callbacks: ((value: MarkdownReference | null) => void)[] }>();
let scheduled = false;
let generation = 0;

export function resolveReference(item: ReferenceKey): Promise<MarkdownReference | null> {
  return new Promise(resolve => {
    const key = keyOf(item);
    const existing = pending.get(key);
    if (existing) existing.callbacks.push(resolve);
    else pending.set(key, {item, callbacks: [resolve]});
    if (!scheduled) {
      scheduled = true;
      queueMicrotask(() => void flush());
    }
  });
}

async function flush() {
  scheduled = false;
  const batch = pending;
  pending = new Map();
  const requestGeneration = generation;
  const entries = [...batch.values()];
  for (let start = 0; start < entries.length; start += 100) {
    const part = entries.slice(start, start + 100);
    let results: MarkdownReference[] = [];
    try { results = await api.resolveReferences(part.map(entry => entry.item)); } catch { /* Unavailable stays non-navigable. */ }
    const byKey = new Map(results.map(item => [keyOf(item), item]));
    for (const entry of part) {
      const result = requestGeneration === generation ? byKey.get(keyOf(entry.item)) || null : null;
      for (const callback of entry.callbacks) callback(result);
    }
  }
}

export function clearReferenceResolver() {
  generation++;
  for (const entry of pending.values()) for (const callback of entry.callbacks) callback(null);
  pending.clear();
}
