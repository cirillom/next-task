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

  function formatDate(value: string): string {
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
      const [year, month, day] = value.split('-').map(Number);
      return new Date(year, month - 1, day).toLocaleDateString();
    }
    return new Date(value).toLocaleDateString();
  }
</script>

<article class:blocked={task.current_block} class:finished={task.finished_at} class="task-card">
  <div class="task-card__top">
    <button class="title-button" on:click={() => dispatch('open', task.id)}>
      <span>{task.title}</span>
      <span class="task-id">#{task.id}</span>
    </button>
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
    <span class="priority" title="Priority">{task.priority}</span>
    <span>{task.status.name}</span>
    <span class="date-meta" title={new Date(task.created_at).toLocaleString()}>Created {formatDate(task.created_at)}</span>
    <span
      class="date-meta"
      class:overdue={!!task.due_date && !task.finished_at && task.due_date < new Date().toISOString().slice(0, 10)}
    >Due {task.due_date ? formatDate(task.due_date) : '—'}</span>
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
        <span aria-hidden="true">✓</span>
      </button>

      <button
        type="button"
        class="quick-action worked-action"
        disabled={busy}
        title="Set last worked on to now"
        on:click={markWorkedNow}
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="8.5" />
          <path d="M12 7.5V12l3.2 2" />
        </svg>
        <span>Worked now</span>
      </button>

      <button
        type="button"
        class="quick-action block-action"
        class:active={!!task.current_block}
        disabled={busy}
        on:click={() => task.current_block ? act(() => api.unblockTask(task.id)) : (blockModalOpen = true)}
      >
        {#if task.current_block}
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M7 10V8a5 5 0 0 1 9.5-2" />
            <rect x="5" y="10" width="14" height="10" rx="2" />
          </svg>
          <span>Unblock</span>
        {:else}
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <circle cx="12" cy="12" r="8.5" />
            <path d="M6 18 18 6" />
          </svg>
          <span>Block</span>
        {/if}
      </button>

      <div class="status-select">
        <select
          aria-label="Status"
          disabled={busy}
          value={task.status.id}
          on:change={(event) => act(() => api.updateTask(task.id, { status_id: Number(event.currentTarget.value) }))}
        >
          {#each statuses as status}<option value={status.id}>{status.name}</option>{/each}
        </select>
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="m8 10 4 4 4-4" />
        </svg>
      </div>

      <div class="priority-stepper" aria-label="Priority">
        <button
          type="button"
          aria-label="Decrease priority"
          title="Decrease priority"
          disabled={busy || task.priority <= 1}
          on:click={() => act(() => api.updateTask(task.id, { priority: task.priority - 1 }))}
        >−</button>
        <span title="Priority">{task.priority}</span>
        <button
          type="button"
          aria-label="Increase priority"
          title="Increase priority"
          disabled={busy}
          on:click={() => act(() => api.updateTask(task.id, { priority: task.priority + 1 }))}
        >+</button>
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
  .title-button {
    display: flex;
    align-items: baseline;
    gap: .45rem;
  }

  .task-id {
    flex: 0 0 auto;
    color: var(--muted);
    font-size: .72rem;
    font-weight: 700;
    opacity: .72;
  }

  .date-meta {
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }

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
    color: #d8d6cf;
    padding: 0;
    font-size: 1rem;
    font-weight: 900;
    line-height: 1;
  }

  .finish-toggle.checked {
    border-color: var(--forest);
    background: var(--forest);
    color: #fff;
  }

  .finish-toggle:hover:not(:disabled) {
    border-color: var(--forest);
    color: #aaa69c;
  }

  .finish-toggle.checked:hover:not(:disabled) {
    color: #fff;
  }

  .quick-action {
    display: inline-flex;
    height: 2rem;
    align-items: center;
    gap: .38rem;
    border: 1px solid #cfcbc0;
    border-radius: .55rem;
    background: #fbfaf6;
    color: var(--ink);
    padding: 0 .62rem;
    font-size: .78rem;
    font-weight: 700;
    line-height: 1;
  }

  .quick-action svg {
    width: 1rem;
    height: 1rem;
    flex: 0 0 1rem;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
  }

  .quick-action:hover:not(:disabled) {
    border-color: #aaa69c;
    background: #fff;
  }

  .worked-action {
    color: var(--forest-2);
  }

  .block-action {
    color: #8a4d36;
  }

  .block-action.active {
    border-color: #d8b5a6;
    background: #fff4ee;
  }

  .status-select {
    position: relative;
    display: inline-flex;
    height: 2rem;
    align-items: center;
  }

  .status-select select {
    height: 100%;
    max-width: 11rem;
    appearance: none;
    border: 1px solid #c8cec6;
    border-radius: .55rem;
    background: #f4f7f2;
    color: var(--forest-2);
    padding: 0 1.8rem 0 .65rem;
    font-size: .78rem;
    font-weight: 750;
    line-height: 1;
    cursor: pointer;
  }

  .status-select select:hover:not(:disabled) {
    border-color: #9daa9f;
    background: #fff;
  }

  .status-select select:focus-visible {
    outline: 2px solid var(--forest);
    outline-offset: 2px;
  }

  .status-select > svg {
    position: absolute;
    right: .52rem;
    width: .85rem;
    height: .85rem;
    pointer-events: none;
    fill: none;
    stroke: var(--forest-2);
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 2;
  }

  .priority-stepper {
    display: inline-grid;
    height: 2rem;
    grid-template-columns: 1.65rem auto 1.65rem;
    align-items: stretch;
    overflow: hidden;
    border: 1px solid #cfcbc0;
    border-radius: .5rem;
    background: #fbfaf6;
  }

  .priority-stepper button {
    min-width: 0;
    border: 0;
    border-radius: 0;
    background: transparent;
    padding: 0;
    font-size: .95rem;
    line-height: 1;
  }

  .priority-stepper button:hover:not(:disabled) {
    background: rgba(0, 0, 0, .045);
  }

  .priority-stepper span {
    display: grid;
    min-width: 1.65rem;
    place-items: center;
    border-right: 1px solid #dedad0;
    border-left: 1px solid #dedad0;
    padding: 0 .2rem;
    color: var(--forest);
    font-size: .76rem;
    font-weight: 800;
    font-variant-numeric: tabular-nums;
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

    .quick-action span {
      display: none;
    }

    .quick-action {
      width: 2rem;
      justify-content: center;
      padding: 0;
    }

    .status-select select {
      max-width: 8.5rem;
    }
  }
</style>