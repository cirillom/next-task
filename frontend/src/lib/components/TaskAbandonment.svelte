<script lang="ts">
  import { t } from '../i18n';
  import { createEventDispatcher } from 'svelte';
  import type { Task } from '../api/types';
  import TaskAction from './TaskAction.svelte';
  import { formatDateTime } from '../format';

  export let task: Task;
  export let disabled = false;
  export let readOnly = false;
  export let compact = true;
  const dispatch = createEventDispatcher<{ abandon: void; restore: void; open: number }>();
</script>

{#if task.abandoned_by_task_id || (!readOnly && !task.finished_at && task.priority > 0)}
  <div class="abandonment">
    {#if task.abandoned_at}
      <span title={formatDateTime(task.abandoned_at)}>{$t('ui.taskAbandonment.abandoned')}</span>
      {#if !readOnly}<TaskAction icon="restore" label={$t('ui.taskAbandonment.restoreTask')} className="abandon-action" {disabled} {compact} on:click={() => dispatch('restore')} />{/if}
    {:else if task.abandoned_by_task_id}
      <span>{$t('ui.taskAbandonment.inactiveBecauseAParentTaskIsAbandoned')}</span>
      <button type="button" class="parent-link" on:click={() => dispatch('open', task.abandoned_by_task_id!)}>{$t('ui.taskAbandonment.openParent', { value1: task.abandoned_by_task_id })}</button>
    {:else}
      <TaskAction icon="abandon" label={$t('ui.taskAbandonment.abandonTask')} className="abandon-action" {disabled} {compact} on:click={() => dispatch('abandon')} />
    {/if}
  </div>
{/if}

<style>
  .abandonment { display: inline-flex; flex-wrap: wrap; align-items: center; gap: .5rem; color: var(--muted); font-size: .8rem; }
  .parent-link { border: 0; background: transparent; color: var(--forest-2); padding: 0; font: inherit; text-decoration: underline; }
</style>
