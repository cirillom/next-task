<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { api } from '../api/client';
  import type { Status, Task } from '../api/types';
  import Markdown from './Markdown.svelte';

  export let task: Task;
  export let statuses: Status[] = [];
  export let readOnly = false;

  const dispatch = createEventDispatcher<{ changed: Task; open: number; error: string }>();
  let busy = false;

  async function act(action: () => Promise<Task>) {
    busy = true;
    try {
      dispatch('changed', await action());
    } catch (error) {
      dispatch('error', error instanceof Error ? error.message : 'Action failed');
    } finally {
      busy = false;
    }
  }

  function block() {
    const reason = window.prompt('Why is this task blocked?');
    if (reason?.trim()) void act(() => api.blockTask(task.id, reason.trim()));
  }
</script>

<article class:blocked={task.current_block} class:finished={task.finished_at} class="task-card">
  <div class="task-card__top">
    <button class="title-button" on:click={() => dispatch('open', task.id)}>{task.title}</button>
    <span class="score" title="Calculated score">{task.score.toFixed(1)}</span>
  </div>

  {#if task.description}
    <Markdown source={task.description} />
  {/if}

  <div class="meta-row">
    <span class="priority">P{task.priority}</span>
    <span>{task.status.name}</span>
    {#if task.due_date}<span class:overdue={!task.finished_at && task.due_date < new Date().toISOString().slice(0, 10)}>Due {task.due_date}</span>{/if}
    {#each task.assignees as assignee}<span>{assignee.display_name}</span>{/each}
  </div>

  {#if task.direct_tags.length}
    <div class="tag-row">
      {#each task.direct_tags as tag}
        <span class="tag" style:--tag-color={tag.color || '#73847c'}>#{tag.name}</span>
      {/each}
    </div>
  {/if}

  {#if task.current_block}
    <div class="blocked-reason"><strong>Blocked:</strong> {task.current_block.reason}</div>
  {/if}

  {#if !readOnly}
    <div class="task-actions">
      <button disabled={busy} on:click={() => dispatch('open', task.id)}>Open</button>
      <button disabled={busy} on:click={() => act(() => task.finished_at ? api.reopenTask(task.id) : api.finishTask(task.id))}>
        {task.finished_at ? 'Reopen' : 'Finish'}
      </button>
      <button disabled={busy} on:click={() => task.current_block ? act(() => api.unblockTask(task.id)) : block()}>
        {task.current_block ? 'Unblock' : 'Block'}
      </button>
      <select
        aria-label="Status"
        disabled={busy}
        value={task.status.id}
        on:change={(event) => act(() => api.updateTask(task.id, { status_id: Number(event.currentTarget.value) }))}
      >
        {#each statuses as status}<option value={status.id}>{status.name}</option>{/each}
      </select>
      <div class="stepper" aria-label="Priority">
        <button disabled={busy || task.priority <= 1} on:click={() => act(() => api.updateTask(task.id, { priority: task.priority - 1 }))}>−</button>
        <span>{task.priority}</span>
        <button disabled={busy} on:click={() => act(() => api.updateTask(task.id, { priority: task.priority + 1 }))}>+</button>
      </div>
    </div>
  {/if}
</article>
