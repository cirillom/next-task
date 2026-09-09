<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { api } from '../api/client';
  import type { Task } from '../api/types';
  import { daysSince, formatDate, formatDateTime, localDate } from '../format';
  import BlockTaskModal from './BlockTaskModal.svelte';
  import Markdown from './Markdown.svelte';
  import TaskCompletionDialog from './TaskCompletionDialog.svelte';
  import TaskHierarchy from './TaskHierarchy.svelte';

  export let task: Task;
  export let readOnly = false;

  const dispatch = createEventDispatcher<{ changed: Task; open: number; error: string }>();
  let busy = false;
  let descriptionExpanded = false;
  let blockModalOpen = false;
  let completionOpen = false;

  function idleAnchor(): string {
    return task.last_worked_at || task.created_at;
  }

  function idleLabel(): string {
    const days = daysSince(idleAnchor());
    return `Idle ${days} ${days === 1 ? 'day' : 'days'} (${formatDate(idleAnchor())})`;
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

  function finish() {
    if (task.unfinished_descendant_count > 0) {
      completionOpen = true;
      return;
    }
    void act(() => api.finishTask(task.id));
  }

  async function confirmFinish() {
    busy = true;
    try {
      const updated = await api.finishTask(task.id);
      completionOpen = false;
      dispatch('changed', updated);
    } catch (error) {
      dispatch('error', error instanceof Error ? error.message : 'Could not finish task');
    } finally {
      busy = false;
    }
  }
</script>

<article class="recommended-card">
  <div class="recommended-card__top">
    <div>
      <p class="eyebrow">Recommended next</p>
      <h2>{task.title} <span class="task-id">#{task.id}</span></h2>
    </div>
    <div class="recommended-card__header-actions">
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

  <TaskHierarchy {task} on:open={(event) => dispatch('open', event.detail)} />

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
      class:overdue={!!task.due_date && task.due_date < localDate()}
    >Due {task.due_date ? formatDate(task.due_date) : '—'}</span>
    <span class="date-meta" title={formatDateTime(idleAnchor())}>{idleLabel()}</span>
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
      <button type="button" class="action-button finish-action" disabled={busy} on:click={finish}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.2 4.2L19 7" /></svg>
        <span>Finish</span>
      </button>
      <button type="button" class="action-button worked-action" disabled={busy} on:click={markWorkedNow}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3.2 2" /></svg>
        <span>Worked now</span>
      </button>
      <button type="button" class="action-button block-action" disabled={busy} on:click={() => (blockModalOpen = true)}>
        <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M6 18 18 6" /></svg>
        <span>Block</span>
      </button>
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

{#if completionOpen}
  <TaskCompletionDialog
    workspaceId={task.workspace_id}
    taskId={task.id}
    taskTitle={task.title}
    {busy}
    on:close={() => (completionOpen = false)}
    on:confirm={() => void confirmFinish()}
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

  .recommended-card__top { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; }
  .recommended-card__top .eyebrow { margin-bottom: .35rem; }
  .recommended-card h2 { margin: 0; font-size: clamp(1.35rem, 3vw, 1.8rem); }
  .task-id { color: var(--muted); font-size: .55em; font-weight: 750; vertical-align: middle; }
  .recommended-card__header-actions { display: flex; align-items: center; gap: .35rem; }

  .edit-button {
    display: grid; width: 1.75rem; height: 1.75rem; place-items: center; border: 0; border-radius: .4rem;
    background: transparent; color: var(--muted); opacity: .35; padding: .3rem;
    transition: opacity .15s ease, background .15s ease;
  }

  .edit-button svg { width: 100%; height: 100%; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }
  .recommended-card:hover .edit-button, .edit-button:focus-visible { opacity: .85; }
  .edit-button:hover:not(:disabled) { background: rgba(0, 0, 0, .04); }

  .score { flex: 0 0 auto; border-radius: .55rem; background: #f3e7c8; color: #6b4d13; padding: .42rem .62rem; font-size: 1rem; font-variant-numeric: tabular-nums; font-weight: 850; }
  .task-description { width: 100%; height: 7rem; margin-top: .6rem; overflow-y: auto; padding: .65rem .75rem; border: 1px solid var(--line); border-radius: .55rem; background: #faf8f2; }
  .task-description.expanded { height: auto; overflow-y: visible; }
  .description-toggle { margin-top: .35rem; border: 0; background: transparent; color: var(--forest-2); padding: .15rem 0; font-size: .8rem; font-weight: 700; text-decoration: underline; text-underline-offset: .15rem; }
  .meta-row, .tag-row { display: flex; flex-wrap: wrap; align-items: center; gap: .45rem .65rem; margin-top: .8rem; }
  .meta-row { color: var(--muted); font-size: .8rem; }
  .meta-row > span + span::before { content: '·'; margin-right: .65rem; color: #b8b3a8; font-weight: 700; }
  .priority { color: var(--forest); font-weight: 800; }
  .date-meta { font-variant-numeric: tabular-nums; }
  .overdue { color: var(--danger); font-weight: 700; }
  .tag { display: inline-flex; align-items: center; border-radius: 2rem; background: color-mix(in srgb, var(--tag-color) 15%, white); color: color-mix(in srgb, var(--tag-color) 80%, black); padding: .25rem .55rem; font-size: .78rem; }
  .recommended-actions { display: flex; flex-wrap: wrap; gap: .55rem; margin-top: 1rem; border-top: 1px solid #e8e3d9; padding-top: .85rem; }
  .action-button { display: inline-flex; align-items: center; gap: .4rem; border: 1px solid #cbc8be; border-radius: .55rem; background: #fff; color: var(--ink); padding: .58rem .78rem; font-size: .8rem; font-weight: 700; }
  .action-button svg { width: 1rem; height: 1rem; flex: 0 0 1rem; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }
  .action-button:hover:not(:disabled) { border-color: #9fa9a3; background: #fbfaf6; }
  .finish-action { border-color: var(--forest); background: var(--forest); color: #fff; }
  .finish-action:hover:not(:disabled) { border-color: var(--forest-2); background: var(--forest-2); }
  .worked-action { color: var(--forest-2); }
  .block-action { color: #8a4d36; }

  @media (max-width: 600px) {
    .recommended-card { padding: 1.05rem; }
    .edit-button { opacity: .6; }
    .action-button { flex: 1 1 calc(50% - .55rem); justify-content: center; }
  }
</style>
