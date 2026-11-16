<script lang="ts">
  import type { TagSummary } from '../api/types';
  import { tagAppearance } from '../tagAppearance';

  export let tag: TagSummary;
  export let selected = false;
  export let inherited = false;
  export let compact = false;

  $: appearance = tagAppearance(tag.color);
</script>

<span
  class="tag-badge"
  class:selected
  class:inherited
  class:compact
  style:--tag-background={appearance.background}
  style:--tag-foreground={appearance.foreground}
><slot>{tag.display_name}</slot></span>

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
  .tag-badge.compact {
    max-width: 100%;
    background: color-mix(in srgb, var(--tag-background) 10%, var(--paper));
    border-color: color-mix(in srgb, var(--tag-background) 20%, var(--paper));
    color: var(--ink);
    padding: .12rem .35rem;
    font-size: .65rem;
    font-weight: 600;
    overflow-wrap: anywhere;
  }
  .tag-badge.compact::before {
    content: '';
    flex: 0 0 .3rem;
    width: .3rem;
    height: .3rem;
    border-radius: 50%;
    background: var(--tag-background);
  }
  .tag-badge :global(button) { border: 0; border-radius: 50%; background: transparent; color: inherit; padding: 0 .1rem; line-height: 1; }
  .tag-badge :global(button:hover) { background: rgba(0, 0, 0, .15); }
</style>
