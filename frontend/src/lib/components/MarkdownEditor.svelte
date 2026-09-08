<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import Markdown from './Markdown.svelte';

  export let value = '';
  export let disabled = false;
  export let label = 'Description (Markdown)';
  export let placeholder = 'Add details, links, lists, tables, or code…';
  export let compact = false;

  const dispatch = createEventDispatcher<{ input: string }>();
  let mobileTab: 'edit' | 'preview' = 'edit';

  function handleInput(event: Event) {
    value = (event.currentTarget as HTMLTextAreaElement).value;
    dispatch('input', value);
  }
</script>

<div class:compact class="markdown-editor-live">
  <div class="mobile-tabs" aria-label="Description view">
    <button type="button" class:active={mobileTab === 'edit'} on:click={() => (mobileTab = 'edit')}>Edit</button>
    <button type="button" class:active={mobileTab === 'preview'} on:click={() => (mobileTab = 'preview')}>Preview</button>
  </div>

  <div class="editor-grid">
    <label class:hidden-mobile={mobileTab !== 'edit'}>
      <span class="field-label">{label}</span>
      <textarea
        {disabled}
        {placeholder}
        rows={compact ? 7 : 10}
        value={value}
        on:input={handleInput}
      ></textarea>
    </label>

    <section class:hidden-mobile={mobileTab !== 'preview'} class="preview" aria-label="Markdown preview">
      <span class="field-label">Preview</span>
      <div class="preview-body">
        {#if value}
          <Markdown source={value} />
        {:else}
          <p class="muted">Nothing to preview yet.</p>
        {/if}
      </div>
    </section>
  </div>
</div>

<style>
  .markdown-editor-live { display: grid; gap: .45rem; }

  .editor-grid {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    gap: .65rem;
  }

  label,
  .preview { min-width: 0; }

  textarea {
    width: 100%;
    min-height: 15rem;
    resize: vertical;
    line-height: 1.5;
  }

  .preview {
    display: flex;
    min-height: 15rem;
    max-height: 26rem;
    flex-direction: column;
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: .55rem;
    background: #faf8f2;
  }

  .preview > .field-label {
    flex: 0 0 auto;
    border-bottom: 1px solid var(--line);
    padding: .5rem .65rem;
  }

  .preview-body {
    min-height: 0;
    flex: 1 1 auto;
    overflow: auto;
    padding: .6rem .7rem;
  }

  .preview-body .muted { margin: 0; }

  .compact textarea { min-height: 9rem; }
  .compact .preview { min-height: 9rem; max-height: 13rem; }

  .mobile-tabs {
    display: none;
    width: fit-content;
    overflow: hidden;
    border: 1px solid #cbc8be;
    border-radius: .5rem;
    background: #fff;
  }

  .mobile-tabs button {
    border: 0;
    border-radius: 0;
    background: transparent;
    color: var(--muted);
    padding: .4rem .7rem;
    font-size: .76rem;
    font-weight: 750;
  }

  .mobile-tabs button.active {
    background: #eef2ef;
    color: var(--forest-2);
  }

  @media (max-width: 640px) {
    .mobile-tabs { display: inline-flex; }
    .editor-grid { grid-template-columns: 1fr; }
    .hidden-mobile { display: none; }
    textarea,
    .preview,
    .compact textarea,
    .compact .preview { min-height: 12rem; max-height: none; }
  }
</style>
