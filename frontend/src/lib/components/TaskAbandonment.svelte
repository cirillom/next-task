<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Task } from '../api/types';
  import AppButton from './AppButton.svelte';
  import { formatDateTime } from '../format';

  export let task: Task;
  export let disabled = false;
  export let readOnly = false;
  const dispatch = createEventDispatcher<{ abandon: void; restore: void; open: number }>();
</script>

{#if task.abandoned_by_task_id || (!readOnly && !task.finished_at && task.priority > 0)}
  <div class="abandonment">
    {#if task.abandoned_at}
      <span title={formatDateTime(task.abandoned_at)}>Abandoned</span>
      {#if !readOnly}<AppButton className="abandon-action" {disabled} on:click={() => dispatch('restore')}>Restore task</AppButton>{/if}
    {:else if task.abandoned_by_task_id}
      <span>Inactive because a parent task is abandoned.</span>
      <button type="button" class="parent-link" on:click={() => dispatch('open', task.abandoned_by_task_id!)}>Open parent #{task.abandoned_by_task_id}</button>
    {:else}
      <AppButton className="abandon-action" {disabled} on:click={() => dispatch('abandon')}>Abandon task</AppButton>
    {/if}
  </div>
{/if}

<style>
  .abandonment { display: inline-flex; flex-wrap: wrap; align-items: center; gap: .5rem; color: var(--muted); font-size: .8rem; }
  .abandonment :global(.abandon-action) { min-height: 2rem; padding: .35rem .6rem; font-size: .78rem; }
  .parent-link { border: 0; background: transparent; color: var(--forest-2); padding: 0; font: inherit; text-decoration: underline; }
</style>
