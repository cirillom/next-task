<script lang="ts">
  import DOMPurify from 'dompurify';
  import { marked } from 'marked';

  export let source = '';
  $: html = DOMPurify.sanitize(marked.parse(source, { gfm: true }) as string);
</script>

<div class="markdown">{@html html}</div>

<style>
  .markdown :global(li:has(> input[type='checkbox'])) {
    list-style: none;
  }

  .markdown :global(input[type='checkbox']) {
    width: .95rem;
    height: .95rem;
    margin: 0 .45rem 0 -1.35rem;
    vertical-align: -.12rem;
    opacity: 1;
    accent-color: var(--forest);
    pointer-events: none;
  }
</style>
