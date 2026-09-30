<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Block } from '../api/types';

  export let block: Block;
  const dispatch = createEventDispatcher<{ openTask: number }>();
</script>

{#if block.blocking_task}
  <button type="button" title={block.blocking_task.title} aria-label={`Open ${block.blocking_task.title}, task #${block.blocking_task.id}`} on:click={() => dispatch('openTask', block.blocking_task!.id)}>{block.blocking_task.title} #{block.blocking_task.id}</button>
{:else}
  <span>{block.reason}</span>
{/if}

<style>
  button { max-width: 100%; border: 0; background: transparent; color: inherit; padding: 0; font: inherit; text-align: left; text-decoration: underline; text-underline-offset: .12rem; overflow-wrap: anywhere; }
  span { white-space: pre-line; }
</style>
