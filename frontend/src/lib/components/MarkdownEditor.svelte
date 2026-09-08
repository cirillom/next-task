<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import DOMPurify from 'dompurify';
  import { marked } from 'marked';

  export let value = '';
  export let disabled = false;
  export let label = 'Description';
  export let placeholder = 'Add details, links, lists, tables, or code…';
  export let compact = false;

  const dispatch = createEventDispatcher<{ input: string }>();
  const CARET_MARKER = '\uE000';

  let editor: HTMLDivElement;
  let focused = false;
  let lastRendered = '';

  function serializeChildren(node: ParentNode): string {
    return Array.from(node.childNodes).map(serializeNode).join('');
  }

  function indent(text: string, spaces = 2): string {
    const prefix = ' '.repeat(spaces);
    return text
      .split('\n')
      .filter((line, index, lines) => line || index < lines.length - 1)
      .map((line) => line ? `${prefix}${line}` : line)
      .join('\n');
  }

  function serializeList(list: Element): string {
    const ordered = list.tagName === 'OL';
    const items = Array.from(list.children).filter((child) => child.tagName === 'LI');
    let output = '';

    items.forEach((item, index) => {
      let body = '';
      let nested = '';
      for (const child of Array.from(item.childNodes)) {
        if (child instanceof Element && (child.tagName === 'UL' || child.tagName === 'OL')) {
          nested += indent(serializeList(child).trimEnd()) + '\n';
        } else {
          body += serializeNode(child);
        }
      }
      const prefix = ordered ? `${index + 1}. ` : '- ';
      output += `${prefix}${body.trim()}\n${nested}`;
    });

    return `${output.trimEnd()}\n\n`;
  }

  function serializeNode(node: Node): string {
    if (node.nodeType === Node.TEXT_NODE) return node.textContent || '';
    if (!(node instanceof HTMLElement)) return '';

    const children = () => serializeChildren(node);
    switch (node.tagName) {
      case 'P':
        return `${children().trimEnd()}\n\n`;
      case 'BR':
        return '\n';
      case 'STRONG':
      case 'B':
        return `**${children()}**`;
      case 'EM':
      case 'I':
        return `*${children()}*`;
      case 'DEL':
      case 'S':
        return `~~${children()}~~`;
      case 'CODE':
        if (node.parentElement?.tagName === 'PRE') return node.textContent || '';
        return `\`${node.textContent || ''}\``;
      case 'PRE': {
        const code = (node.textContent || '').replace(/\n$/, '');
        return `\`\`\`\n${code}\n\`\`\`\n\n`;
      }
      case 'H1':
      case 'H2':
      case 'H3':
      case 'H4':
      case 'H5':
      case 'H6': {
        const level = Number(node.tagName.slice(1));
        return `${'#'.repeat(level)} ${children().trim()}\n\n`;
      }
      case 'UL':
      case 'OL':
        return serializeList(node);
      case 'LI':
        return children();
      case 'BLOCKQUOTE': {
        const quote = children().trim().split('\n').map((line) => `> ${line}`).join('\n');
        return `${quote}\n\n`;
      }
      case 'A': {
        const href = node.getAttribute('href') || '';
        return `[${children()}](${href})`;
      }
      case 'IMG': {
        const src = node.getAttribute('src') || '';
        const alt = node.getAttribute('alt') || '';
        return `![${alt}](${src})`;
      }
      case 'HR':
        return '---\n\n';
      case 'INPUT': {
        const input = node as HTMLInputElement;
        if (input.type === 'checkbox') return `[${input.checked ? 'x' : ' '}] `;
        return '';
      }
      case 'TABLE':
        return `${node.outerHTML}\n\n`;
      case 'DIV':
        return `${children().trimEnd()}\n`;
      default:
        return children();
    }
  }

  function normalizedMarkdown(): string {
    return serializeChildren(editor)
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trimEnd();
  }

  function prepareInteractiveContent() {
    if (!editor) return;
    editor.querySelectorAll<HTMLInputElement>('input[type="checkbox"]').forEach((checkbox) => {
      checkbox.disabled = disabled;
    });
  }

  function markdownHtml(markdown: string): string {
    return markdown
      ? DOMPurify.sanitize(marked.parse(markdown, { gfm: true }) as string)
      : '';
  }

  function renderMarkdown(markdown: string) {
    if (!editor) return;
    editor.innerHTML = markdownHtml(markdown);
    lastRendered = markdown;
    prepareInteractiveContent();
  }

  function insertCaretMarker(): boolean {
    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0) return false;

    const range = selection.getRangeAt(0);
    if (!editor.contains(range.startContainer)) return false;

    range.collapse(false);
    const marker = document.createTextNode(CARET_MARKER);
    range.insertNode(marker);
    return true;
  }

  function restoreCaret() {
    const walker = document.createTreeWalker(editor, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode() as Text | null;

    while (node) {
      const index = node.data.indexOf(CARET_MARKER);
      if (index !== -1) {
        node.data = node.data.replace(CARET_MARKER, '');
        const range = document.createRange();
        const selection = window.getSelection();
        range.setStart(node, index);
        range.collapse(true);
        selection?.removeAllRanges();
        selection?.addRange(range);
        return;
      }
      node = walker.nextNode() as Text | null;
    }

    const range = document.createRange();
    const selection = window.getSelection();
    range.selectNodeContents(editor);
    range.collapse(false);
    selection?.removeAllRanges();
    selection?.addRange(range);
  }

  function rerenderWhileEditing() {
    if (disabled) return;

    const hasCaret = insertCaretMarker();
    const markdownWithMarker = normalizedMarkdown();
    const next = markdownWithMarker.replace(CARET_MARKER, '');

    editor.innerHTML = markdownHtml(markdownWithMarker);
    prepareInteractiveContent();
    if (hasCaret) restoreCaret();

    value = next;
    lastRendered = next;
    dispatch('input', next);
  }

  function handleCheckboxChange(event: Event) {
    if (disabled || !(event.target instanceof HTMLInputElement) || event.target.type !== 'checkbox') return;
    const next = normalizedMarkdown();
    value = next;
    lastRendered = next;
    dispatch('input', next);
  }

  function handleFocus() {
    focused = true;
  }

  function handleBlur() {
    focused = false;
    renderMarkdown(value);
  }

  function handleClick(event: MouseEvent) {
    const target = event.target as HTMLElement;
    if (!disabled && target.closest('a')) event.preventDefault();
  }

  onMount(() => renderMarkdown(value));

  $: if (editor && !focused && value !== lastRendered) renderMarkdown(value);
  $: if (editor) prepareInteractiveContent();
</script>

<div class:compact class="markdown-editor-live">
  {#if label}<span class="field-label">{label}</span>{/if}
  <div
    bind:this={editor}
    class="live-surface"
    class:disabled
    contenteditable={!disabled}
    role="textbox"
    aria-multiline="true"
    aria-label={label || 'Markdown editor'}
    data-placeholder={placeholder}
    spellcheck="true"
    on:focus={handleFocus}
    on:blur={handleBlur}
    on:input={rerenderWhileEditing}
    on:change={handleCheckboxChange}
    on:click={handleClick}
  ></div>
</div>

<style>
  .markdown-editor-live { display: grid; gap: .35rem; }

  .live-surface {
    width: 100%;
    min-height: 15rem;
    max-height: 32rem;
    overflow: auto;
    border: 1px solid #cfcbbf;
    border-radius: .6rem;
    background: #fff;
    padding: .75rem .85rem;
    color: var(--ink);
    line-height: 1.55;
    outline: 0;
  }

  .live-surface:focus {
    border-color: #8ca095;
    box-shadow: 0 0 0 2px rgba(70, 105, 85, .1);
  }

  .live-surface:empty::before {
    content: attr(data-placeholder);
    color: var(--muted);
    pointer-events: none;
  }

  .live-surface.disabled {
    background: #faf8f2;
    color: var(--muted);
  }

  .live-surface :global(p:first-child),
  .live-surface :global(h1:first-child),
  .live-surface :global(h2:first-child),
  .live-surface :global(h3:first-child) { margin-top: 0; }

  .live-surface :global(p:last-child),
  .live-surface :global(ul:last-child),
  .live-surface :global(ol:last-child),
  .live-surface :global(pre:last-child) { margin-bottom: 0; }

  .live-surface :global(h1) { font-size: 1.55rem; }
  .live-surface :global(h2) { font-size: 1.3rem; }
  .live-surface :global(h3) { font-size: 1.12rem; }
  .live-surface :global(h1),
  .live-surface :global(h2),
  .live-surface :global(h3) { margin: 1rem 0 .45rem; line-height: 1.25; }

  .live-surface :global(strong) { font-weight: 800; }
  .live-surface :global(em) { font-style: italic; }
  .live-surface :global(del) { color: var(--muted); }

  .live-surface :global(ul),
  .live-surface :global(ol) { padding-left: 1.4rem; }

  .live-surface :global(li:has(> input[type='checkbox'])) { list-style: none; }
  .live-surface :global(input[type='checkbox']) {
    width: .95rem;
    height: .95rem;
    margin: 0 .45rem 0 -1.3rem;
    vertical-align: -.12rem;
    accent-color: var(--forest);
  }

  .live-surface :global(blockquote) {
    margin-left: 0;
    border-left: 3px solid #c9d3cc;
    padding-left: .8rem;
    color: var(--muted);
  }

  .live-surface :global(code) {
    border-radius: .25rem;
    background: #f0eee7;
    padding: .08rem .25rem;
    font-size: .9em;
  }

  .live-surface :global(pre) {
    overflow: auto;
    border-radius: .45rem;
    background: #f0eee7;
    padding: .7rem;
  }

  .live-surface :global(pre code) { background: transparent; padding: 0; }
  .live-surface :global(a) { color: var(--forest-2); text-decoration: underline; text-underline-offset: .12rem; }

  .compact .live-surface { min-height: 9rem; max-height: 18rem; }

  @media (max-width: 640px) {
    .live-surface,
    .compact .live-surface { min-height: 12rem; max-height: 24rem; }
  }
</style>
