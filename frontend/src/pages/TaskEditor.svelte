<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { Task, TaskInput, Workspace } from '../lib/api/types';
  import BlockTaskModal from '../lib/components/BlockTaskModal.svelte';
  import TaskForm from '../lib/components/TaskForm.svelte';

  export let workspace: Workspace;
  export let taskId = 0;
  const dispatch = createEventDispatcher<{ close: void; saved: Task; changed: Task; deleted: number }>();

  let task: Task | null = null;
  let loading = true;
  let busy = false;
  let blockModalOpen = false;
  let error = '';

  function datetimeLocal(value: string | null): string {
    if (!value) return '';
    const date = new Date(value);
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
    return local.toISOString().slice(0, 16);
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

  function reblock() {
    if (!task) return;
    void runBlockingAction(() => api.reblockTask(task!.id), 'Could not reblock task');
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
      <div>
        <p class="eyebrow">{taskId ? 'Task details' : 'Create task'}</p>
        <h1 id="task-editor-title" class="editor-title">
          {#if taskId}<span class="header-task-id">#{taskId}</span>{/if}
          <span>{taskId ? task?.title || 'Task' : 'New task'}</span>
        </h1>
      </div>
      <div class="editor-header-actions">
        {#if task && workspace.role !== 'viewer'}
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
        <button class="icon-button" aria-label="Close" on:click={() => dispatch('close')}>×</button>
      </div>
    </header>

    {#if loading}
      <p class="empty">Loading editor…</p>
    {:else if taskId && !task}
      {#if error}<p class="error" role="alert">{error}</p>{/if}
    {:else}
      <TaskForm
        {workspace}
        {taskId}
        initialTitle={task?.title || ''}
        initialDescription={task?.description || ''}
        initialStatusId={task?.status.id || 0}
        initialPriority={task?.priority || 1}
        initialDueDate={task?.due_date || ''}
        initialLastWorked={datetimeLocal(task?.last_worked_at || null)}
        initialParentTaskId={task?.parent_task_id || 0}
        initialAssigneeIds={task?.assignees.map((item) => item.id) || []}
        initialTagIds={task?.direct_tags.map((item) => item.id) || []}
        taskDetails={task}
        allowDelete={!!task && workspace.role !== 'viewer'}
        {busy}
        {error}
        submitLabel={taskId ? 'Save task' : 'Create task'}
        busyLabel={taskId ? 'Saving…' : 'Creating…'}
        on:cancel={() => dispatch('close')}
        on:delete={remove}
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
    on:reblock={reblock}
    on:deleteBlock={(event) => deleteBlock(event.detail)}
  />
{/if}

<style>
  .editor-title {
    display: flex;
    align-items: baseline;
    gap: .5rem;
  }

  .header-task-id {
    color: var(--muted);
    font-size: .52em;
    font-weight: 750;
    font-variant-numeric: tabular-nums;
  }

  .editor-header-actions {
    display: flex;
    align-items: center;
    gap: .55rem;
  }

  .quick-action {
    display: inline-flex;
    height: 2.1rem;
    align-items: center;
    gap: .38rem;
    border: 1px solid #cfcbc0;
    border-radius: .55rem;
    background: #fbfaf6;
    color: var(--ink);
    padding: 0 .65rem;
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

  .block-action { color: #8a4d36; }
  .block-action.active { border-color: #d8b5a6; background: #fff4ee; }

  @media (max-width: 600px) {
    .quick-action span { display: none; }
    .quick-action { width: 2.1rem; justify-content: center; padding: 0; }
  }
</style>
