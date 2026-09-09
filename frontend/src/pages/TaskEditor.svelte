<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import { localDateTime } from '../lib/format';
  import type { Task, TaskInput, TaskSummary, Workspace } from '../lib/api/types';
  import BlockTaskModal from '../lib/components/BlockTaskModal.svelte';
  import TaskCompletionDialog from '../lib/components/TaskCompletionDialog.svelte';
  import TaskForm from '../lib/components/TaskForm.svelte';

  export let workspace: Workspace;
  export let taskId = 0;
  const dispatch = createEventDispatcher<{
    close: void;
    saved: Task;
    changed: Task;
    deleted: number;
    openTask: number;
  }>();

  let task: Task | null = null;
  let loading = true;
  let busy = false;
  let blockModalOpen = false;
  let completionTarget: TaskSummary | null = null;
  let error = '';

  $: isDraft = task?.priority === 0;

  function taskSummary(item: Task): TaskSummary {
    return {
      id: item.id,
      title: item.title,
      finished_at: item.finished_at,
      unfinished_descendant_count: item.unfinished_descendant_count
    };
  }

  onMount(async () => {
    if (!taskId) {
      loading = false;
      return;
    }

    try {
      task = await api.task(taskId);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load task';
    } finally {
      loading = false;
    }
  });

  async function save(input: TaskInput) {
    busy = true;
    error = '';
    try {
      const saved = taskId
        ? await api.updateTask(taskId, input)
        : await api.createTask({ ...input, workspace_id: workspace.id });
      dispatch('saved', saved);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not save task';
    } finally {
      busy = false;
    }
  }

  async function remove() {
    if (!task || !window.confirm(`Delete “${task.title}”? This cannot be undone.`)) return;
    busy = true;
    try {
      await api.deleteTask(task.id);
      dispatch('deleted', task.id);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not delete task';
      busy = false;
    }
  }

  async function runTaskAction(action: () => Promise<Task>, fallbackMessage: string) {
    busy = true;
    error = '';
    try {
      const updated = await action();
      task = updated;
      dispatch('changed', updated);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : fallbackMessage;
    } finally {
      busy = false;
    }
  }

  async function runBlockingAction(action: () => Promise<Task>, fallbackMessage: string) {
    busy = true;
    error = '';
    try {
      const updated = await action();
      task = updated;
      dispatch('changed', updated);
      blockModalOpen = false;
    } catch (reason) {
      error = reason instanceof Error ? reason.message : fallbackMessage;
    } finally {
      busy = false;
    }
  }

  async function finishTarget(target: TaskSummary) {
    if (!task) return;
    busy = true;
    error = '';
    try {
      if (target.id === task.id) {
        task = await api.finishTask(task.id);
      } else {
        await api.finishTask(target.id);
        task = await api.task(task.id);
      }
      completionTarget = null;
      dispatch('changed', task);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not finish task';
    } finally {
      busy = false;
    }
  }

  function toggleFinished() {
    if (!task) return;
    if (task.finished_at) {
      void runTaskAction(() => api.reopenTask(task!.id), 'Could not reopen task');
      return;
    }

    const target = taskSummary(task);
    if (target.unfinished_descendant_count > 0) completionTarget = target;
    else void finishTarget(target);
  }

  async function toggleSubtask(subtask: TaskSummary) {
    if (!task) return;
    if (!subtask.finished_at && subtask.unfinished_descendant_count > 0) {
      completionTarget = subtask;
      return;
    }
    if (!subtask.finished_at) {
      await finishTarget(subtask);
      return;
    }

    busy = true;
    error = '';
    try {
      await api.reopenTask(subtask.id);
      task = await api.task(task.id);
      dispatch('changed', task);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not reopen subtask';
    } finally {
      busy = false;
    }
  }

  function block(request: { reason: string; unblocked_at: string | null }) {
    if (!task) return;
    void runBlockingAction(
      () => api.blockTask(task!.id, request.reason, request.unblocked_at),
      'Could not block task'
    );
  }

  function unblock() {
    if (!task) return;
    void runTaskAction(() => api.unblockTask(task!.id), 'Could not unblock task');
  }

  function reblock(request: { unblocked_at: string | null }) {
    if (!task) return;
    void runBlockingAction(
      () => api.reblockTask(task!.id, request.unblocked_at),
      'Could not reblock task'
    );
  }

  async function deleteBlock(blockId: number) {
    if (!task) return;
    busy = true;
    error = '';
    try {
      const updated = await api.deleteBlock(task.id, blockId);
      task = updated;
      dispatch('changed', updated);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not delete blocking reason';
    } finally {
      busy = false;
    }
  }
