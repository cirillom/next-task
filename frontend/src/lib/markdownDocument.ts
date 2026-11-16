import { StateEffect, StateField, type Extension } from '@codemirror/state';
import { invertedEffects } from '@codemirror/commands';

export function sourceOffsets(source: string): number[] {
  const offsets = [0];
  for (let i = 0; i < source.length;) {
    if (source[i] === '\r' && source[i + 1] === '\n') i += 2;
    else i++;
    offsets.push(i);
  }
  return offsets;
}

export const restoreMarkdownSource = StateEffect.define<string>();
export const markdownSource = StateField.define<string>({
  create: () => '',
  update(source, transaction) {
    for (const effect of transaction.effects) if (effect.is(restoreMarkdownSource)) return effect.value;
    if (!transaction.docChanged) return source;
    const offsets = sourceOffsets(source);
    const changes: { from: number; to: number; insert: string }[] = [];
    transaction.changes.iterChanges((from, to, _fromB, _toB, inserted) => {
      changes.push({ from: offsets[from], to: offsets[to], insert: inserted.toString() });
    });
    for (const change of changes.reverse()) source = source.slice(0, change.from) + change.insert + source.slice(change.to);
    return source;
  }
});

export function markdownSourceState(source: string): Extension {
  return [
    markdownSource.init(() => source),
    invertedEffects.of(transaction => transaction.docChanged
      ? [restoreMarkdownSource.of(transaction.startState.field(markdownSource))]
      : [])
  ];
}
