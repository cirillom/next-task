import { autocompletion, type CompletionContext } from '@codemirror/autocomplete';
import { syntaxTree } from '@codemirror/language';
import { api } from './api/client';

export async function referenceCompletionSource(context: CompletionContext) {
  const match = context.matchBefore(/\[\[[^\]\n]{0,120}/);
  if (!match) return null;
  let escapes = 0;
  for (let pos = match.from - 1; pos >= 0 && context.state.sliceDoc(pos, pos + 1) === '\\'; pos--) escapes++;
  if (escapes % 2) return null;
  let node = syntaxTree(context.state).resolveInner(match.from, 1);
  while (node) {
    if (['FencedCode', 'CodeBlock', 'InlineCode'].includes(node.name)) return null;
    if (!node.parent) break;
    node = node.parent;
  }
  context.addEventListener('abort', () => {}, {onDocChange: true});
  const stale = () => context.aborted || !!context.view && (
    context.view.state.selection.main.head !== context.pos ||
    context.view.state.sliceDoc(match.from, context.pos) !== match.text
  );
  await new Promise(resolve => setTimeout(resolve, 200));
  if (stale()) return null;
  try {
    const results = await api.references(match.text.slice(2));
    if (stale()) return null;
    return {
      from: match.from,
      filter: false,
      options: results.filter(item => item.label !== null).map(item => ({
        label: `${item.label} #${item.id}`,
        detail: item.kind === 'tag' ? item.paths.join(' / ') : '',
        apply: `[[${item.kind}:${item.id}]]`
      }))
    };
  } catch {
    return null;
  }
}

export const referenceCompletion = autocompletion({override: [referenceCompletionSource]});
