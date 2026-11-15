import { StateField, type EditorState } from '@codemirror/state';
import { syntaxTree } from '@codemirror/language';
import { Decoration, EditorView, WidgetType, type DecorationSet } from '@codemirror/view';
import { isolateHistory } from '@codemirror/commands';
import { checklistOffsets, editChecklist, parsedHighlights, parsedInlineMath, parsedReferences, renderMarkdown } from './markdown';
import { markdownSource, sourceOffsets } from './markdownDocument';
import { resolveReference, type ReferenceKey } from './referenceResolver';
import { renderVisibleDiagrams } from './markdownDiagrams';
import { renderVisibleMath } from './markdownMath';

function resolveWidgetReferences(node: HTMLElement, rendered: ReturnType<typeof renderMarkdown>, navigate?: (target: ReferenceKey) => void) {
  for (const anchor of node.querySelectorAll<HTMLAnchorElement>('a[data-markdown-reference]')) {
    const reference = rendered.references.get(anchor.dataset.markdownReference || '');
    if (!reference) continue;
    void resolveReference(reference).then(result => {
      if (!anchor.isConnected || !result?.label) return;
      anchor.textContent = reference.alias || result.label;
      anchor.href = result.kind === 'task' ? `#/tasks?task=${result.id}` : `#/tags?tag=${result.id}`;
      anchor.removeAttribute('aria-disabled');
    });
    anchor.addEventListener('click', event => {
      event.preventDefault();
      if (anchor.getAttribute('aria-disabled') !== 'true') navigate?.(reference);
    });
  }
}

class TaskCheckbox extends WidgetType {
  constructor(private from: number, private checked: boolean, private label: string, private disabled: boolean) { super(); }
  eq(other: TaskCheckbox) { return this.from === other.from && this.checked === other.checked && this.label === other.label && this.disabled === other.disabled; }
  toDOM(view: EditorView) {
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.dataset.taskOffset = String(this.from);
    input.checked = this.checked;
    input.disabled = this.disabled;
    input.setAttribute('aria-label', this.label);
    input.addEventListener('change', () => {
      if (view.state.readOnly || view.state.doc.sliceString(this.from, this.from + 3).toLowerCase() !== (this.checked ? '[x]' : '[ ]')) return;
      const focused = document.activeElement === input;
      view.dispatch({ changes: { from: this.from + 1, to: this.from + 2, insert: input.checked ? 'x' : ' ' }, annotations: isolateHistory.of('full') });
      if (focused) requestAnimationFrame(() => view.dom.querySelector<HTMLInputElement>(`input[data-task-offset="${this.from}"]`)?.focus());
    });
    return input;
  }
  ignoreEvent() { return true; }
}

class TableWidget extends WidgetType {
  constructor(private html: string, private from: number, private to: number, private rendered: ReturnType<typeof renderMarkdown>, private navigate?: (target: ReferenceKey) => void) { super(); }
  eq(other: TableWidget) { return this.html === other.html && this.from === other.from && this.to === other.to; }
  toDOM(view: EditorView) {
    const node = document.createElement('div');
    node.className = 'markdown cm-md-table';
    node.innerHTML = this.html;
    resolveWidgetReferences(node, this.rendered, this.navigate);
    node.addEventListener('click', event => {
      const anchor = event.target instanceof Element ? event.target.closest('a') : null;
      if (anchor?.getAttribute('href')?.startsWith(`#${this.rendered.footnotePrefix}`)) {
        event.preventDefault();
        view.dispatch({selection: {anchor: this.from}});
        view.focus();
        return;
      }
      if (!(event.target instanceof Element) || event.target.closest('a, input, button, summary')) return;
      if (!window.getSelection()?.isCollapsed) return;
      const row = event.target.closest('tr');
      const cell = event.target.closest('td, th');
      const rows = [...node.querySelectorAll('tr')];
      const rowIndex = row ? rows.indexOf(row) : 0;
      const firstLine = view.state.doc.lineAt(this.from).number;
      const lastLine = view.state.doc.lineAt(this.to).number;
      const line = view.state.doc.line(Math.min(lastLine, firstLine + (rowIndex > 0 ? rowIndex + 1 : 0)));
      const cellIndex = row && cell ? [...row.children].indexOf(cell) : 0;
      const pipes = [...line.text.matchAll(/\|/g)].map(match => match.index!);
      const leading = line.text.trimStart().startsWith('|');
      const start = leading ? (pipes[cellIndex] ?? 0) + 1 : cellIndex ? (pipes[cellIndex - 1] ?? 0) + 1 : 0;
      const end = pipes[cellIndex + (leading ? 1 : 0)] ?? line.length;
      const bounds = cell?.getBoundingClientRect();
      const fraction = bounds?.width ? Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)) : 0;
      const position = line.from + Math.min(line.length, start + Math.round(Math.max(0, end - start) * fraction));
      view.dispatch({selection: {anchor: position}});
      view.focus();
    });
    return node;
  }
}

