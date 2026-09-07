<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { api } from '../api/client';
  import type { Task } from '../api/types';
  import { formatDate, formatDateTime } from '../format';
  import BlockTaskModal from './BlockTaskModal.svelte';
  import Markdown from './Markdown.svelte';

  export let task: Task;
  export let readOnly = false;

  const dispatch = createEventDispatcher<{ changed: Task; open: number; error: string }>();
  let busy = false;
  let descriptionExpanded = false;
  let blockModalOpen = false;

  function idleDays(): number {
    const anchor = new Date(task.last_worked_at || task.created_at).getTime();
    return Math.max(0, Math.floor((Date.now() - anchor) / 86_400_000));
  }

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

  function block(request: { reason: string; unblocked_at: string | null }) {
    void runBlockingAction(
      () => api.blockTask(task.id, request.reason, request.unblocked_at),
      'Could not block task'
    );
  }

  function reblock(request: { unblocked_at: string | null }) {
    void runBlockingAction(
      () => api.reblockTask(task.id, request.unblocked_at),
      'Could not reblock task'
    );
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

<article class="recommended-card">
  <div class="recommended-card__top">
    <div>
      <p class="eyebrow">Recommended next</p>
      <h2>{task.title} <span class="task-id">#{task.id}</span></h2>
    </div>
    <span class="score" title="Calculated score">{task.score.toFixed(1)}</span>
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
    <span class="priority">Priority {task.priority}</span>
    <span>{task.status.name}</span>
    <span class="date-meta" title={formatDateTime(task.created_at)}>Created {formatDate(task.created_at)}</span>
    <span
      class="date-meta"
      class:overdue={!!task.due_date && task.due_date < new Date().toISOString().slice(0, 10)}
    >Due {task.due_date ? formatDate(task.due_date) : '—'}</span>
    <span class="date-meta">Last worked {task.last_worked_at ? formatDateTime(task.last_worked_at) : '—'}</span>
    <span class="date-meta">Idle {idleDays()} {idleDays() === 1 ? 'day' : 'days'}</span>
    {#each task.assignees as assignee}<span>{assignee.display_name}</span>{/each}
  </div>

  {#if task.direct_tags.length}
    <div class="tag-row">
      {#each task.direct_tags as tag}
        <span class="tag" style:--tag-color={tag.color || '#73847c'}>#{tag.name}</span>
      {/each}
    </div>
  {/if}

  {#if !readOnly}
    <div class="recommended-actions">
      <button
        type="button"
        class="primary-action"
        disabled={busy}
        on:click={() => act(() => api.finishTask(task.id))}
      >
        <span aria-hidden="true">✓</span>
        Finish
      </button>
      <button type="button" disabled={busy} on:click={markWorkedNow}>Worked now</button>
      <button type="button" disabled={busy} on:click={() => (blockModalOpen = true)}>Block / defer</button>
      <button type="button" disabled={busy} on:click={() => dispatch('open', task.id)}>Edit task</button>
    </div>
  {:else}
    <div class="recommended-actions">
      <button type="button" on:click={() => dispatch('open', task.id)}>View task</button>
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
    on:reblock={(event) => reblock(event.detail)}
    on:deleteBlock={(event) => deleteBlock(event.detail)}
  />
{/if}

<style>
  .recommended-card {
    border: 1px solid #cfd8d2;
    border-left: 5px solid var(--forest-2);
    border-radius: 1rem;
    background: var(--paper);
    padding: 1.35rem 1.4rem;
    box-shadow: 0 14px 38px rgba(30, 48, 39, .1);
  }

  .recommended-card__top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }

  .recommended-card__top .eyebrow {
    margin-bottom: .35rem;
  }

  .recommended-card h2 {
    margin: 0;
    font-size: clamp(1.35rem, 3vw, 1.8rem);
  }

  .task-id {
    color: var(--muted);
    font-size: .55em;
    font-weight: 750;
    vertical-align: middle;
  }

  .score {
    flex: 0 0 auto;
    border-radius: .55rem;
    background: #f3e7c8;
    color: #6b4d13;
    padding: .42rem .62rem;
    font-size: 1rem;
    font-variant-numeric: tabular-nums;
    font-weight: 850;
  }

  .task-description {
    max-height: 7rem;
    margin-top: .85rem;
    overflow: hidden;
    border-top: 1px solid #ebe6dc;
    padding-top: .75rem;
  }

  .task-description.expanded {
    max-height: none;
  }

  .description-toggle {
    border: 0;
    background: transparent;
    color: var(--forest-2);
    padding: .35rem 0 0;
    font-size: .75rem;
    font-weight: 700;
  }

  .meta-row,
  .tag-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: .45rem .65rem;
    margin-top: .8rem;
  }

  .meta-row {
    color: var(--muted);
    font-size: .8rem;
  }

  .meta-row > span + span::before {
    content: '·';
    margin-right: .65rem;
    color: #b8b3a8;
    font-weight: 700;
  }

  .priority {
    color: var(--forest);
    font-weight: 800;
  }

  .date-meta {
    font-variant-numeric: tabular-nums;
  }

  .overdue {
    color: var(--danger);
    font-weight: 700;
  }

  .tag {
    display: inline-flex;
    align-items: center;
    border-radius: 2rem;
    background: color-mix(in srgb, var(--tag-color) 15%, white);
    color: color-mix(in srgb, var(--tag-color) 80%, black);
    padding: .25rem .55rem;
    font-size: .78rem;
  }

  .recommended-actions {
    display: flex;
    flex-wrap: wrap;
    gap: .55rem;
    margin-top: 1rem;
    border-top: 1px solid #e8e3d9;
    padding-top: .85rem;
  }

  .recommended-actions button {
    border: 1px solid #cbc8be;
    border-radius: .55rem;
    background: #fff;
    color: var(--ink);
    padding: .58rem .78rem;
    font-size: .8rem;
    font-weight: 700;
  }

  .recommended-actions button:hover:not(:disabled) {
    border-color: #9fa9a3;
    background: #fbfaf6;
  }

  .recommended-actions .primary-action {
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    border-color: var(--forest);
    background: var(--forest);
    color: #fff;
  }

  .recommended-actions .primary-action:hover:not(:disabled) {
    border-color: var(--forest-2);
    background: var(--forest-2);
  }

  @media (max-width: 600px) {
    .recommended-card {
      padding: 1.05rem;
    }

    .recommended-actions button {
      flex: 1 1 calc(50% - .55rem);
    }
  }
</style>
