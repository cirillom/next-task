<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { ApiError, api } from '../api/client';
  import type { Member, Status, Tag, Task, TaskInput, TaskSummary, Workspace } from '../api/types';
  import { formatDateTime } from '../format';
  import MarkdownEditor from './MarkdownEditor.svelte';

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
  export let busy = false;
  export let error = '';
  export let submitLabel = 'Save task';
  export let busyLabel = 'Saving…';
  export let cancelLabel = 'Cancel';

  const dispatch = createEventDispatcher<{
    submit: TaskInput;
    cancel: void;
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
  let assigneeOpen = false;
  let tagIds = [...initialTagIds];
  let newTags = initialNewTags;
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
  $: selectedMembers = members.filter((member) => assigneeIds.includes(member.user_id));

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

  function toggleAssignee(userId: number) {
    assigneeIds = assigneeIds.includes(userId)
      ? assigneeIds.filter((id) => id !== userId)
      : [...assigneeIds, userId];
  }

  function toggleTag(tagId: number) {
    tagIds = tagIds.includes(tagId)
      ? tagIds.filter((id) => id !== tagId)
      : [...tagIds, tagId];
  }

  function memberInitial(member: Member): string {
    return (member.display_name || member.email).trim().slice(0, 1).toUpperCase();
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
    <div class="title-row">
      <label>Title<input bind:value={title} maxlength="500" required disabled={workspace.role === 'viewer'} /></label>
    </div>

    <div class="metadata-row">
      <label>Status<select bind:value={statusId} disabled={workspace.role === 'viewer'}>{#each statuses as item}<option value={item.id}>{item.name}</option>{/each}</select></label>
      <label>Priority<input type="number" bind:value={priority} min="1" disabled={workspace.role === 'viewer'} /></label>
      <label>Due date<input type="date" lang="pt-BR" bind:value={dueDate} disabled={workspace.role === 'viewer'} /></label>
      <label>Last worked<input type="datetime-local" lang="pt-BR" bind:value={lastWorked} disabled={workspace.role === 'viewer'} /></label>
    </div>

    <section class="hierarchy-panel" aria-label="Task hierarchy">
      <div class="hierarchy-header">
        <div>
          <span class="field-label">Task hierarchy</span>
          {#if taskDetails?.subtasks.length}
            <small>{completedSubtasks} / {taskDetails.subtasks.length} direct subtasks complete</small>
          {/if}
        </div>
        {#if taskDetails?.parent_task}
          <button type="button" class="parent-jump" on:click={() => dispatch('openTask', taskDetails!.parent_task!.id)}>
            Open parent #{taskDetails.parent_task.id}
          </button>
        {/if}
      </div>

      <div class="parent-field">
        <span class="field-label">Parent</span>
        <div class="parent-combobox">
          <input
            id="task-parent-search"
            type="text"
            value={parentSearch}
            placeholder="No parent task"
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

      {#if taskDetails?.subtasks.length}
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
                >{subtask.finished_at ? '✓' : '○'}</button>
              {:else}
                <span class="subtask-state" aria-hidden="true">{subtask.finished_at ? '✓' : '○'}</span>
              {/if}
              <button type="button" class="subtask-open" on:click={() => dispatch('openTask', subtask.id)}>{subtask.title}</button>
              <small>#{subtask.id}</small>
            </div>
          {/each}
        </div>
      {/if}
    </section>

    <MarkdownEditor bind:value={description} disabled={workspace.role === 'viewer'} compact />

    <section class="assignee-section">
      <span class="field-label">Assignees</span>
      <div class="assignee-picker">
        <button
          type="button"
          class="assignee-control"
          disabled={workspace.role === 'viewer'}
          aria-expanded={assigneeOpen}
          on:click={() => (assigneeOpen = !assigneeOpen)}
        >
          <span class="selected-assignees">
            {#if selectedMembers.length === 0}
              <span class="unassigned">Unassigned</span>
            {:else}
              {#each selectedMembers as member (member.user_id)}
                <span class="assignee-pill"><span class="avatar">{memberInitial(member)}</span>{member.display_name}</span>
              {/each}
            {/if}
          </span>
          <span class="picker-caret" aria-hidden="true">⌄</span>
        </button>

        {#if assigneeOpen && workspace.role !== 'viewer'}
          <div class="assignee-menu">
            <div class="picker-menu-title">Assign people</div>
            {#each members as member (member.user_id)}
              <button type="button" class:selected={assigneeIds.includes(member.user_id)} on:click={() => toggleAssignee(member.user_id)}>
                <span class="menu-check">{assigneeIds.includes(member.user_id) ? '✓' : ''}</span>
                <span class="avatar">{memberInitial(member)}</span>
                <span class="member-copy"><strong>{member.display_name}</strong><small>{member.email}</small></span>
              </button>
            {/each}
          </div>
        {/if}
      </div>
    </section>

    <section class="tags-section">
      <span class="field-label">Direct tags</span>
      <div class="tags-line">
        {#each tags as tag (tag.id)}
          <button
            type="button"
            class:selected={tagIds.includes(tag.id)}
            style:--tag-color={tag.color || '#73847c'}
            disabled={workspace.role === 'viewer'}
            on:click={() => toggleTag(tag.id)}
          >#{tag.name}</button>
        {/each}
        {#if workspace.role !== 'viewer'}
          <input bind:value={newTags} aria-label="Add new tags" placeholder="+ new tags" />
        {/if}
      </div>
    </section>

    {#if taskDetails}
      <section class="detail-panel compact-details">
        <dl>
          <div><dt>Creator</dt><dd>{taskDetails.creator.display_name}</dd></div>
          <div><dt>Created</dt><dd>{formatDateTime(taskDetails.created_at)}</dd></div>
          {#if taskDetails.finished_at}<div><dt>Finished</dt><dd>{formatDateTime(taskDetails.finished_at)}</dd></div>{/if}
        </dl>
        {#if taskDetails.current_block}<div class="blocked-reason"><strong>Currently blocked:</strong> {taskDetails.current_block.reason}</div>{/if}

        {#if taskDetails.blocking_history.length}
          <details class="block-history">
            <summary>Blocking history <span>{taskDetails.blocking_history.length}</span></summary>
            <ol>
              {#each taskDetails.blocking_history as block (block.id)}
                <li>
                  <div><strong>{block.reason}</strong>{#if taskDetails.current_block?.id === block.id}<span class="active-block">Active</span>{/if}</div>
                  <small>Blocked {formatDateTime(block.blocked_at)}{block.unblocked_at ? ` · Unblocked ${formatDateTime(block.unblocked_at)}` : ''}</small>
                </li>
              {/each}
            </ol>
          </details>
        {/if}
      </section>
    {/if}

    {#if localError || error}<p class="error" role="alert">{localError || error}</p>{/if}
    <footer class="editor-actions">
      <span></span>
      <button type="button" disabled={busy || resolving} on:click={() => dispatch('cancel')}>{cancelLabel}</button>
      {#if workspace.role !== 'viewer'}<button class="primary" disabled={busy || resolving || !statusId || !title.trim()}>{busy || resolving ? busyLabel : submitLabel}</button>{/if}
    </footer>
  </form>
{/if}

<style>
  .shared-task-form { display: grid; gap: .65rem; }

  .shared-task-form :global(input),
  .shared-task-form :global(select),
  .shared-task-form :global(textarea) { padding: .5rem .6rem; }

  .title-row label { width: 100%; }

  .metadata-row {
    display: grid;
    grid-template-columns: 1.2fr .65fr 1fr 1.25fr;
    gap: .55rem;
  }

  .hierarchy-panel {
    display: grid;
    gap: .55rem;
    border: 1px solid var(--line);
    border-radius: .65rem;
    background: #faf9f4;
    padding: .65rem .75rem;
  }

  .hierarchy-header,
  .parent-field,
  .subtask-row {
    display: flex;
    align-items: center;
  }

  .hierarchy-header { justify-content: space-between; gap: .75rem; }
  .hierarchy-header > div { display: flex; align-items: baseline; gap: .6rem; min-width: 0; }
  .hierarchy-header small { color: var(--muted); font-size: .72rem; }

  .parent-jump {
    border: 0;
    background: transparent;
    color: var(--forest-2);
    padding: 0;
    font-size: .72rem;
    font-weight: 750;
  }

  .parent-jump:hover { text-decoration: underline; text-underline-offset: .14rem; }

  .parent-field { gap: .65rem; }
  .parent-field > .field-label { flex: 0 0 4rem; }
  .parent-combobox { position: relative; flex: 1; min-width: 0; }

  .parent-options {
    position: absolute;
    z-index: 8;
    top: calc(100% + .25rem);
    left: 0;
    right: 0;
    max-height: 15rem;
    overflow: auto;
    border: 1px solid #cbc8be;
    border-radius: .55rem;
    background: #fff;
    box-shadow: 0 12px 28px rgba(20, 27, 23, .16);
    padding: .3rem;
  }

  .parent-options button { display: block; width: 100%; border: 0; border-radius: .4rem; background: transparent; color: var(--ink); padding: .5rem .6rem; text-align: left; font: inherit; }
  .parent-options button:hover, .parent-options button.selected { background: #f0eee7; }
  .parent-empty { display: block; padding: .55rem .6rem; color: var(--muted); font-size: .85rem; }

  .subtask-list { display: grid; gap: .14rem; border-top: 1px solid #e6e1d7; padding-top: .45rem; }

  .subtask-row {
    display: grid;
    grid-template-columns: 1.55rem minmax(0, 1fr) auto;
    gap: .35rem;
    border-radius: .4rem;
    padding: .18rem .3rem;
  }

  .subtask-row:hover { background: #f0eee7; }
  .subtask-row.finished { color: var(--muted); }
  .subtask-row small { color: var(--muted); font-size: .7rem; }

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

  .subtask-toggle.finished { border-color: var(--forest); background: var(--forest); color: #fff; }

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

  .subtask-open:hover { text-decoration: underline; text-underline-offset: .14rem; }
  .subtask-state { color: var(--forest-2); font-weight: 850; }

  .assignee-section,
  .tags-section { display: grid; gap: .3rem; }

  .assignee-picker { position: relative; }

  .assignee-control {
    display: flex;
    width: 100%;
    min-height: 2.35rem;
    align-items: center;
    justify-content: space-between;
    gap: .5rem;
    border: 1px solid #cfcbbf;
    border-radius: .55rem;
    background: #fff;
    color: var(--ink);
    padding: .3rem .45rem;
    text-align: left;
  }

  .selected-assignees { display: flex; min-width: 0; flex-wrap: wrap; align-items: center; gap: .3rem; }
  .unassigned { color: var(--muted); font-size: .8rem; padding: 0 .15rem; }

  .assignee-pill {
    display: inline-flex;
    align-items: center;
    gap: .3rem;
    border-radius: 999px;
    background: #eef2ef;
    padding: .18rem .45rem .18rem .2rem;
    font-size: .75rem;
    font-weight: 650;
  }

  .avatar {
    display: inline-grid;
    width: 1.45rem;
    height: 1.45rem;
    flex: 0 0 1.45rem;
    place-items: center;
    border-radius: 50%;
    background: #dfe8e2;
    color: var(--forest-2);
    font-size: .66rem;
    font-weight: 850;
  }

  .picker-caret { color: var(--muted); }

  .assignee-menu {
    position: absolute;
    z-index: 9;
    top: calc(100% + .3rem);
    left: 0;
    width: min(100%, 24rem);
    max-height: 16rem;
    overflow: auto;
    border: 1px solid #cbc8be;
    border-radius: .6rem;
    background: #fff;
    box-shadow: 0 14px 34px rgba(20, 27, 23, .18);
    padding: .3rem;
  }

  .picker-menu-title { border-bottom: 1px solid #ebe7dd; padding: .45rem .5rem; color: var(--muted); font-size: .72rem; font-weight: 800; }

  .assignee-menu button {
    display: grid;
    width: 100%;
    grid-template-columns: 1rem 1.45rem minmax(0, 1fr);
    align-items: center;
    gap: .45rem;
    border: 0;
    border-radius: .4rem;
    background: transparent;
    color: var(--ink);
    padding: .4rem .45rem;
    text-align: left;
  }

  .assignee-menu button:hover,
  .assignee-menu button.selected { background: #f2f3ef; }
  .menu-check { color: var(--forest-2); font-weight: 900; }
  .member-copy { display: grid; min-width: 0; }
  .member-copy small { overflow: hidden; color: var(--muted); font-size: .68rem; text-overflow: ellipsis; white-space: nowrap; }

  .tags-line {
    display: flex;
    min-height: 2.35rem;
    align-items: center;
    gap: .3rem;
    overflow-x: auto;
    border: 1px solid #cfcbbf;
    border-radius: .55rem;
    background: #fff;
    padding: .3rem .4rem;
  }

  .tags-line button {
    flex: 0 0 auto;
    border: 1px solid color-mix(in srgb, var(--tag-color) 30%, white);
    border-radius: 999px;
    background: color-mix(in srgb, var(--tag-color) 9%, white);
    color: color-mix(in srgb, var(--tag-color) 78%, black);
    padding: .18rem .45rem;
    font-size: .72rem;
  }

  .tags-line button.selected { background: color-mix(in srgb, var(--tag-color) 23%, white); font-weight: 800; }
  .tags-line input { width: 8rem; min-width: 8rem; flex: 1 0 8rem; border: 0; padding: .2rem .35rem; box-shadow: none; }
  .tags-line input:focus { outline: 0; }

  .compact-details { margin-top: 0; padding-top: .5rem; }
  .compact-details dl { display: flex; flex-wrap: wrap; gap: .4rem 1.1rem; }
  .compact-details dl > div { display: flex; grid-template-columns: none; gap: .35rem; padding: 0; font-size: .75rem; }

  .block-history { margin-top: .55rem; border-top: 1px solid #ebe7dd; padding-top: .45rem; }
  .block-history summary { color: var(--forest-2); cursor: pointer; font-size: .76rem; font-weight: 750; }
  .block-history summary span { color: var(--muted); font-weight: 650; }
  .block-history ol { display: grid; gap: .45rem; margin: .55rem 0 0; padding: 0; list-style: none; }
  .block-history li { border-left: 2px solid #d9d4c9; padding-left: .55rem; }
  .block-history li > div { display: flex; align-items: center; gap: .45rem; }
  .block-history li strong { font-size: .76rem; }
  .block-history li small { color: var(--muted); font-size: .68rem; }
  .active-block { border-radius: 999px; background: #f8e6dc; color: #7c3821; padding: .1rem .35rem; font-size: .62rem; font-weight: 800; }

  .editor-actions {
    bottom: -1rem;
    grid-template-columns: 1fr auto auto;
    margin: .65rem -1rem -1rem;
    padding: .7rem 1rem;
  }

  @media (max-width: 800px) {
    .metadata-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }

  @media (max-width: 600px) {
    .metadata-row { grid-template-columns: 1fr; }
    .parent-field { align-items: flex-start; flex-direction: column; gap: .25rem; }
    .parent-field > .field-label { flex-basis: auto; }
    .parent-combobox { width: 100%; }
    .hierarchy-header { align-items: flex-start; flex-direction: column; gap: .25rem; }
    .editor-actions { bottom: -.75rem; margin: .6rem -.75rem -.75rem; padding: .65rem .75rem; }
  }
</style>
