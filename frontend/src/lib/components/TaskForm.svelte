<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { ApiError, api } from '../api/client';
  import type { Member, Status, Tag, Task, TaskInput, Workspace } from '../api/types';
  import Markdown from './Markdown.svelte';

  export let workspace: Workspace;
  export let taskId = 0;
  export let initialTitle = '';
  export let initialDescription = '';
  export let initialStatusId = 0;
  export let initialPriority = 1;
  export let initialDueDate = '';
  export let initialLastWorked = '';
  export let initialParentTaskId = 0;
  export let initialAssigneeIds: number[] = [];
  export let initialTagIds: number[] = [];
  export let initialNewTags = '';
  export let taskDetails: Task | null = null;
  export let allowDelete = false;
  export let busy = false;
  export let error = '';
  export let submitLabel = 'Save task';
  export let busyLabel = 'Saving…';
  export let cancelLabel = 'Cancel';

  const dispatch = createEventDispatcher<{ submit: TaskInput; cancel: void; delete: void }>();

  let statuses: Status[] = [];
  let tags: Tag[] = [];
  let members: Member[] = [];
  let parentTasks: Task[] = [];
  let filteredParentTasks: Task[] = [];

  let title = initialTitle;
  let description = initialDescription;
  let statusId = initialStatusId;
  let priority = initialPriority;
  let dueDate = initialDueDate;
  let lastWorked = initialLastWorked;
  let parentTaskId = initialParentTaskId;
  let parentSearch = '';
  let parentOpen = false;
  let parentDirty = false;
  let assigneeIds = [...initialAssigneeIds];
  let tagIds = [...initialTagIds];
  let newTags = initialNewTags;
  let mobileTab: 'edit' | 'preview' = 'edit';
  let loading = true;
  let resolving = false;
  let localError = '';

  $: {
    const candidates = parentTasks.filter((item) => item.id !== taskId);
    const needle = parentSearch.trim().toLowerCase();
    filteredParentTasks = parentDirty && needle
      ? candidates.filter((item) => item.title.toLowerCase().includes(needle))
      : candidates;
  }

  function parentOptionLabel(item: Task): string {
    return `${item.title} (#${item.id})`;
  }

  function focusParent(event: FocusEvent) {
    parentOpen = true;
    parentDirty = false;
    (event.currentTarget as HTMLInputElement).select();
  }

  function filterParents(value: string) {
    parentSearch = value;
    parentDirty = true;
    parentTaskId = 0;
    parentOpen = true;
  }

  function chooseParent(item: Task | null) {
    parentTaskId = item?.id || 0;
    parentSearch = item ? parentOptionLabel(item) : '';
    parentDirty = false;
    parentOpen = false;
  }

  function closeParent() {
    parentOpen = false;
    if (!parentDirty) return;
    const selected = parentTasks.find((item) => item.id === parentTaskId);
    parentSearch = selected ? parentOptionLabel(selected) : '';
    parentDirty = false;
  }

  onMount(async () => {
    try {
      [statuses, tags, members, parentTasks] = await Promise.all([
        api.statuses(workspace.id),
        api.tags(workspace.id),
        api.members(workspace.id),
        api.tasks(workspace.id, { finished: false })
      ]);

      if (!statuses.some((item) => item.id === statusId)) statusId = statuses[0]?.id || 0;

      if (parentTaskId) {
        let parent = parentTasks.find((item) => item.id === parentTaskId);
        if (!parent) {
          try {
            parent = await api.task(parentTaskId);
          } catch {
            parent = undefined;
          }
        }
        parentSearch = parent ? parentOptionLabel(parent) : '';
      }
    } catch (reason) {
      localError = reason instanceof Error ? reason.message : 'Could not load task options';
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

  async function submit() {
    resolving = true;
    localError = '';
    try {
      dispatch('submit', {
        title,
        description: description || null,
        status_id: statusId,
        priority,
        due_date: dueDate || null,
        last_worked_at: lastWorked ? new Date(lastWorked).toISOString() : null,
        parent_task_id: parentTaskId || null,
        assignee_ids: assigneeIds,
        tag_ids: await resolveTagIds()
      });
    } catch (reason) {
      localError = reason instanceof Error ? reason.message : 'Could not prepare task';
    } finally {
      resolving = false;
    }
  }
</script>

{#if loading}
  <p class="empty">Loading task editor…</p>
{:else}
  <form class="shared-task-form" on:submit|preventDefault={submit}>
    <div class="form-grid">
      <label class="wide">Title<input bind:value={title} maxlength="500" required disabled={workspace.role === 'viewer'} /></label>
      <label>Status<select bind:value={statusId} disabled={workspace.role === 'viewer'}>{#each statuses as item}<option value={item.id}>{item.name}</option>{/each}</select></label>
      <label>Priority<input type="number" bind:value={priority} min="1" disabled={workspace.role === 'viewer'} /></label>
      <label>Due date<input type="date" bind:value={dueDate} disabled={workspace.role === 'viewer'} /></label>
      <label>Last worked<input type="datetime-local" bind:value={lastWorked} disabled={workspace.role === 'viewer'} /></label>

      <div class="wide parent-field">
        <label for="task-parent-search">Parent task</label>
        <div class="parent-combobox">
          <input
            id="task-parent-search"
            type="text"
            value={parentSearch}
            placeholder="No parent"
            autocomplete="off"
            role="combobox"
            aria-autocomplete="list"
            aria-controls="parent-task-options"
            aria-expanded={parentOpen}
            disabled={workspace.role === 'viewer'}
            on:focus={focusParent}
            on:input={(event) => filterParents(event.currentTarget.value)}
            on:blur={closeParent}
          />
          {#if parentOpen && workspace.role !== 'viewer'}
            <div id="parent-task-options" class="parent-options" role="listbox">
              <button type="button" class:selected={!parentTaskId} on:mousedown|preventDefault={() => chooseParent(null)}>No parent</button>
              {#each filteredParentTasks as item (item.id)}
                <button type="button" class:selected={item.id === parentTaskId} on:mousedown|preventDefault={() => chooseParent(item)}>{item.title}</button>
              {/each}
              {#if !filteredParentTasks.length}<span class="parent-empty">No matching tasks</span>{/if}
            </div>
          {/if}
        </div>
      </div>
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
      <label class="new-tags">Add new tags<input bind:value={newTags} placeholder="errands, home, project-x" /><span class="help">Comma- or newline-separated. New tags are created and assigned when you save.</span></label>
    </fieldset>

    {#if taskDetails}
      <section class="detail-panel">
        <dl><div><dt>Creator</dt><dd>{taskDetails.creator.display_name}</dd></div><div><dt>Created</dt><dd>{new Date(taskDetails.created_at).toLocaleString()}</dd></div><div><dt>Finished</dt><dd>{taskDetails.finished_at ? new Date(taskDetails.finished_at).toLocaleString() : 'Not finished'}</dd></div></dl>
        {#if taskDetails.current_block}<div class="blocked-reason"><strong>Currently blocked:</strong> {taskDetails.current_block.reason}</div>{/if}
        {#if taskDetails.subtasks.length}<h3>Subtasks</h3><ul>{#each taskDetails.subtasks as subtask}<li>{subtask.finished_at ? '✓' : '○'} {subtask.title}</li>{/each}</ul>{/if}
      </section>
    {/if}

    {#if localError || error}<p class="error" role="alert">{localError || error}</p>{/if}
    <footer class="editor-actions">
      {#if allowDelete}<button type="button" class="danger" disabled={busy || resolving} on:click={() => dispatch('delete')}>Delete</button>{/if}
      <span></span>
      <button type="button" disabled={busy || resolving} on:click={() => dispatch('cancel')}>{cancelLabel}</button>
      {#if workspace.role !== 'viewer'}<button class="primary" disabled={busy || resolving || !statusId || !title.trim()}>{busy || resolving ? busyLabel : submitLabel}</button>{/if}
    </footer>
  </form>
{/if}

<style>
  .shared-task-form { display: grid; gap: 1rem; }
  .parent-field > label { display: block; margin-bottom: .35rem; }
  .parent-combobox { position: relative; }
  .parent-options { position: absolute; z-index: 8; top: calc(100% + .25rem); left: 0; right: 0; max-height: 15rem; overflow: auto; border: 1px solid #cbc8be; border-radius: .55rem; background: #fff; box-shadow: 0 12px 28px rgba(20, 27, 23, .16); padding: .3rem; }
  .parent-options button { display: block; width: 100%; border: 0; border-radius: .4rem; background: transparent; color: var(--ink); padding: .5rem .6rem; text-align: left; font: inherit; }
  .parent-options button:hover, .parent-options button.selected { background: #f0eee7; }
  .parent-empty { display: block; padding: .55rem .6rem; color: var(--muted); font-size: .85rem; }
  .new-tags { display: block; margin-top: .85rem; }
</style>
