<script lang="ts">
  import { t } from '../i18n';
  import { createEventDispatcher } from 'svelte';
  import type { Block } from '../api/types';

  export let block: Block;
  const dispatch = createEventDispatcher<{ openTask: number }>();
</script>

{#if block.blocking_task}
  <button type="button" title={block.blocking_task.title} aria-label={$t('ui.blockLabel.openTask', { value1: block.blocking_task.title, value2: block.blocking_task.id })} on:click={() => dispatch('openTask', block.blocking_task!.id)}>{block.blocking_task.title} #{block.blocking_task.id}</button>
  {#if block.blocking_task.abandoned_by_task_id}<span> {$t('ui.blockLabel.abandoned')}</span>{/if}
{:else}
  <span>{block.reason}</span>
{/if}

<style>
  button { max-width: 100%; border: 0; background: transparent; color: inherit; padding: 0; font: inherit; text-align: left; text-decoration: underline; text-underline-offset: .12rem; overflow-wrap: anywhere; }
  span { white-space: pre-line; }
</style>
