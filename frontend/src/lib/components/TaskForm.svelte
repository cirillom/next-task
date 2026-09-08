<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { ApiError, api } from '../api/client';
  import type { Member, Status, Tag, Task, TaskInput, TaskSummary, Workspace } from '../api/types';
  import { formatDateTime } from '../format';
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

  const dispatch = createEventDispatcher<{
    submit: TaskInput;
    cancel: void;
    delete: void;
    openTask: number;
    toggleSubtask: TaskSummary;
  }>();

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

  $: completedSubtasks = taskDetails?.subtasks.filter((subtask) => !!subtask.finished_at).length || 0;

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
    parentSearch = '';
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
    <div class="form-grid compact-grid">
      <label class="title-field">Title<input bind:value={title} maxlength="500" required disabled={workspace.role === 'viewer'} /></label>
      <label>Status<select bind:value={statusId} disabled={workspace.role === 'viewer'}>{#each statuses as item}<option value={item.id}>{item.name}</option>{/each}</select></label>
      <label>Priority<input type="number" bind:value={priority} min="1" disabled={workspace.role === 'viewer'} /></label>
      <label>Due date<input type="date" lang="pt-BR" bind:value={dueDate} disabled={workspace.role === 'viewer'} /></label>
      <label>Last worked<input type="datetime-local" lang="pt-BR" bind:value={lastWorked} disabled={workspace.role === 'viewer'} /></label>

      <div class="parent-field">
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
                <button type="button" class:selected={item.id === parentTaskId} on:mousedown|preventDefault={() => chooseParent(item)}>{parentOptionLabel(item)}</button>
              {/each}
              {#if !filteredParentTasks.length}<span class="parent-empty">No matching tasks</span>{/if}
            </div>
          {/if}
        </div>
      </div>
    </div>

    {#if taskDetails && (taskDetails.parent_task || taskDetails.subtasks.length)}
      <section class="hierarchy-panel" aria-label="Task hierarchy">
        {#if taskDetails.parent_task}
          <div class="hierarchy-section">
            <span class="field-label">Parent</span>
            <button
              type="button"
              class="hierarchy-parent"
              on:click={() => dispatch('openTask', taskDetails!.parent_task!.id)}
            >
              <span aria-hidden="true">↳</span>
              <strong>{taskDetails.parent_task.title}</strong>
              <small>#{taskDetails.parent_task.id}</small>
            </button>
          </div>
        {/if}

        {#if taskDetails.subtasks.length}
          <div class="hierarchy-section">
            <div class="subtask-heading">
              <span class="field-label">Subtasks</span>
              <small>{completedSubtasks} / {taskDetails.subtasks.length} complete</small>
            </div>
            <div class="subtask-list">
              {#each taskDetails.subtasks as subtask (subtask.id)}
                <div class:finished={!!subtask.finished_at} class="subtask-row">
                  {#if workspace.role !== 'viewer'}
                    <button
                      type="button"
                      class="subtask-toggle"
                      class:finished={!!subtask.finished_at}
                      disabled={busy || resolving}
                      aria-label={subtask.finished_at ? `Reopen ${subtask.title}` : `Finish ${subtask.title}`}
                      title={subtask.finished_at ? 'Reopen subtask' : 'Finish subtask'}
                      on:click={() => dispatch('toggleSubtask', subtask)}
                    >
                      {subtask.finished_at ? '✓' : '○'}
                    </button>
                  {:else}
                    <span class="subtask-state" aria-hidden="true">{subtask.finished_at ? '✓' : '○'}</span>
                  {/if}
                  <button
                    type="button"
                    class="subtask-open"
                    on:click={() => dispatch('openTask', subtask.id)}
                  >{subtask.title}</button>
                  <small>#{subtask.id}</small>
                </div>
              {/each}
            </div>
          </div>
        {/if}
      </section>
    {/if}

    <div class="mobile-tabs"><button type="button" class:active={mobileTab === 'edit'} on:click={() => (mobileTab = 'edit')}>Edit</button><button type="button" class:active={mobileTab === 'preview'} on:click={() => (mobileTab = 'preview')}>Preview</button></div>
    <div class="markdown-editor compact-markdown">
      <label class:hidden-mobile={mobileTab !== 'edit'}>Description (Markdown)<textarea bind:value={description} rows="8" disabled={workspace.role === 'viewer'} placeholder="Add details, links, lists, tables, or code…"></textarea></label>
      <section class:hidden-mobile={mobileTab !== 'preview'} class="preview"><span class="field-label">Preview</span>{#if description}<Markdown source={description} />{:else}<p class="muted">Nothing to preview yet.</p>{/if}</section>
    </div>

    <div class="options-grid">
      <fieldset disabled={workspace.role === 'viewer'}><legend>Assignees</legend><div class="choice-grid">{#each members as member}<label><input type="checkbox" value={member.user_id} bind:group={assigneeIds} /> {member.display_name}</label>{/each}</div></fieldset>
      <fieldset disabled={workspace.role === 'viewer'}>
        <legend>Direct tags</legend>
        <div class="choice-grid">{#each tags as tag}<label><input type="checkbox" value={tag.id} bind:group={tagIds} /> #{tag.name}</label>{/each}</div>
        <label class="new-tags">Add new tags<input bind:value={newTags} placeholder="errands, home, project-x" /></label>
      </fieldset>
    </div>

    {#if taskDetails}
      <section class="detail-panel compact-details">
        <dl><div><dt>Creator</dt><dd>{taskDetails.creator.display_name}</dd></div><div><dt>Created</dt><dd>{formatDateTime(taskDetails.created_at)}</dd></div><div><dt>Finished</dt><dd>{taskDetails.finished_at ? formatDateTime(taskDetails.finished_at) : 'Not finished'}</dd></div></dl>
        {#if taskDetails.current_block}<div class="blocked-reason"><strong>Currently blocked:</strong> {taskDetails.current_block.reason}</div>{/if}
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
  .shared-task-form {
    display: grid;
    gap: .65rem;
  }

  .shared-task-form :global(input),
  .shared-task-form :global(select),
  .shared-task-form :global(textarea) {
    padding: .5rem .6rem;
  }

  .compact-grid {
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: .55rem;
  }

  .title-field { grid-column: span 2; }
  .parent-field { grid-column: span 2; }
  .parent-field > label { display: block; margin-bottom: .35rem; }
  .parent-combobox { position: relative; }
  .parent-options { position: absolute; z-index: 8; top: calc(100% + .25rem); left: 0; right: 0; max-height: 15rem; overflow: auto; border: 1px solid #cbc8be; border-radius: .55rem; background: #fff; box-shadow: 0 12px 28px rgba(20, 27, 23, .16); padding: .3rem; }
  .parent-options button { display: block; width: 100%; border: 0; border-radius: .4rem; background: transparent; color: var(--ink); padding: .5rem .6rem; text-align: left; font: inherit; }
  .parent-options button:hover, .parent-options button.selected { background: #f0eee7; }
  .parent-empty { display: block; padding: .55rem .6rem; color: var(--muted); font-size: .85rem; }
  .new-tags { display: block; margin-top: .55rem; }

  .hierarchy-panel {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    gap: .75rem 1rem;
    align-items: start;
    border: 1px solid var(--line);
    border-radius: .65rem;
    background: #faf9f4;
    padding: .65rem .75rem;
  }

  .hierarchy-section {
    display: grid;
    gap: .3rem;
    min-width: 0;
  }

  .hierarchy-parent {
    display: inline-flex;
    width: fit-content;
    max-width: 100%;
    align-items: baseline;
    gap: .35rem;
    border: 0;
    background: transparent;
    color: var(--forest-2);
    padding: 0;
    font: inherit;
    text-align: left;
  }

  .hierarchy-parent:hover,
  .subtask-open:hover {
    text-decoration: underline;
    text-underline-offset: .14rem;
  }

  .hierarchy-parent small,
  .subtask-row small,
  .subtask-heading small {
    color: var(--muted);
    font-size: .72rem;
    font-weight: 650;
  }

  .subtask-heading {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: .75rem;
  }

  .subtask-list {
    display: grid;
    gap: .18rem;
  }

  .subtask-row {
    display: grid;
    grid-template-columns: 1.55rem minmax(0, 1fr) auto;
    align-items: center;
    gap: .35rem;
    border-radius: .4rem;
    padding: .18rem .3rem;
  }

  .subtask-row:hover { background: #f0eee7; }
  .subtask-row.finished { color: var(--muted); }

  .subtask-toggle {
    display: grid;
    width: 1.45rem;
    height: 1.45rem;
    place-items: center;
    border: 1px solid #9bb0a3;
    border-radius: 50%;
    background: #fff;
    color: var(--forest-2);
    padding: 0;
    font-size: .8rem;
    font-weight: 900;
  }

  .subtask-toggle.finished {
    border-color: var(--forest);
    background: var(--forest);
    color: #fff;
  }

  .subtask-open {
    min-width: 0;
    overflow: hidden;
    border: 0;
    background: transparent;
    color: inherit;
    padding: .2rem 0;
    font: inherit;
    text-align: left;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .subtask-state { color: var(--forest-2); font-weight: 850; }

  .compact-markdown {
    gap: .65rem;
    margin-top: 0;
  }

  .compact-markdown textarea {
    min-height: 10rem;
  }

  .compact-markdown .preview {
    max-height: 14rem;
    min-height: 10rem;
  }

  .options-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: .65rem;
  }

  .options-grid fieldset {
    min-width: 0;
    margin: 0;
    padding: .65rem;
  }

  .options-grid .choice-grid {
    gap: .35rem .55rem;
  }

  .compact-details {
    margin-top: 0;
    padding-top: .55rem;
  }

  .compact-details dl {
    display: flex;
    flex-wrap: wrap;
    gap: .5rem 1.2rem;
  }

  .compact-details dl > div {
    display: flex;
    grid-template-columns: none;
    gap: .4rem;
    padding: 0;
    font-size: .78rem;
  }

  .editor-actions {
    bottom: -1rem;
    margin: .65rem -1rem -1rem;
    padding: .7rem 1rem;
  }

  @media (max-width: 800px) {
    .compact-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .title-field,
    .parent-field { grid-column: 1 / -1; }
    .hierarchy-panel,
    .options-grid { grid-template-columns: 1fr; }
  }

  @media (max-width: 600px) {
    .compact-grid { grid-template-columns: 1fr; }
    .title-field,
    .parent-field { grid-column: auto; }
    .editor-actions { bottom: -.75rem; margin: .6rem -.75rem -.75rem; padding: .65rem .75rem; }
  }
</style>