</script>

<div class="modal-backdrop" role="presentation" on:click|self={() => dispatch('close')}>
  <div class="task-editor" role="dialog" aria-modal="true" aria-labelledby="task-editor-title">
    <header class="editor-header">
      <div class="editor-heading-copy">
        <p class="eyebrow">{isDraft ? 'Edit draft' : taskId ? 'Task details' : 'Create task'}</p>
        <h1 id="task-editor-title" class="editor-title">
          {#if taskId}<span class="header-task-id">#{taskId}</span>{/if}
          <span>{taskId ? task?.title || 'Task' : 'New task'}</span>
        </h1>
      </div>
      <div class="editor-header-actions">
        {#if task && workspace.role !== 'viewer'}
          {#if !isDraft}
            <button
              type="button"
              class="finish-action"
              class:reopen={!!task.finished_at}
              disabled={busy}
              on:click={toggleFinished}
            >
              {#if task.finished_at}
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.8 9A8 8 0 1 1 4 14" /><path d="M4 4v5h5" /></svg>
                <span>Reopen</span>
              {:else}
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12.5 4.2 4.2L19 7" /></svg>
                <span>Finish</span>
              {/if}
            </button>
            <button
              type="button"
              class="quick-action block-action"
              class:active={!!task.current_block}
              disabled={busy}
              on:click={() => task?.current_block ? unblock() : (blockModalOpen = true)}
            >
              {#if task.current_block}
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10V8a5 5 0 0 1 9.5-2" /><rect x="5" y="10" width="14" height="10" rx="2" /></svg>
                <span>Unblock</span>
              {:else}
                <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="8.5" /><path d="M6 18 18 6" /></svg>
                <span>Block</span>
              {/if}
            </button>
          {/if}
          <button
            type="button"
            class="header-icon delete-icon"
            aria-label="Delete task"
            title="Delete task"
            disabled={busy}
            on:click={remove}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16" /><path d="M9 7V4h6v3" /><path d="m7 7 1 13h8l1-13" /><path d="M10 11v5M14 11v5" /></svg>
          </button>
        {/if}
        <button class="header-icon close-icon" aria-label="Close" title="Close" on:click={() => dispatch('close')}>×</button>
      </div>
    </header>

    {#if loading}
      <p class="empty">Loading editor…</p>
    {:else if taskId && !task}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
    {:else}
      {#if isDraft}
        <p class="notice draft-notice">Review the draft and choose a priority of 1 or higher before saving it as a task.</p>
      {/if}
      <TaskForm
        {workspace}
        {taskId}
        initialTitle={task?.title || ''}
        initialDescription={task?.description || ''}
        initialStatusId={task?.status.id || 0}
        initialPriority={isDraft ? 1 : task?.priority || 1}
        initialDueDate={task?.due_date || ''}
        initialLastWorked={task?.last_worked_at ? localDateTime(task.last_worked_at) : ''}
        initialParentTaskId={task?.parent_task_id || 0}
        initialAssigneeIds={task?.assignees.map((item) => item.id) || []}
        initialTagIds={task?.direct_tags.map((item) => item.id) || []}
        taskDetails={task}
        {busy}
        {error}
        submitLabel={isDraft ? 'Save as task' : taskId ? 'Save task' : 'Create task'}
        busyLabel={isDraft ? 'Saving…' : taskId ? 'Saving…' : 'Creating…'}
        on:cancel={() => dispatch('close')}
        on:openTask={(event) => dispatch('openTask', event.detail)}
        on:toggleSubtask={(event) => void toggleSubtask(event.detail)}
        on:submit={(event) => save(event.detail)}
      />
    {/if}
  </div>
</div>

{#if task && blockModalOpen}
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

{#if completionTarget}
  <TaskCompletionDialog
    workspaceId={workspace.id}
    taskId={completionTarget.id}
    taskTitle={completionTarget.title}
    {busy}
    on:close={() => (completionTarget = null)}
    on:confirm={() => void finishTarget(completionTarget!)}
  />
{/if}

<style>
  .task-editor {
    width: min(100%, 60rem);
    padding: 1rem;
  }

  .editor-header {
    top: -1rem;
    align-items: center;
    margin: -1rem -1rem .8rem;
    padding: .8rem 1rem .7rem;
  }

  .draft-notice { margin: 0 0 .65rem; }
  .editor-heading-copy { min-width: 0; }
  .editor-header .eyebrow { margin-bottom: .25rem; }
  .editor-header h1 { font-size: 1.65rem; }

  .editor-title {
    display: flex;
    min-width: 0;
    align-items: baseline;
    gap: .5rem;
    margin: 0;
    white-space: nowrap;
  }

  .editor-title > span:last-child {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .header-task-id {
    flex: 0 0 auto;
    color: var(--muted);
    font-size: .52em;
    font-weight: 750;
    font-variant-numeric: tabular-nums;
  }

  .editor-header-actions {
    display: flex;
    flex: 0 0 auto;
    align-items: center;
    gap: .4rem;
  }

  .finish-action,
  .quick-action {
    display: inline-flex;
    height: 2.1rem;
    align-items: center;
    gap: .38rem;
    border-radius: .55rem;
    padding: 0 .65rem;
    font-size: .78rem;
    font-weight: 700;
    line-height: 1;
  }

  .finish-action {
    border: 1px solid var(--forest);
    background: var(--forest);
    color: #fff;
    font-weight: 800;
  }

  .finish-action:hover:not(:disabled) { border-color: var(--forest-2); background: var(--forest-2); }
  .finish-action.reopen { border-color: #b9c3bd; background: #fff; color: var(--forest-2); }

  .quick-action { border: 1px solid #cfcbc0; background: #fbfaf6; color: var(--ink); }

  .finish-action svg,
  .quick-action svg,
  .header-icon svg {
    width: 1rem;
    height: 1rem;
    flex: 0 0 1rem;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
  }

  .quick-action:hover:not(:disabled) { border-color: #aaa69c; background: #fff; }
  .block-action { color: #8a4d36; }
  .block-action.active { border-color: #d8b5a6; background: #fff4ee; }

  .header-icon {
    display: grid;
    width: 2.1rem;
    height: 2.1rem;
    place-items: center;
    border: 1px solid #cbc8be;
    border-radius: .5rem;
    background: #fff;
    color: var(--muted);
    padding: 0;
  }

  .header-icon:hover:not(:disabled) { background: #f7f5ef; color: var(--ink); }
  .delete-icon { color: var(--danger); }
  .delete-icon:hover:not(:disabled) { border-color: #d8aaa5; background: #fff2f0; color: var(--danger); }
  .close-icon { font-size: 1.35rem; line-height: 1; }

  @media (max-width: 600px) {
    .task-editor { padding: .75rem; }
    .editor-header { top: -.75rem; margin: -.75rem -.75rem .7rem; padding: .7rem .75rem; }
    .finish-action span,
    .quick-action span { display: none; }
    .finish-action,
    .quick-action { width: 2.1rem; justify-content: center; padding: 0; }
  }
</style>
