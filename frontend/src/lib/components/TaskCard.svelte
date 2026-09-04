<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { api } from '../api/client';
  import type { Status, Task } from '../api/types';
  import BlockTaskModal from './BlockTaskModal.svelte';
  import Markdown from './Markdown.svelte';

  export let task: Task;
  export let statuses: Status[] = [];
  export let readOnly = false;

  const dispatch = createEventDispatcher<{ changed: Task; open: number; error: string }>();
  let busy = false;
  let descriptionExpanded = false;
  let blockModalOpen = false;

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

  async function runBlockingAction(action: () => Promise<Task>, fallbackMessage: string) {
    busy = true;
    try {
      dispatch('changed', await action());
      blockModalOpen = false;
    } catch (error) {
      dispatch('error', error instanceof Error ? error.message : fallbackMessage);
    } finally {
      busy = false;
    }
  }

  function block(reason: string) {
    void runBlockingAction(() => api.blockTask(task.id, reason), 'Could not block task');
  }

  function reblock() {
    void runBlockingAction(() => api.reblockTask(task.id), 'Could not reblock task');
  }

  async function deleteBlock(blockId: number) {
    busy = true;
    try {
      dispatch('changed', await api.deleteBlock(task.id, blockId));
    } catch (error) {
      dispatch('error', error instanceof Error ? error.message : 'Could not delete blocking reason');
    } finally {
      busy = false;
    }
  }

  function markWorkedNow() {
    void act(() => api.updateTask(task.id, { last_worked_at: new Date().toISOString() }));
  }
</script>

<article class:blocked={task.current_block} class:finished={task.finished_at} class="task-card">
  <div class="task-card__top">
    <button class="title-button" on:click={() => dispatch('open', task.id)}>{task.title}</button>
    <div class="task-card__header-actions">
      {#if !readOnly}
        <button
          type="button"
          class="edit-button"
          aria-label="Edit task"
          title="Edit task"
          disabled={busy}
          on:click={() => dispatch('open', task.id)}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" />
          </svg>
        </button>
      {/if}
      <span class="score" title="Calculated score">{task.score.toFixed(1)}</span>
    </div>
  </div>

  {#if task.description}
    <div class:expanded={descriptionExpanded} class="task-description">
      <Markdown source={task.description} />
    </div>
    <button
      type="button"
      class="description-toggle"
      aria-expanded={descriptionExpanded}
      on:click={() => (descriptionExpanded = !descriptionExpanded)}
    >
      {descriptionExpanded ? 'Collapse description' : 'Expand description'}
    </button>
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
      <button
        type="button"
        class="finish-toggle"
        class:checked={!!task.finished_at}
        aria-label={task.finished_at ? 'Reopen task' : 'Finish task'}
        aria-pressed={!!task.finished_at}
        title={task.finished_at ? 'Reopen task' : 'Finish task'}
        disabled={busy}
        on:click={() => act(() => task.finished_at ? api.reopenTask(task.id) : api.finishTask(task.id))}
      >
        <span aria-hidden="true">{task.finished_at ? '✓' : ''}</span>
      </button>
      <button disabled={busy} title="Set last worked on to now" on:click={markWorkedNow}>Worked now</button>
      <button disabled={busy} on:click={() => task.current_block ? act(() => api.unblockTask(task.id)) : (blockModalOpen = true)}>
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

{#if blockModalOpen}
  <BlockTaskModal
    taskTitle={task.title}
    history={task.blocking_history}
    {busy}
    on:close={() => (blockModalOpen = false)}
    on:block={(event) => block(event.detail)}
    on:reblock={reblock}
    on:deleteBlock={(event) => deleteBlock(event.detail)}
  />
{/if}

<style>
  .task-card__header-actions {
    display: flex;
    align-items: center;
    gap: .35rem;
  }

  .edit-button {
    display: grid;
    width: 1.75rem;
    height: 1.75rem;
    place-items: center;
    border: 0;
    border-radius: .4rem;
    background: transparent;
    color: var(--muted);
    opacity: .35;
    padding: .3rem;
    transition: opacity .15s ease, background .15s ease;
  }

  .edit-button svg {
    width: 100%;
    height: 100%;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
  }

  .task-card:hover .edit-button,
  .edit-button:focus-visible {
    opacity: .85;
  }

  .edit-button:hover:not(:disabled) {
    background: rgba(0, 0, 0, .04);
  }

  .finish-toggle {
    display: grid;
    width: 2rem;
    height: 2rem;
    flex: 0 0 2rem;
    place-items: center;
    border: 1.5px solid #aaa69c;
    border-radius: .45rem;
    background: #fff;
    color: #fff;
    padding: 0;
    font-size: 1rem;
    font-weight: 900;
    line-height: 1;
  }

  .finish-toggle.checked {
    border-color: var(--forest);
    background: var(--forest);
  }

  .finish-toggle:hover:not(:disabled) {
    border-color: var(--forest);
  }

  .task-description {
    width: 100%;
    height: 7rem;
    margin-top: .6rem;
    overflow-y: auto;
    padding: .65rem .75rem;
    border: 1px solid var(--line);
    border-radius: .55rem;
    background: #faf8f2;
  }

  .task-description.expanded {
    height: auto;
    overflow-y: visible;
  }

  .description-toggle {
    margin-top: .35rem;
    border: 0;
    background: transparent;
    color: var(--forest-2);
    padding: .15rem 0;
    font-size: .8rem;
    font-weight: 700;
    text-decoration: underline;
    text-underline-offset: .15rem;
  }

  @media (max-width: 600px) {
    .edit-button {
      opacity: .6;
    }
  }
</style>