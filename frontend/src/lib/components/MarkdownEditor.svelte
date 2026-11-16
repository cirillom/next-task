<script lang="ts">
  import { createEventDispatcher, getContext, onMount } from 'svelte';
  import { Annotation, Compartment, EditorSelection, EditorState, Prec, Transaction } from '@codemirror/state';
  import { EditorView, keymap, placeholder as placeholderExtension } from '@codemirror/view';
  import { defaultKeymap, history, historyKeymap, isolateHistory } from '@codemirror/commands';
  import { markdown, markdownKeymap, markdownLanguage } from '@codemirror/lang-markdown';
  import { syntaxTree } from '@codemirror/language';
  import { t, text } from '../i18n';
  import { markdownSource, markdownSourceState, restoreMarkdownSource, sourceOffsets } from '../markdownDocument';
  import { liveMarkdownPreview } from '../markdownPreview';
  import { referenceCompletion } from '../referenceCompletion';
  import { referenceNavigation, type ReferenceKey } from '../referenceResolver';
  import Markdown from './Markdown.svelte';
  import { closeTopDialog, hasDialog } from '../keyboard';

  export let value = '';
  export let disabled = false;
  export let label = 'ui.markdownEditor.description';
  export let placeholder = 'ui.markdownEditor.addDetailsLinksListsTablesOrCode';
  export let compact = false;
  export let documentId: string | number = 0;
  export let inputId = '';

  const dispatch = createEventDispatcher<{ input: string; selection: { cursor: number; inCode: boolean }; blur: void }>();
  const navigateReference = getContext<(target: ReferenceKey) => void>(referenceNavigation);
  const preview = new Compartment();
  const permissions = new Compartment();
  const attributes = new Compartment();
  const externalChange = Annotation.define<boolean>();
  let root: HTMLDivElement;
  let view: EditorView;
  let activeDocument: string | number = documentId;
  let mode: 'live' | 'source' | 'reading' = 'live';

  function wrap(prefix: string, suffix: string, link = false) {
    return (editor: EditorView) => {
      if (editor.state.readOnly) return false;
      editor.dispatch(editor.state.changeByRange(range => {
        const selected = editor.state.sliceDoc(range.from, range.to);
        const content = link && !selected ? 'text' : selected;
        const insert = prefix + content + suffix;
        const start = link ? range.from + prefix.length + content.length + 2 : range.from + prefix.length;
        const end = link ? start + 3 : start + content.length;
        return { changes: { from: range.from, to: range.to, insert }, range: EditorSelection.range(start, end) };
      }));
      return true;
    };
  }

  function createState(source: string) {
    return EditorState.create({
      doc: source,
      extensions: [
        markdownSourceState(source), history(), EditorState.allowMultipleSelections.of(true), referenceCompletion,
        markdown({base: markdownLanguage, addKeymap: false, completeHTMLTags: false}),
        keymap.of([
          {key: 'Mod-b', run: wrap('**', '**')},
          {key: 'Mod-i', run: wrap('*', '*')},
          {key: 'Mod-k', run: wrap('[', '](url)', true)},
          ...markdownKeymap, ...historyKeymap, ...defaultKeymap.filter(binding => binding.key !== 'Escape' && binding.key !== 'Mod-Enter')
        ]),
        EditorView.lineWrapping,
        preview.of(mode === 'live' ? liveMarkdownPreview($t('ui.markdownEditor.toggleChecklistItem'), $t('ui.markdownEditor.referenceUnavailable'), navigateReference) : []),
        permissions.of([EditorState.readOnly.of(disabled), EditorView.editable.of(!disabled)]),
        attributes.of([EditorView.contentAttributes.of({'aria-label': $text(label) || $t('ui.markdownEditor.markdownEditor'), spellcheck: 'true', ...(inputId ? {id: inputId} : {})}), placeholderExtension($text(placeholder))]),
        Prec.highest(EditorView.domEventHandlers({
          blur: () => {dispatch('blur'); return false;},
          keydown: (event, editor) => {
            if (event.key !== 'Escape' || event.repeat || event.isComposing || !hasDialog() || editor.dom.querySelector('.cm-tooltip-autocomplete')) return false;
            event.preventDefault();
            event.stopPropagation();
            closeTopDialog();
            return true;
          }
        })),
        EditorView.updateListener.of(update => {
          const external = update.transactions.some(transaction => transaction.annotation(externalChange));
          if (update.docChanged && !external) {
            value = update.state.field(markdownSource);
            dispatch('input', value);
          }
          if ((update.docChanged && !external) || update.selectionSet) {
            const head = update.state.selection.main.head;
            let node = syntaxTree(update.state).resolveInner(Math.max(0, head - 1), -1);
            let inCode = false;
            while (node) {
              if (['FencedCode', 'CodeBlock', 'InlineCode'].includes(node.name)) { inCode = true; break; }
              if (!node.parent) break;
              node = node.parent;
            }
            dispatch('selection', {cursor: sourceOffsets(value)[head], inCode});
          }
        })
      ]
    });
  }

  onMount(() => {
    activeDocument = documentId;
    view = new EditorView({parent: root, state: createState(value)});
    return () => view.destroy();
  });

  function changeMode(next: typeof mode) {
    mode = next;
    view.dispatch({effects: preview.reconfigure(next === 'live' ? liveMarkdownPreview($t('ui.markdownEditor.toggleChecklistItem'), $t('ui.markdownEditor.referenceUnavailable'), navigateReference) : [])});
  }

  export function focus() {
    if (mode === 'reading') changeMode('live');
    view?.focus();
  }

  function toggleChecklist(next: string) {
    if (!view || disabled || next.length !== value.length) return;
    let offset = 0;
    while (offset < value.length && value[offset] === next[offset]) offset++;
    const position = sourceOffsets(value).indexOf(offset);
    if (position < 0 || value.slice(offset + 1) !== next.slice(offset + 1)) return;
    view.dispatch({changes: {from: position, to: position + 1, insert: next[offset]}, annotations: isolateHistory.of('full')});
  }

  $: if (view && documentId !== activeDocument) {
    activeDocument = documentId;
    view.setState(createState(value));
  } else if (view && value !== view.state.field(markdownSource)) {
    view.dispatch({
      changes: {from: 0, to: view.state.doc.length, insert: value},
      effects: restoreMarkdownSource.of(value),
      annotations: [Transaction.addToHistory.of(false), externalChange.of(true)]
    });
  }
  $: if (view) view.dispatch({effects: [
    permissions.reconfigure([EditorState.readOnly.of(disabled), EditorView.editable.of(!disabled)]),
    attributes.reconfigure([EditorView.contentAttributes.of({'aria-label': $text(label) || $t('ui.markdownEditor.markdownEditor'), spellcheck: 'true', ...(inputId ? {id: inputId} : {})}), placeholderExtension($text(placeholder))])
  ]});
