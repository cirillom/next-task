<script lang="ts">
  import type { TagSummary } from '../api/types';
  import { tagAppearance } from '../tagAppearance';

  export let tag: TagSummary;
  export let selected = false;
  export let inherited = false;

  $: appearance = tagAppearance(tag.color);
</script>

<span
  class="tag-badge"
  class:selected
  class:inherited
  style:--tag-background={appearance.background}
  style:--tag-foreground={appearance.foreground}
><slot>{tag.name}</slot></span>

<style>
  .tag-badge {
    display: inline-flex;
    align-items: center;
    gap: .25rem;
    border: 1px solid transparent;
    border-radius: 999px;
    background: var(--tag-background);
    color: var(--tag-foreground);
    padding: .25rem .55rem;
    font-size: .78rem;
    font-weight: 750;
    line-height: 1.2;
  }
  .tag-badge.selected { box-shadow: 0 0 0 2px var(--paper), 0 0 0 4px var(--tag-background); }
  .tag-badge.inherited { border-style: dashed; border-color: currentColor; }
  .tag-badge :global(button) { border: 0; border-radius: 50%; background: transparent; color: inherit; padding: 0 .1rem; line-height: 1; }
  .tag-badge :global(button:hover) { background: rgba(0, 0, 0, .15); }
</style>