class ReferenceWidget extends WidgetType {
  constructor(private from: number, private reference: ReferenceKey & {raw: string; alias: string | null}, private unavailable: string, private navigate?: (target: ReferenceKey) => void) { super(); }
  eq(other: ReferenceWidget) { return this.from === other.from && this.reference.raw === other.reference.raw && this.unavailable === other.unavailable; }
  toDOM(view: EditorView) {
    const anchor = document.createElement('a');
    anchor.className = 'cm-md-link';
    anchor.textContent = this.reference.alias || this.reference.raw;
    anchor.setAttribute('aria-disabled', 'true');
    anchor.addEventListener('click', event => {
      event.preventDefault();
      if (anchor.getAttribute('aria-disabled') !== 'true') this.navigate?.(this.reference);
    });
    void resolveReference(this.reference).then(result => {
      if (!anchor.isConnected || view.state.doc.sliceString(this.from, this.from + this.reference.raw.length) !== this.reference.raw) return;
      if (!result?.label) { anchor.textContent = this.reference.alias || this.unavailable; return; }
      anchor.textContent = this.reference.alias || result.label;
      anchor.href = result.kind === 'task' ? `#/tasks?task=${result.id}` : `#/tags?tag=${result.id}`;
      anchor.removeAttribute('aria-disabled');
    });
    return anchor;
  }
  ignoreEvent() { return true; }
}

class MathWidget extends WidgetType {
  private stop = () => {};
  constructor(private from: number, private math: {raw: string; source: string; display: boolean}) { super(); }
  eq(other: MathWidget) { return this.from === other.from && this.math.raw === other.math.raw; }
  toDOM(view: EditorView) {
    const wrapper = document.createElement('span');
    const content = document.createElement('span');
    content.dataset.markdownMath = 'math';
    content.textContent = this.math.raw;
    wrapper.append(content);
    this.stop = renderVisibleMath(wrapper, new Map([['math', this.math]]));
    wrapper.addEventListener('click', event => {
      if (!window.getSelection()?.isCollapsed) return;
      const rect = wrapper.getBoundingClientRect();
      const fraction = rect.width ? Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width)) : 0;
      view.dispatch({selection: {anchor: this.from + Math.round(this.math.raw.length * fraction)}});
      view.focus();
    });
    return wrapper;
  }
  destroy() { this.stop(); }
}

class InlineLinkWidget extends WidgetType {
  constructor(private html: string, private from: number, private to: number) { super(); }
  eq(other: InlineLinkWidget) { return this.html === other.html && this.from === other.from && this.to === other.to; }
  toDOM(view: EditorView) {
    const node = document.createElement('span');
    node.className = 'markdown cm-md-inline';
    node.innerHTML = this.html;
    node.addEventListener('click', event => {
      if (event.target instanceof Element && event.target.closest('a[href]')) return;
      if (!window.getSelection()?.isCollapsed) return;
      view.dispatch({selection: {anchor: this.from}});
      view.focus();
    });
    return node;
  }
  ignoreEvent() { return true; }
}

