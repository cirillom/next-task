<script lang="ts">
  import DOMPurify from 'dompurify';
  import { marked } from 'marked';

  export let source = '';
  $: html = DOMPurify.sanitize(marked.parse(source, { gfm: true }) as string);
</script>

<div class="markdown">{@html html}</div>

