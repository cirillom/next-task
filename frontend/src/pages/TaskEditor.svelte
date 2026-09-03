<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { Member, Status, Tag, Task, TaskInput, Workspace } from '../lib/api/types';
  import Markdown from '../lib/components/Markdown.svelte';

  export let workspace: Workspace;
  export let taskId = 0;
  const dispatch = createEventDispatcher<{ close: void; saved: Task; deleted: number }>();

  let task: Task | null = null;
  let statuses: Status[] = [];
  let tags: Tag[] = [];
  let members: Member[] = [];
  let parentTasks: Task[] = [];
  let title = '';
  let description = '';
  let statusId = 0;
  let priority = 1;
  let dueDate = '';
  let lastWorked = '';
  let parentTaskId = 0;
  let assigneeIds: number[] = [];
  let tagIds: number[] = [];
  let mobileTab: 'edit' | 'preview' = 'edit';
  let loading = true;
  let busy = false;
  let error = '';

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

  async function save() {
    busy = true;
    error = '';
    const input: TaskInput = {
      title,
      description: description || null,
      status_id: statusId,
      priority,
      due_date: dueDate || null,
      last_worked_at: lastWorked ? new Date(lastWorked).toISOString() : null,
      parent_task_id: parentTaskId || null,
      assignee_ids: assigneeIds,
      tag_ids: tagIds
    };
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
</script>

<div class="modal-backdrop" role="presentation" on:click|self={() => dispatch('close')}>
  <div class="task-editor" role="dialog" aria-modal="true" aria-labelledby="task-editor-title">
    <header class="editor-header">
      <div><p class="eyebrow">{taskId ? 'Task details' : 'Create task'}</p><h1 id="task-editor-title">{taskId ? title || 'Task' : 'New task'}</h1></div>
      <button class="icon-button" aria-label="Close" on:click={() => dispatch('close')}>×</button>
    </header>

    {#if loading}<p class="empty">Loading editor…</p>{:else}
      <form on:submit|preventDefault={save}>
        <div class="form-grid">
          <label class="wide">Title<input bind:value={title} maxlength="500" required disabled={workspace.role === 'viewer'} /></label>
          <label>Status<select bind:value={statusId} disabled={workspace.role === 'viewer'}>{#each statuses as item}<option value={item.id}>{item.name}</option>{/each}</select></label>
          <label>Priority<input type="number" bind:value={priority} min="1" disabled={workspace.role === 'viewer'} /></label>
          <label>Due date<input type="date" bind:value={dueDate} disabled={workspace.role === 'viewer'} /></label>
          <label>Last worked<input type="datetime-local" bind:value={lastWorked} disabled={workspace.role === 'viewer'} /></label>
          <label class="wide">Parent task<select bind:value={parentTaskId} disabled={workspace.role === 'viewer'}><option value={0}>No parent</option>{#each parentTasks.filter((item) => item.id !== taskId) as item}<option value={item.id}>{item.title}</option>{/each}</select></label>
        </div>

        <div class="mobile-tabs"><button type="button" class:active={mobileTab === 'edit'} on:click={() => (mobileTab = 'edit')}>Edit</button><button type="button" class:active={mobileTab === 'preview'} on:click={() => (mobileTab = 'preview')}>Preview</button></div>
        <div class="markdown-editor">
          <label class:hidden-mobile={mobileTab !== 'edit'}>Description (Markdown)<textarea bind:value={description} rows="14" disabled={workspace.role === 'viewer'} placeholder="Add details, links, lists, tables, or code…"></textarea></label>
          <section class:hidden-mobile={mobileTab !== 'preview'} class="preview"><span class="field-label">Preview</span>{#if description}<Markdown source={description} />{:else}<p class="muted">Nothing to preview yet.</p>{/if}</section>
        </div>

        <fieldset disabled={workspace.role === 'viewer'}><legend>Assignees</legend><div class="choice-grid">{#each members as member}<label><input type="checkbox" value={member.user_id} bind:group={assigneeIds} /> {member.display_name}</label>{/each}</div></fieldset>
        <fieldset disabled={workspace.role === 'viewer'}><legend>Direct tags</legend><div class="choice-grid">{#each tags as tag}<label><input type="checkbox" value={tag.id} bind:group={tagIds} /> #{tag.name}</label>{/each}</div></fieldset>

        {#if task}
          <section class="detail-panel">
            <dl><div><dt>Creator</dt><dd>{task.creator.display_name}</dd></div><div><dt>Created</dt><dd>{new Date(task.created_at).toLocaleString()}</dd></div><div><dt>Finished</dt><dd>{task.finished_at ? new Date(task.finished_at).toLocaleString() : 'Not finished'}</dd></div></dl>
            {#if task.current_block}<div class="blocked-reason"><strong>Currently blocked:</strong> {task.current_block.reason}</div>{/if}
            {#if task.subtasks.length}<h3>Subtasks</h3><ul>{#each task.subtasks as subtask}<li>{subtask.finished_at ? '✓' : '○'} {subtask.title}</li>{/each}</ul>{/if}
            {#if task.blocking_history.length}<h3>Blocking history</h3><ul class="history">{#each task.blocking_history as block}<li><strong>{block.reason}</strong><span>{new Date(block.blocked_at).toLocaleString()} → {block.unblocked_at ? new Date(block.unblocked_at).toLocaleString() : 'active'}</span></li>{/each}</ul>{/if}
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