class RenderedBlockWidget extends WidgetType {
  private stop = () => {};
  constructor(private html: string, private from: number, private to: number, private source: string, private rendered: ReturnType<typeof renderMarkdown>, private disclosures: Map<string, boolean>, private navigate?: (target: ReferenceKey) => void) { super(); }
  eq(other: RenderedBlockWidget) { return this.html === other.html && this.from === other.from && this.to === other.to; }
  toDOM(view: EditorView) {
    const node = document.createElement('div');
    node.className = 'markdown cm-md-block';
    node.innerHTML = this.html;
    [...node.querySelectorAll<HTMLDetailsElement>('details.callout')].forEach((details, index) => {
      const key = `${this.from}:${index}`;
      if (this.disclosures.has(key)) details.open = this.disclosures.get(key)!;
      details.addEventListener('toggle', () => this.disclosures.set(key, details.open));
    });
    const stopDiagram = renderVisibleDiagrams(node, this.rendered.diagrams);
    const stopMath = renderVisibleMath(node, this.rendered.maths);
    this.stop = () => {stopDiagram(); stopMath();};
    resolveWidgetReferences(node, this.rendered, this.navigate);
    node.addEventListener('change', event => {
      const input = event.target;
      if (!(input instanceof HTMLInputElement) || input.type !== 'checkbox' || view.state.readOnly) return;
      const offset = this.rendered.controls.get(input.dataset.markdownControl || '');
      if (offset === undefined) return;
      const source = view.state.field(markdownSource);
      const checked = input.checked;
      input.checked = this.source[offset] !== ' ';
      const next = editChecklist(source, this.source, offset, checked);
      const position = sourceOffsets(source).indexOf(offset);
      if (next !== null && next !== source && position >= 0) view.dispatch({changes: {from: position, to: position + 1, insert: next[offset]}, annotations: isolateHistory.of('full')});
    });
    node.addEventListener('click', event => {
      const anchor = event.target instanceof Element ? event.target.closest('a') : null;
      if (anchor?.getAttribute('href')?.startsWith(`#${this.rendered.footnotePrefix}`)) {
        event.preventDefault();
        view.dispatch({selection: {anchor: this.from}});
        view.focus();
        return;
      }
      if (!(event.target instanceof Element) || event.target.closest('a, input, button, summary')) return;
      if (!window.getSelection()?.isCollapsed) return;
      const bounds = node.getBoundingClientRect();
      const fraction = bounds.height ? Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)) : 0;
      view.dispatch({selection: {anchor: this.from + Math.round((this.to - this.from) * fraction)}});
      view.focus();
    });
    return node;
  }
  destroy() { this.stop(); }
}

