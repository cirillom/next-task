<script lang="ts">
  import { createEventDispatcher, tick } from 'svelte';
  import DOMPurify from 'dompurify';
  import { marked } from 'marked';

  export let value = '';
  export let disabled = false;
  export let label = 'Description';
  export let placeholder = 'Add details, links, lists, tables, or code…';
  export let compact = false;

  const dispatch = createEventDispatcher<{ input: string }>();

  let root: HTMLDivElement;
  let activeTextarea: HTMLTextAreaElement;
  let activeLine: number | null = null;
  let lines = splitLines(value);
  let internalValue = value;

  function splitLines(markdown: string): string[] {
    const next = markdown.split('\n');
    return next.length ? next : [''];
  }

  function escapeHtml(text: string): string {
    return text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  function inlineMarkdown(source: string): string {
    return DOMPurify.sanitize(marked.parseInline(source, { gfm: true }) as string);
  }

  function indentationWidth(indent: string): number {
    return indent.replace(/\t/g, '    ').length;
  }

  function fenceMarker(line: string): RegExpMatchArray | null {
    return line.match(/^\s*(`{3,}|~{3,})/);
  }

  function insideFence(index: number): boolean {
    let fenceCharacter = '';
    for (let lineIndex = 0; lineIndex < index; lineIndex += 1) {
      const marker = fenceMarker(lines[lineIndex] || '');
      if (!marker) continue;
      const character = marker[1][0];
      if (!fenceCharacter) fenceCharacter = character;
      else if (fenceCharacter === character) fenceCharacter = '';
    }
    return !!fenceCharacter;
  }

  function renderedLineHtml(line: string, index: number): string {
    if (!line) return '<div class="md-blank">&nbsp;</div>';

    const marker = fenceMarker(line);
    if (marker) {
      const language = line.slice(line.indexOf(marker[1]) + marker[1].length).trim();
      return `<div class="md-code-fence">${language ? escapeHtml(language) : '&nbsp;'}</div>`;
    }

    if (insideFence(index)) return `<div class="md-code-line">${escapeHtml(line) || '&nbsp;'}</div>`;

    const heading = line.match(/^\s*(#{1,6})\s+(.+)$/);
    if (heading) {
      const level = heading[1].length;
      return `<h${level}>${inlineMarkdown(heading[2])}</h${level}>`;
    }

    if (/^\s{0,3}((\*\s*){3,}|(-\s*){3,}|(_\s*){3,})$/.test(line)) {
      return '<hr />';
    }

    const task = line.match(/^(\s*)[-*+]\s+\[([ xX])\]\s+(.*)$/);
    if (task) {
      const offset = Math.min(indentationWidth(task[1]) * .45, 4.5);
      const checked = task[2].toLowerCase() === 'x';
      return `<div class="md-list-line md-task-line" style="--line-indent:${offset}rem"><input type="checkbox" ${checked ? 'checked' : ''} disabled /><span>${inlineMarkdown(task[3])}</span></div>`;
    }

    const bullet = line.match(/^(\s*)[-*+]\s+(.*)$/);
    if (bullet) {
      const offset = Math.min(indentationWidth(bullet[1]) * .45, 4.5);
      return `<div class="md-list-line" style="--line-indent:${offset}rem"><span class="md-marker">•</span><span>${inlineMarkdown(bullet[2])}</span></div>`;
    }

    const ordered = line.match(/^(\s*)(\d+)[.)]\s+(.*)$/);
    if (ordered) {
      const offset = Math.min(indentationWidth(ordered[1]) * .45, 4.5);
      return `<div class="md-list-line" style="--line-indent:${offset}rem"><span class="md-marker md-number">${ordered[2]}.</span><span>${inlineMarkdown(ordered[3])}</span></div>`;
    }

    const quote = line.match(/^\s*>\s?(.*)$/);
    if (quote) return `<blockquote>${inlineMarkdown(quote[1])}</blockquote>`;

    return `<div class="md-paragraph">${inlineMarkdown(line)}</div>`;
  }

  function emitLines(nextLines: string[]) {
    lines = nextLines.length ? nextLines : [''];
    const next = lines.join('\n');
    internalValue = next;
    value = next;
    dispatch('input', next);
  }

  function resizeActiveTextarea() {
    if (!activeTextarea) return;
    activeTextarea.style.height = 'auto';
    activeTextarea.style.height = `${Math.max(activeTextarea.scrollHeight, 26)}px`;
  }

  async function activateLine(index: number, column?: number) {
    if (disabled) return;
    activeLine = Math.max(0, Math.min(index, lines.length - 1));
    await tick();
    if (!activeTextarea) return;
    resizeActiveTextarea();
    activeTextarea.focus();
    const position = Math.min(column ?? lines[activeLine].length, lines[activeLine].length);
    activeTextarea.setSelectionRange(position, position);
  }

  function updateLine(index: number, text: string) {
    const next = [...lines];
    next[index] = text;
    emitLines(next);
  }

  async function handleLineInput(index: number, event: Event) {
    const textarea = event.currentTarget as HTMLTextAreaElement;
    const text = textarea.value;

    if (!text.includes('\n')) {
      updateLine(index, text);
      await tick();
      resizeActiveTextarea();
      return;
    }

    const cursor = textarea.selectionStart;
    const beforeCursor = text.slice(0, cursor).split('\n');
    const replacement = text.split('\n');
    const next = [...lines];
    next.splice(index, 1, ...replacement);
    emitLines(next);

    const nextIndex = index + beforeCursor.length - 1;
    const nextColumn = beforeCursor[beforeCursor.length - 1].length;
    await activateLine(nextIndex, nextColumn);
  }

  function continuationPrefix(line: string): string {
    const task = line.match(/^(\s*[-*+]\s+)\[[ xX]\]\s+/);
    if (task) return `${task[1]}[ ] `;

    const bullet = line.match(/^(\s*[-*+]\s+)/);
    if (bullet) return bullet[1];

    const ordered = line.match(/^(\s*)(\d+)([.)]\s+)/);
    if (ordered) return `${ordered[1]}${Number(ordered[2]) + 1}${ordered[3]}`;

    const quote = line.match(/^(\s*>\s?)/);
    return quote?.[1] || '';
  }

  async function handleLineKeydown(index: number, event: KeyboardEvent) {
    const textarea = event.currentTarget as HTMLTextAreaElement;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const line = lines[index] || '';

    if (event.key === 'Enter') {
      event.preventDefault();
      const prefix = continuationPrefix(line.slice(0, start));
      const before = line.slice(0, start);
      const after = line.slice(end);
      const next = [...lines];
      next.splice(index, 1, before, `${prefix}${after}`);
      emitLines(next);
      await activateLine(index + 1, prefix.length);
      return;
    }

    if (event.key === 'Backspace' && start === 0 && end === 0 && index > 0) {
      event.preventDefault();
      const previous = lines[index - 1];
      const next = [...lines];
      next.splice(index - 1, 2, `${previous}${line}`);
      emitLines(next);
      await activateLine(index - 1, previous.length);
      return;
    }

    if (event.key === 'Delete' && start === line.length && end === line.length && index < lines.length - 1) {
      event.preventDefault();
      const next = [...lines];
      next.splice(index, 2, `${line}${lines[index + 1]}`);
      emitLines(next);
      await activateLine(index, start);
      return;
    }

    if (event.key === 'ArrowUp' && !event.shiftKey && index > 0) {
      event.preventDefault();
      await activateLine(index - 1, start);
      return;
    }

    if (event.key === 'ArrowDown' && !event.shiftKey && index < lines.length - 1) {
      event.preventDefault();
      await activateLine(index + 1, start);
    }
  }

  function handleSurfaceMouseDown(event: MouseEvent) {
    if (disabled || event.target !== root) return;
    event.preventDefault();
    void activateLine(lines.length - 1);
  }

  function handleActiveBlur() {
    window.setTimeout(() => {
      if (!root?.contains(document.activeElement)) activeLine = null;
    }, 0);
  }

  $: if (activeLine === null && value !== internalValue) {
    internalValue = value;
    lines = splitLines(value);
  }
</script>

<div class:compact class="markdown-editor-live">
  {#if label}<span class="field-label">{label}</span>{/if}
  <div
    bind:this={root}
    class="live-surface"
    class:disabled
    class:empty={lines.length === 1 && !lines[0]}
    role="textbox"
    aria-multiline="true"
    aria-label={label || 'Markdown editor'}
    data-placeholder={placeholder}
    on:mousedown={handleSurfaceMouseDown}
  >
    {#each lines as line, index (index)}
      {#if activeLine === index && !disabled}
        <textarea
          bind:this={activeTextarea}
          class="source-line"
          rows="1"
          value={line}
          spellcheck="true"
          aria-label={`Markdown source line ${index + 1}`}
          on:input={(event) => void handleLineInput(index, event)}
          on:keydown={(event) => void handleLineKeydown(index, event)}
          on:blur={handleActiveBlur}
        ></textarea>
      {:else}
        <div
          class="rendered-line"
          class:interactive={!disabled}
          role={!disabled ? 'button' : undefined}
          tabindex={!disabled ? 0 : undefined}
          on:mousedown|preventDefault={() => void activateLine(index)}
          on:keydown={(event) => {
            if (!disabled && (event.key === 'Enter' || event.key === ' ')) {
              event.preventDefault();
              void activateLine(index);
            }
          }}
        >{@html renderedLineHtml(line, index)}</div>
      {/if}
    {/each}
  </div>
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
    padding: .7rem .8rem;
    color: var(--ink);
    line-height: 1.55;
    outline: 0;
  }

  .live-surface:focus-within {
    border-color: #8ca095;
    box-shadow: 0 0 0 2px rgba(70, 105, 85, .1);
  }

  .live-surface.empty:not(:focus-within)::before {
    content: attr(data-placeholder);
    display: block;
    color: var(--muted);
    pointer-events: none;
  }

  .live-surface.disabled {
    background: #faf8f2;
    color: var(--muted);
  }

  .rendered-line {
    min-height: 1.55em;
    border-radius: .3rem;
    padding: .06rem .2rem;
  }

  .rendered-line.interactive { cursor: text; }
  .rendered-line.interactive:hover { background: rgba(66, 91, 76, .045); }
  .rendered-line:focus-visible { outline: 1px solid #9bada2; outline-offset: 1px; }

  .source-line {
    display: block;
    width: 100%;
    min-height: 1.7rem;
    overflow: hidden;
    resize: none;
    border: 0;
    border-radius: .3rem;
    background: #f4f6f3;
    color: var(--ink);
    padding: .14rem .28rem;
    box-shadow: inset 2px 0 0 #8ca095;
    font: inherit;
    line-height: 1.55;
    outline: 0;
  }

  .rendered-line :global(.md-blank) { min-height: .85rem; }
  .rendered-line :global(.md-paragraph) { min-height: 1.55em; }

  .rendered-line :global(h1),
  .rendered-line :global(h2),
  .rendered-line :global(h3),
  .rendered-line :global(h4),
  .rendered-line :global(h5),
  .rendered-line :global(h6) {
    margin: .1rem 0;
    line-height: 1.3;
  }

  .rendered-line :global(h1) { font-size: 1.55rem; }
  .rendered-line :global(h2) { font-size: 1.3rem; }
  .rendered-line :global(h3) { font-size: 1.12rem; }
  .rendered-line :global(h4),
  .rendered-line :global(h5),
  .rendered-line :global(h6) { font-size: 1rem; }

  .rendered-line :global(strong) { font-weight: 800; }
  .rendered-line :global(em) { font-style: italic; }
  .rendered-line :global(del) { color: var(--muted); }

  .rendered-line :global(.md-list-line) {
    display: grid;
    grid-template-columns: 1.2rem minmax(0, 1fr);
    gap: .15rem;
    margin-left: var(--line-indent);
  }

  .rendered-line :global(.md-marker) { color: var(--muted); text-align: right; }
  .rendered-line :global(.md-number) { font-variant-numeric: tabular-nums; }

  .rendered-line :global(.md-task-line input) {
    width: .95rem;
    height: .95rem;
    margin: .24rem 0 0 .08rem;
    accent-color: var(--forest);
    pointer-events: none;
  }

  .rendered-line :global(blockquote) {
    margin: 0;
    border-left: 3px solid #c9d3cc;
    padding-left: .8rem;
    color: var(--muted);
  }

  .rendered-line :global(code) {
    border-radius: .25rem;
    background: #f0eee7;
    padding: .08rem .25rem;
    font-size: .9em;
  }

  .rendered-line :global(a) {
    color: var(--forest-2);
    text-decoration: underline;
    text-underline-offset: .12rem;
    pointer-events: none;
  }

  .rendered-line :global(hr) {
    border: 0;
    border-top: 1px solid var(--line);
    margin: .65rem .15rem;
  }

  .rendered-line :global(.md-code-fence),
  .rendered-line :global(.md-code-line) {
    margin: 0 -.05rem;
    background: #f0eee7;
    padding: .12rem .55rem;
    font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
    font-size: .88em;
  }

  .rendered-line :global(.md-code-fence) {
    min-height: .35rem;
    color: var(--muted);
    font-size: .7rem;
  }

  .compact .live-surface { min-height: 9rem; max-height: 18rem; }

  @media (max-width: 640px) {
    .live-surface,
    .compact .live-surface { min-height: 12rem; max-height: 24rem; }
  }
</style>
