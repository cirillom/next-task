<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Task } from '../api/types';

  export let task: Task;
  export let compact = false;

  const dispatch = createEventDispatcher<{ open: number }>();

  $: completedSubtasks = task.subtasks.filter((subtask) => !!subtask.finished_at).length;
</script>

{#if task.parent_task || task.subtasks.length}
  <div class:compact class="task-hierarchy">
    {#if task.parent_task}
      <div class="parent-link">
        <span aria-hidden="true">↳</span>
        <span>Parent:</span>
        <button
          type="button"
          title={`Open parent task #${task.parent_task.id}`}
          on:click={() => dispatch('open', task.parent_task!.id)}
        >
          {task.parent_task.title}
          <small>#{task.parent_task.id}</small>
        </button>
      </div>
    {/if}

    {#if task.subtasks.length}
      <span class="subtask-progress">
        Subtasks {completedSubtasks} / {task.subtasks.length} complete
      </span>
    {/if}
  </div>
{/if}

<style>
  .task-hierarchy {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: .4rem .8rem;
    margin-top: .65rem;
    color: var(--muted);
    font-size: .78rem;
  }

  .parent-link {
    display: inline-flex;
    min-width: 0;
    align-items: center;
    gap: .28rem;
  }

  .parent-link > span:first-child {
    color: var(--forest-2);
    font-weight: 900;
  }

  .parent-link button {
    display: inline-flex;
    min-width: 0;
    align-items: baseline;
    gap: .3rem;
    overflow: hidden;
    border: 0;
    background: transparent;
    color: var(--forest-2);
    padding: 0;
    font: inherit;
    font-weight: 750;
    text-align: left;
  }

  .parent-link button:hover {
    text-decoration: underline;
    text-underline-offset: .14rem;
  }

  .parent-link button small {
    flex: 0 0 auto;
    color: var(--muted);
    font-size: .68rem;
    font-weight: 700;
  }

  .subtask-progress {
    border-radius: 999px;
    background: rgba(55, 95, 75, .08);
    color: var(--forest-2);
    padding: .2rem .45rem;
    font-weight: 750;
  }

  .task-hierarchy.compact {
    margin-top: .22rem;
    font-size: .69rem;
  }

  .task-hierarchy.compact .subtask-progress {
    padding: .12rem .35rem;
  }

  .task-hierarchy.compact .parent-link button small {
    font-size: .63rem;
  }
</style>