export function liveMarkdownPreview(checkboxLabel: string, unavailable: string, navigate?: (target: ReferenceKey) => void) {
  let cachedSource: string | null = null;
  let tables: {from: number; to: number; html: string}[] = [];
  let rendered: ReturnType<typeof renderMarkdown> | null = null;
  let blockReadOnly = false;
  let validOffsets = new Set<number>();
  let references: ReturnType<typeof parsedReferences> = [];
  let matches: RegExpMatchArray[] = [];
  let highlights: {from: number; to: number}[] = [];
  let maths: {from: number; math: ReturnType<typeof parsedInlineMath>[number]}[] = [];
  const disclosures = new Map<string, boolean>();
  function decorations(state: EditorState) {
    const ranges: ReturnType<Decoration['range']>[] = [];
    const source = state.field(markdownSource);
    const offsets = sourceOffsets(source);
    if (source !== cachedSource || state.readOnly !== blockReadOnly) {
      cachedSource = source;
      blockReadOnly = state.readOnly;
      validOffsets = new Set(checklistOffsets(source).values());
      rendered = /\||\[!|mermaid|\${1,2}[\r\n]|\]/.test(source) ? renderMarkdown(source, !state.readOnly, checkboxLabel) : null;
      tables = rendered ? [...rendered.tables.values()] : [];
      references = source.includes('[[') ? parsedReferences(source) : [];
      const text = state.doc.toString();
      matches = [...text.matchAll(/\[\[(?:task|tag):[1-9]\d{0,15}(?:\|[^\]\n]*)?\]\]/g)].filter(match => {
        let escapes = 0;
        for (let pos = match.index - 1; pos >= 0 && text[pos] === '\\'; pos--) escapes++;
        if (escapes % 2) return false;
        let node = syntaxTree(state).resolveInner(match.index, 1);
        while (node) {
          if (['FencedCode', 'CodeBlock', 'InlineCode', 'HTMLBlock', 'HTMLTag'].includes(node.name)) return false;
          if (!node.parent) break;
          node = node.parent;
        }
        return true;
      });
      const highlightMatches = [...text.matchAll(/==(?=\S)([\s\S]*?\S)==/g)].filter(match => {
        let escapes = 0;
        for (let pos = match.index - 1; pos >= 0 && text[pos] === '\\'; pos--) escapes++;
        if (escapes % 2) return false;
        let node = syntaxTree(state).resolveInner(match.index, 1);
        while (node) {
          if (['FencedCode', 'CodeBlock', 'InlineCode', 'HTMLBlock', 'HTMLTag'].includes(node.name)) return false;
          if (!node.parent) break;
          node = node.parent;
        }
        return true;
      });
      const parsed = source.includes('==') ? parsedHighlights(source) : [];
      highlights = parsed.length === highlightMatches.length && parsed.every((raw, index) => raw === highlightMatches[index][0])
        ? highlightMatches.map(match => ({from: match.index!, to: match.index! + match[0].length})) : [];
      const mathMatches = [...text.matchAll(/(\${1,2})(?!\$)((?:\\.|[^\\\n$])*?(?:\\.|[^\\\n$]))\1(?=[\s?!.,:]|$)/g)].filter(match => {
        if (matches.some(reference => match.index >= reference.index! && match.index < reference.index! + reference[0].length)) return false;
        let escapes = 0;
        for (let pos = match.index - 1; pos >= 0 && text[pos] === '\\'; pos--) escapes++;
        if (escapes % 2) return false;
        let node = syntaxTree(state).resolveInner(match.index, 1);
        while (node) {
          if (['FencedCode', 'CodeBlock', 'InlineCode', 'HTMLBlock', 'HTMLTag', 'URL'].includes(node.name)) return false;
          if (!node.parent) break;
          node = node.parent;
        }
        return true;
      });
      const parsedMaths = source.includes('$') ? parsedInlineMath(source) : [];
      maths = parsedMaths.length === mathMatches.length && parsedMaths.every((math, index) => math.raw === mathMatches[index][0])
        ? parsedMaths.map((math, index) => ({from: mathMatches[index].index!, math})) : [];
    }
    const selected = (from: number, to: number) => state.selection.ranges.some(range => range.from <= to && range.to >= from);
    const blocks = tables.map(table => ({...table, from: offsets.indexOf(table.from), to: offsets.indexOf(table.to)}))
      .filter(table => table.from >= 0 && table.to > table.from && table.html && state.doc.lineAt(table.from).from === table.from && !selected(table.from, table.to));
    const richBlocks = rendered ? [...rendered.callouts.values(), ...rendered.diagramBlocks.values(), ...rendered.mathBlocks.values()]
      .map(block => ({...block, from: offsets.indexOf(block.from), to: offsets.indexOf(block.to)}))
      .filter(block => block.from >= 0 && block.to > block.from && block.html && state.doc.lineAt(block.from).from === block.from && !selected(block.from, block.to)) : [];
    const allBlocks = [...blocks, ...richBlocks].filter(block => ![...blocks, ...richBlocks].some(other => other !== block && other.from <= block.from && other.to >= block.to));
    const candidates = rendered ? [...rendered.inlineLinks.values()]
      .map(link => ({...link, from: offsets.indexOf(link.from), to: offsets.indexOf(link.to)}))
      .filter(link => link.from >= 0 && link.to > link.from && link.html && !selected(link.from, link.to) && !allBlocks.some(block => link.from >= block.from && link.to <= block.to)) : [];
    const inlineLinks = candidates.filter(link => !candidates.some(other => other !== link && other.from <= link.from && other.to >= link.to));
    for (const link of inlineLinks) ranges.push(Decoration.replace({widget: new InlineLinkWidget(link.html, link.from, link.to)}).range(link.from, link.to));
    for (const entry of maths) {
      const to = entry.from + entry.math.raw.length;
      if (!selected(entry.from, to) && ![...allBlocks, ...inlineLinks].some(block => entry.from >= block.from && to <= block.to)) {
        ranges.push(Decoration.replace({widget: new MathWidget(entry.from, entry.math)}).range(entry.from, to));
      }
    }
    for (const highlight of highlights) {
      if (!selected(highlight.from, highlight.to) && ![...allBlocks, ...inlineLinks].some(block => highlight.from >= block.from && highlight.to <= block.to)) {
        ranges.push(Decoration.mark({class: 'cm-md-highlight'}).range(highlight.from, highlight.to));
        ranges.push(Decoration.replace({}).range(highlight.from, highlight.from + 2));
        ranges.push(Decoration.replace({}).range(highlight.to - 2, highlight.to));
      }
    }
    if (references.length === matches.length && references.every((reference, index) => reference.raw === matches[index][0])) {
      references.forEach((reference, index) => {
        const from = matches[index].index ?? -1;
        if (from < 0) return;
        const to = from + reference.raw.length;
        if (!selected(from, to) && ![...allBlocks, ...inlineLinks].some(block => from >= block.from && to <= block.to)) ranges.push(Decoration.replace({widget: new ReferenceWidget(from, reference, unavailable, navigate)}).range(from, to));
      });
    }
    const marks: Record<string, string> = {
      StrongEmphasis: 'cm-md-strong', Emphasis: 'cm-md-emphasis', Strikethrough: 'cm-md-strike',
      InlineCode: 'cm-md-code', Link: 'cm-md-link'
    };
    syntaxTree(state).iterate({ enter(node) {
      if (allBlocks.some(block => node.from === block.from && node.to === block.to)) return false;
      if (inlineLinks.some(link => node.from === link.from && node.to === link.to)) return false;
      if (marks[node.name]) ranges.push(Decoration.mark({class: marks[node.name]}).range(node.from, node.to));
      if (/^ATXHeading[1-6]$/.test(node.name)) ranges.push(Decoration.mark({class: 'cm-md-heading'}).range(node.from, node.to));
      if (['EmphasisMark', 'StrikethroughMark', 'CodeMark', 'HeaderMark'].includes(node.name)) {
        const parent = node.node.parent;
        if (parent && !selected(parent.from, parent.to)) ranges.push(Decoration.replace({}).range(node.from, node.to));
      }
      if (node.name === 'TaskMarker' && validOffsets.has(offsets[node.from + 1])) {
        const parent = node.node.parent;
        if (parent && !selected(parent.from, parent.to)) {
          const checked = state.doc.sliceString(node.from + 1, node.from + 2).toLowerCase() === 'x';
          ranges.push(Decoration.replace({widget: new TaskCheckbox(node.from, checked, checkboxLabel, state.readOnly)}).range(node.from, node.to));
        }
      }
    }});
    for (const block of allBlocks) {
      const widget = blocks.includes(block) ? new TableWidget(block.html, block.from, block.to, rendered!, navigate) : new RenderedBlockWidget(block.html, block.from, block.to, source, rendered!, disclosures, navigate);
      ranges.push(Decoration.replace({widget, block: true}).range(block.from, block.to));
    }
    return Decoration.set(ranges, true);
  }
  return StateField.define<DecorationSet>({
    create: decorations,
    update(value, transaction) {
      const treeChanged = syntaxTree(transaction.startState) !== syntaxTree(transaction.state);
      if (treeChanged) cachedSource = null;
      return transaction.docChanged || transaction.selection || transaction.reconfigured || treeChanged ? decorations(transaction.state) : value;
    },
    provide: field => EditorView.decorations.from(field)
  });
}
