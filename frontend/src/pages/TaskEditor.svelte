<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { ApiError, api } from '../lib/api/client';
  import type { Member, Status, Tag, Task, TaskInput, Workspace } from '../lib/api/types';
  import BlockTaskModal from '../lib/components/BlockTaskModal.svelte';
  import Markdown from '../lib/components/Markdown.svelte';

  export let workspace: Workspace;
  export let taskId = 0;
  const dispatch = createEventDispatcher<{ close: void; saved: Task; changed: Task; deleted: number }>();

  let task: Task | null = null;
  let statuses: Status[] = [];
  let tags: Tag[] = [];
  let members: Member[] = [];
  let parentTasks: Task[] = [];
  let filteredParentTasks: Task[] = [];
  let title = '';
  let description = '';
  let statusId = 0;
  let priority = 1;
  let dueDate = '';
  let lastWorked = '';
  let parentTaskId = 0;
  let parentSearch = '';
  let assigneeIds: number[] = [];
  let tagIds: number[] = [];
  let newTags = '';
  let mobileTab: 'edit' | 'preview' = 'edit';
  let loading = true;
  let busy = false;
  let blockModalOpen = false;
  let error = '';

  $: {
    const needle = parentSearch.trim().toLowerCase();
    filteredParentTasks = parentTasks.filter(
      (item) =>
        item.id !== taskId &&
        (item.id === parentTaskId || !needle || item.title.toLowerCase().includes(needle))
    );
  }

  function datetimeLocal(value: string | null): string {
    if (!value) return '';
    const date = new Date(value);
    const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
    return local.toISOString().slice(0, 16);
  }

  onMount(async () => {
    try {
      [statuses, tags, members, parentTasks] = await Promise.all([
        api.statuses(workspace.id),
        api.tags(workspace.id),
        api.members(workspace.id),
        api.tasks(workspace.id, { finished: false })
      ]);
      statusId = statuses[0]?.id || 0;
      if (taskId) {
        task = await api.task(taskId);
        title = task.title;
        description = task.description || '';
        statusId = task.status.id;
        priority = task.priority;
        dueDate = task.due_date || '';
        lastWorked = datetimeLocal(task.last_worked_at);
        parentTaskId = task.parent_task_id || 0;
        assigneeIds = task.assignees.map((item) => item.id);
        tagIds = task.direct_tags.map((item) => item.id);
      }
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load task';
    } finally {
      loading = false;
    }
  });

  function normalizedNewTags(): string[] {
    const values = newTags
      .split(/[\n,]+/)
      .map((value) => value.trim().replace(/^#/, '').trim().toLowerCase())
      .filter(Boolean);
    return [...new Set(values)];
  }

  async function resolveTagIds(): Promise<number[]> {
    const resolved = new Set(tagIds);
    for (const name of normalizedNewTags()) {
      const existing = tags.find((tag) => tag.name.toLowerCase() === name);
      if (existing) {
        resolved.add(existing.id);
        continue;
      }
      try {
        const created = await api.createTag(workspace.id, { name });
        tags = [...tags, created];
        resolved.add(created.id);
      } catch (reason) {
        if (!(reason instanceof ApiError) || reason.status !== 409) throw reason;
        tags = await api.tags(workspace.id);
        const concurrent = tags.find((tag) => tag.name.toLowerCase() === name);
        if (!concurrent) throw reason;
        resolved.add(concurrent.id);
      }
    }
    return [...resolved];
  }

  async function save() {
    busy = true;
    error = '';
    try {
      const resolvedTagIds = taskId ? tagIds : await resolveTagIds();
      const input: TaskInput = {
        title,
        description: description || null,
        status_id: statusId,
        priority,
        due_date: dueDate || null,
        last_worked_at: lastWorked ? new Date(lastWorked).toISOString() : null,
        parent_task_id: parentTaskId || null,
        assignee_ids: assigneeIds,
        tag_ids: resolvedTagIds
      };
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

  function block(reason: string) {
    if (!task) return;
    void runBlockingAction(() => api.blockTask(task!.id, reason), 'Could not block task');
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
      <div><p class="eyebrow">{taskId ? 'Task details' : 'Create task'}</p><h1 id="task-editor-title">{taskId ? title || 'Task' : 'New task'}</h1></div>
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
        {/if}
        <button class="icon-button" aria-label="Close" on:click={() => dispatch('close')}>×</button>
      </div>
    </header>

    {#if loading}<p class="empty">Loading editor…</p>{:else}
      <form on:submit|preventDefault={save}>
        <div class="form-grid">
          <label class="wide">Title<input bind:value={title} maxlength="500" required disabled={workspace.role === 'viewer'} /></label>
          <label>Status<select bind:value={statusId} disabled={workspace.role === 'viewer'}>{#each statuses as item}<option value={item.id}>{item.name}</option>{/each}</select></label>
          <label>Priority<input type="number" bind:value={priority} min="1" disabled={workspace.role === 'viewer'} /></label>
          <label>Due date<input type="date" bind:value={dueDate} disabled={workspace.role === 'viewer'} /></label>
          <label>Last worked<input type="datetime-local" bind:value={lastWorked} disabled={workspace.role === 'viewer'} /></label>
          <label class="wide parent-picker">
            Parent task
            <input type="search" bind:value={parentSearch} placeholder="Search unfinished tasks…" disabled={workspace.role === 'viewer'} />
            <select bind:value={parentTaskId} disabled={workspace.role === 'viewer'}>
              <option value={0}>No parent</option>
              {#each filteredParentTasks as item}<option value={item.id}>{item.title}</option>{/each}
            </select>
            <span class="help">Only unfinished tasks are available as parents.</span>
          </label>
        </div>

        <div class="mobile-tabs"><button type="button" class:active={mobileTab === 'edit'} on:click={() => (mobileTab = 'edit')}>Edit</button><button type="button" class:active={mobileTab === 'preview'} on:click={() => (mobileTab = 'preview')}>Preview</button></div>
        <div class="markdown-editor">
          <label class:hidden-mobile={mobileTab !== 'edit'}>Description (Markdown)<textarea bind:value={description} rows="14" disabled={workspace.role === 'viewer'} placeholder="Add details, links, lists, tables, or code…"></textarea></label>
          <section class:hidden-mobile={mobileTab !== 'preview'} class="preview"><span class="field-label">Preview</span>{#if description}<Markdown source={description} />{:else}<p class="muted">Nothing to preview yet.</p>{/if}</section>
        </div>

        <fieldset disabled={workspace.role === 'viewer'}><legend>Assignees</legend><div class="choice-grid">{#each members as member}<label><input type="checkbox" value={member.user_id} bind:group={assigneeIds} /> {member.display_name}</label>{/each}</div></fieldset>
        <fieldset disabled={workspace.role === 'viewer'}>
          <legend>Direct tags</legend>
          <div class="choice-grid">{#each tags as tag}<label><input type="checkbox" value={tag.id} bind:group={tagIds} /> #{tag.name}</label>{/each}</div>
          {#if !taskId && workspace.role !== 'viewer'}
            <label class="new-tags">Add new tags<input bind:value={newTags} placeholder="errands, home, project-x" /><span class="help">Comma-separated. New tags are created and assigned when you save the task.</span></label>
          {/if}
        </fieldset>

        {#if task}
          <section class="detail-panel">
            <dl><div><dt>Creator</dt><dd>{task.creator.display_name}</dd></div><div><dt>Created</dt><dd>{new Date(task.created_at).toLocaleString()}</dd></div><div><dt>Finished</dt><dd>{task.finished_at ? new Date(task.finished_at).toLocaleString() : 'Not finished'}</dd></div></dl>
            {#if task.current_block}<div class="blocked-reason"><strong>Currently blocked:</strong> {task.current_block.reason}</div>{/if}
            {#if task.subtasks.length}<h3>Subtasks</h3><ul>{#each task.subtasks as subtask}<li>{subtask.finished_at ? '✓' : '○'} {subtask.title}</li>{/each}</ul>{/if}
          </section>
        {/if}

        {#if error}<p class="error" role="alert">{error}</p>{/if}
        <footer class="editor-actions">
          {#if task && workspace.role !== 'viewer'}<button type="button" class="danger" disabled={busy} on:click={remove}>Delete</button>{/if}
          <span></span><button type="button" on:click={() => dispatch('close')}>Cancel</button>
          {#if workspace.role !== 'viewer'}<button class="primary" disabled={busy || !statusId}>{busy ? 'Saving…' : 'Save task'}</button>{/if}
        </footer>
      </form>
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

  .block-action {
    color: #8a4d36;
  }

  .block-action.active {
    border-color: #d8b5a6;
    background: #fff4ee;
  }

  .parent-picker > input {
    margin-bottom: .45rem;
  }

  .new-tags {
    display: block;
    margin-top: .85rem;
  }

  @media (max-width: 600px) {
    .quick-action span {
      display: none;
    }

    .quick-action {
      width: 2.1rem;
      justify-content: center;
      padding: 0;
    }
  }
</style>