</script>

<div class="markdown-editor-live" class:compact>
  <div class="editor-heading">
    {#if label}<span class="field-label">{$text(label)}</span>{/if}
    <div class="modes" role="group" aria-label={$t('ui.markdownEditor.viewMode')}>
      <button type="button" aria-pressed={mode === 'live'} on:click={() => changeMode('live')}>{$t('ui.markdownEditor.livePreview')}</button>
      <button type="button" aria-pressed={mode === 'source'} on:click={() => changeMode('source')}>{$t('ui.markdownEditor.source')}</button>
      <button type="button" aria-pressed={mode === 'reading'} on:click={() => changeMode('reading')}>{$t('ui.markdownEditor.reading')}</button>
    </div>
  </div>
  <div bind:this={root} class="editor-surface" hidden={mode === 'reading'}></div>
  {#if mode === 'reading'}
    <div class="reading-surface"><Markdown source={value} editable={!disabled} {disabled} on:input={(event) => toggleChecklist(event.detail)} /></div>
  {/if}
</div>

<style>
  .markdown-editor-live { display: grid; gap: .35rem; }
  .editor-heading { display: flex; min-height: 1.6rem; align-items: center; justify-content: space-between; gap: .75rem; flex-wrap: wrap; }
  .modes { display: flex; gap: .2rem; }
  .modes button { border: 0; border-radius: .3rem; background: transparent; color: var(--forest-2); padding: .2rem .35rem; font-size: .72rem; font-weight: 750; }
  .modes button[aria-pressed='true'] { background: #e4ece5; }
  .editor-surface, .reading-surface { width: 100%; min-height: 15rem; max-height: 32rem; overflow: auto; border: 1px solid #cfcbbf; border-radius: .6rem; background: #fff; color: var(--ink); line-height: 1.55; }
  .editor-surface:focus-within { border-color: #8ca095; box-shadow: 0 0 0 2px rgba(70, 105, 85, .1); }
  .editor-surface :global(.cm-editor) { min-height: inherit; font: inherit; }
  .editor-surface :global(.cm-scroller) { font: inherit; }
  .editor-surface :global(.cm-content) { padding: .7rem .8rem; }
  .editor-surface :global(.cm-focused) { outline: 0; }
  .editor-surface :global(.cm-md-strong) { font-weight: 800; }
  .editor-surface :global(.cm-md-emphasis) { font-style: italic; }
  .editor-surface :global(.cm-md-strike) { text-decoration: line-through; }
  .editor-surface :global(.cm-md-code) { background: #f0eee7; font-family: monospace; }
  .editor-surface :global(.cm-md-highlight) { background: #fff0a8; }
  .editor-surface :global(.cm-md-heading) { font-weight: 800; font-size: 1.2em; }
  .editor-surface :global(.cm-md-link) { color: var(--forest-2); text-decoration: underline; }
  .editor-surface :global(.cm-md-table) { overflow: auto; padding: .35rem .8rem; }
  .editor-surface :global(.cm-md-block) { overflow: auto; padding: .25rem .8rem; }
  .editor-surface :global(input[type='checkbox']) { width: .95rem; height: .95rem; padding: 0; margin: 0 .35rem 0 0; vertical-align: -.12rem; accent-color: var(--forest); }
  .reading-surface { padding: .7rem .8rem; }
  .compact .editor-surface, .compact .reading-surface { min-height: 9rem; max-height: 18rem; }
  @media (max-width: 640px) { .editor-surface, .reading-surface, .compact .editor-surface, .compact .reading-surface { min-height: 12rem; max-height: 24rem; } }
</style>
