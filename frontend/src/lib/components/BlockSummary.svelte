<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Block } from '../api/types';
  import { formatDateTime } from '../format';
  import BlockLabel from './BlockLabel.svelte';

  export let blocks: Block[] = [];
  export let compact = false;
  const dispatch = createEventDispatcher<{ openTask: number }>();
</script>

{#if blocks.length}
  <div class="blocked-reason block-summary" class:compact>
    {#if blocks.length === 1}
      <div class="block-entry" class:clamped={compact}>
        <strong>Blocked:</strong>
        <BlockLabel block={blocks[0]} on:openTask={(event) => dispatch('openTask', event.detail)} />
        {#if blocks[0].reason && blocks[0].unblocked_at}<span class="block-note"> · Auto-unblocks {formatDateTime(blocks[0].unblocked_at)}</span>{/if}
      </div>
    {:else}
      <strong>Blocked:</strong>
      <ul>
        {#each compact ? blocks.slice(0, 3) : blocks as block (block.id)}
          <li><div class="block-entry" class:clamped={compact}>
            <BlockLabel {block} on:openTask={(event) => dispatch('openTask', event.detail)} />
            {#if block.reason && block.unblocked_at}<span class="block-note"> · Auto-unblocks {formatDateTime(block.unblocked_at)}</span>{/if}
          </div></li>
        {/each}
        {#if compact && blocks.length > 3}<li class="block-note">... +{blocks.length - 3} more</li>{/if}
      </ul>
    {/if}
  </div>
{/if}

<style>
  .block-summary:not(.compact) { margin-top: 0; }
  .block-entry { overflow-wrap: anywhere; line-height: 1.45; }
  .block-entry.clamped { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; line-clamp: 3; overflow: hidden; }
  .block-note { color: var(--muted); font-size: .82rem; }
  ul { margin: .35rem 0 0; padding-left: 1.25rem; }
  li + li { margin-top: .2rem; }
</style>
