<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { ApiError, api } from '../api/client';
  import type { Member, Tag, Task, TaskInput, TaskSummary, Workspace } from '../api/types';
  import { formatDateTime } from '../format';
  import DateTimeInput from './DateTimeInput.svelte';
  import MarkdownEditor from './MarkdownEditor.svelte';
  import TagPicker from './TagPicker.svelte';
  import TagBadge from './TagBadge.svelte';
  import AppButton from './AppButton.svelte';
  import TextField from './TextField.svelte';
  import NumberField from './NumberField.svelte';
  import TaskSearchSelect from './TaskSearchSelect.svelte';
  import BlockSummary from './BlockSummary.svelte';

  export let workspace: Workspace;
  export let taskId = 0;
  export let initialTitle = '';
  export let initialDescription = '';
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
  export let draftSubmitLabel = '';
  export let draftBusyLabel = 'Saving…';
  export let cancelLabel = 'Cancel';

  let selectedWorkspace = workspace;

  const dispatch = createEventDispatcher<{
    submit: TaskInput;
    draft: TaskInput;
    cancel: void;
    openTask: number;
    toggleSubtask: TaskSummary;
    createRelated: { kind: 'parent' | 'child' | 'blocks'; title: string };
    attachChild: TaskSummary;
    detachChild: TaskSummary;
    blockTarget: TaskSummary;
  }>();

  let tags: Tag[] = [];
  let members: Member[] = [];
  let parentTasks: Task[] = [];

  let title = initialTitle;
  let description = initialDescription;
  let priority = initialPriority;
  let dueDate = initialDueDate;
  let lastWorked = initialLastWorked;
  let parentTaskId = initialParentTaskId;
  let assigneeIds = [...initialAssigneeIds];
  let assigneeOpen = false;
  let tagIds = [...initialTagIds];
  let suggestedNewTags = normalizedTagNames(initialNewTags);
  let loading = true;
  let creatingTag = false;
  let createdParentId = 0;
  let localError = '';
  let optionLoadToken = 0;
  const selections = new Map<number, {
    assigneeIds: number[];
    tagIds: number[];
    parentTaskId: number;
  }>();

  $: completedSubtasks = taskDetails?.subtasks.filter((subtask) => !!subtask.finished_at).length || 0;
  $: selectedMembers = members.filter((member) => assigneeIds.includes(member.user_id));
  $: selectedParent = parentTasks.find((item) => item.id === parentTaskId)
    || (taskDetails?.parent_task?.id === parentTaskId ? taskDetails.parent_task : null);

  export function selectCreatedParent(created: Task) {
    parentTasks = [...parentTasks, created];
    parentTaskId = created.id;
  }

  export async function refreshRelatedTasks() {
    parentTasks = await api.tasks(selectedWorkspace.id, { finished: false });
  }

  function toggleAssignee(userId: number) {
    assigneeIds = assigneeIds.includes(userId)
      ? assigneeIds.filter((id) => id !== userId)
      : [...assigneeIds, userId];
  }

  function memberInitial(member: Member): string {
    return (member.display_name || member.email).trim().slice(0, 1).toUpperCase();
  }

  async function loadOptions(target: Workspace, switching = false): Promise<boolean> {
    const token = ++optionLoadToken;
    if (switching) {
      selections.set(selectedWorkspace.id, {
        assigneeIds: [...assigneeIds],
        tagIds: [...tagIds],
        parentTaskId
      });
    }
    loading = true;
    localError = '';
    try {
      const [loadedTags, loadedMembers, loadedParents] = await Promise.all([
        api.tags(target.id),
        api.members(target.id),
        api.tasks(target.id, { finished: false })
      ]);
      if (token !== optionLoadToken) return false;
      tags = loadedTags;
      members = loadedMembers;
      parentTasks = loadedParents;
      selectedWorkspace = target;
      const saved = selections.get(target.id);
      if (saved) {
        assigneeIds = saved.assigneeIds;
        tagIds = saved.tagIds;
        parentTaskId = saved.parentTaskId;
      } else if (switching) {
        assigneeIds = assigneeIds.filter((id) => members.some((member) => member.user_id === id));
        tagIds = [];
        parentTaskId = 0;
        assigneeOpen = false;
      }
      return true;
    } catch (reason) {
      if (token !== optionLoadToken) return false;
      localError = reason instanceof Error ? reason.message : 'Could not load task options';
      return false;
    } finally {
      if (token === optionLoadToken) loading = false;
    }
  }

  export async function switchWorkspace(target: Workspace): Promise<boolean> {
    if (target.id === selectedWorkspace.id) return true;
    if (target.role === 'viewer' || busy || creatingTag) return false;
    return loadOptions(target, true);
  }

  onMount(() => {
    void loadOptions(workspace);
  });

  function normalizeTagName(value: string): string {
    return value.trim();
  }

  function normalizedTagNames(value: string): string[] {
    const values = value
      .split(/[\n,]+/)
      .map(normalizeTagName)
      .filter(Boolean);
    return [...new Set(values)];
  }

  async function createAndSelectTag(input: {
    name: string;
    parent_tag_id: number | null;
    color: string;
    asParent?: boolean;
  }) {
    const name = input.name.trim();
    if (!name || creatingTag) return;
    creatingTag = true;
    localError = '';
    try {
      let created: Tag;
      try {
        created = await api.createTag(selectedWorkspace.id, {
          name,
          color: input.color,
          parent_tag_id: input.parent_tag_id
        });
      } catch (reason) {
        if (!(reason instanceof ApiError) || reason.status !== 409) throw reason;
        tags = await api.tags(selectedWorkspace.id);
        const concurrent = tags.find((tag) => tag.name.toLowerCase() === name.toLowerCase());
        if (!concurrent) throw reason;
        created = concurrent;
        if (
          input.parent_tag_id &&
          !created.parents.some((parent) => parent.id === input.parent_tag_id)
        ) {
          created = await api.addTagParent(selectedWorkspace.id, created.id, input.parent_tag_id);
        }
      }

      tags = await api.tags(selectedWorkspace.id);
      if (input.asParent) createdParentId = created.id;
      else if (!tagIds.includes(created.id)) tagIds = [...tagIds, created.id];
      suggestedNewTags = suggestedNewTags.filter((suggestion) => suggestion.toLowerCase() !== name.toLowerCase());
    } catch (reason) {
      localError = reason instanceof Error ? reason.message : 'Could not create tag';
    } finally {
      creatingTag = false;
    }
  }

  function taskInput(): TaskInput {
    return {
      workspace_id: selectedWorkspace.id,
      title,
      description: description || null,
      priority,
      due_date: dueDate || null,
      last_worked_at: lastWorked ? new Date(lastWorked).toISOString() : null,
      parent_task_id: parentTaskId || null,
      assignee_ids: assigneeIds,
      tag_ids: tagIds
    };
  }

  function submit() {
    localError = '';
    dispatch('submit', taskInput());
  }

  function saveDraft() {
    localError = '';
    dispatch('draft', taskInput());
  }
</script>

{#if loading}
  <p class="empty">Loading task editor…</p>
{:else}
  <form class="shared-task-form" on:submit|preventDefault={submit}>
    {#if taskDetails?.active_blocks.length}
      <BlockSummary blocks={taskDetails.active_blocks} on:openTask={(event) => dispatch('openTask', event.detail)} />
    {/if}
    <div class="title-row">
      <label>Title<TextField bind:value={title} maxlength="500" required disabled={selectedWorkspace.role === 'viewer'} /></label>
    </div>

    <div class="metadata-row">
      <label>Priority<NumberField bind:value={priority} min="1" disabled={selectedWorkspace.role === 'viewer'} /></label>
      <label>Due date<DateTimeInput bind:value={dueDate} disabled={selectedWorkspace.role === 'viewer'} /></label>
      <label>Last worked<DateTimeInput includeTime bind:value={lastWorked} disabled={selectedWorkspace.role === 'viewer'} /></label>
    </div>

    <section class="tags-section">
      <span class="field-label">Direct tags</span>
      <TagPicker
        {tags}
        selectedIds={tagIds}
        suggestedNames={suggestedNewTags}
        disabled={selectedWorkspace.role === 'viewer'}
        creating={creatingTag}
        bind:createdParentId
        on:change={(event) => (tagIds = event.detail)}
        on:create={(event) => void createAndSelectTag(event.detail)}
      />
      {#if selectedWorkspace.id === taskDetails?.workspace_id && taskDetails?.inherited_tags.length}
        <details class="inherited-tags" open>
          <summary>{taskDetails.inherited_tags.length} inherited {taskDetails.inherited_tags.length === 1 ? 'tag' : 'tags'}</summary>
          <div class="inherited-tag-list">
            {#each taskDetails.inherited_tags as tag}
              <TagBadge {tag} inherited />
            {/each}
          </div>
        </details>
      {/if}
    </section>

    <MarkdownEditor bind:value={description} disabled={selectedWorkspace.role === 'viewer'} compact />

    <section class="assignee-section">
      <span class="field-label">Assignees</span>
      <div class="assignee-picker">
        <button
          type="button"
          class="assignee-control"
          disabled={selectedWorkspace.role === 'viewer'}
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

        {#if assigneeOpen && selectedWorkspace.role !== 'viewer'}
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

    <section class="hierarchy-panel" aria-label="Relations">
      <span class="field-label">Relations</span>

      <div class="relation-group">
        <strong>Parent</strong>
        {#if parentTaskId}
          <div class="relation-row">
            <button type="button" class="relation-link" on:click={() => dispatch('openTask', parentTaskId)}>{selectedParent?.title || 'Parent task'} #{parentTaskId}</button>
            {#if selectedWorkspace.role !== 'viewer'}<AppButton disabled={busy} on:click={() => (parentTaskId = 0)}>Remove parent</AppButton>{/if}
          </div>
        {:else}
          <TaskSearchSelect
            tasks={parentTasks}
            excludeIds={[taskId, ...(taskDetails?.subtasks.map((child) => child.id) || [])]}
            placeholder="Search task to add as parent..."
            disabled={selectedWorkspace.role === 'viewer' || busy}
            on:select={(event) => (parentTaskId = event.detail.id)}
            on:create={(event) => dispatch('createRelated', { kind: 'parent', title: event.detail })}
          />
        {/if}
      </div>

      <div class="relation-group">
        <strong>Children {#if taskDetails?.subtasks.length}<small>{completedSubtasks} / {taskDetails.subtasks.length} complete</small>{/if}</strong>
        {#each taskDetails?.subtasks || [] as subtask (subtask.id)}
          <div class:finished={!!subtask.finished_at} class="subtask-row">
            {#if selectedWorkspace.role !== 'viewer'}
              <button type="button" class="subtask-toggle" class:finished={!!subtask.finished_at} disabled={busy || creatingTag} aria-label={subtask.finished_at ? `Reopen ${subtask.title}` : `Finish ${subtask.title}`} on:click={() => dispatch('toggleSubtask', subtask)}>{subtask.finished_at ? '✓' : '○'}</button>
            {:else}
              <span class="subtask-state" aria-hidden="true">{subtask.finished_at ? '✓' : '○'}</span>
            {/if}
            <button type="button" class="subtask-open" on:click={() => dispatch('openTask', subtask.id)}>{subtask.title}</button>
            <small>#{subtask.id}</small>
            {#if selectedWorkspace.role !== 'viewer'}<AppButton className="relation-remove" disabled={busy} on:click={() => dispatch('detachChild', subtask)}>Remove</AppButton>{/if}
          </div>
        {/each}
        {#if taskId && selectedWorkspace.role !== 'viewer'}
          <TaskSearchSelect
            tasks={parentTasks}
            excludeIds={[taskId, ...(taskDetails?.subtasks.map((child) => child.id) || [])]}
            placeholder="Search task to add as child..."
            disabled={busy}
            on:select={(event) => dispatch('attachChild', event.detail)}
            on:create={(event) => dispatch('createRelated', { kind: 'child', title: event.detail })}
          />
        {/if}
      </div>

      <div class="relation-group">
        <strong>Blocks</strong>
        {#each taskDetails?.blocks_tasks || [] as blocked (blocked.id)}
          <div class="block-row"><span aria-hidden="true">→</span><button type="button" class="relation-link" on:click={() => dispatch('openTask', blocked.id)}>{blocked.title} #{blocked.id}</button></div>
        {/each}
        {#if taskId && selectedWorkspace.role !== 'viewer'}
          <TaskSearchSelect
            tasks={parentTasks}
            excludeIds={[taskId, ...(taskDetails?.blocks_tasks.map((blocked) => blocked.id) || [])]}
            placeholder="Search task to block..."
            disabled={busy}
            on:select={(event) => dispatch('blockTarget', event.detail)}
            on:create={(event) => dispatch('createRelated', { kind: 'blocks', title: event.detail })}
          />
        {/if}
      </div>
      {#if !taskId}<small class="relation-hint">Save this task to add children or task blockers.</small>{/if}
    </section>

    {#if taskDetails}
      <section class="detail-panel compact-details">
        <dl>
          <div><dt>Creator</dt><dd>{taskDetails.creator.display_name}</dd></div>
          <div><dt>Created</dt><dd>{formatDateTime(taskDetails.created_at)}</dd></div>
          {#if taskDetails.finished_at}<div><dt>Finished</dt><dd>{formatDateTime(taskDetails.finished_at)}</dd></div>{/if}
        </dl>
      </section>
    {/if}

    {#if localError || error}<p class="error" role="alert">{localError || error}</p>{/if}
    <footer class="editor-actions">
      <span></span>
      <AppButton disabled={busy || creatingTag} on:click={() => dispatch('cancel')}>{cancelLabel}</AppButton>
      {#if selectedWorkspace.role !== 'viewer' && draftSubmitLabel}
        <AppButton disabled={busy || creatingTag || !title.trim()} on:click={saveDraft}>{busy || creatingTag ? draftBusyLabel : draftSubmitLabel}</AppButton>
      {/if}
      {#if selectedWorkspace.role !== 'viewer'}<AppButton type="submit" variant="primary" disabled={busy || creatingTag || !title.trim()}>{busy || creatingTag ? busyLabel : submitLabel}</AppButton>{/if}
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
    grid-template-columns: .65fr 1fr 1.25fr;
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

  .subtask-row {
    display: flex;
    align-items: center;
  }

  .relation-group { display: grid; gap: .35rem; border-top: 1px solid #e6e1d7; padding-top: .5rem; }
  .relation-group:first-of-type { border-top: 0; padding-top: 0; }
  .relation-group > strong { display: flex; gap: .4rem; align-items: baseline; font-size: .82rem; }
  .relation-group small, .relation-hint { color: var(--muted); font-size: .72rem; }
  .relation-row, .block-row { display: flex; align-items: center; gap: .5rem; }
  .relation-link { border: 0; background: transparent; color: var(--forest-2); padding: .2rem 0; text-align: left; font: inherit; font-weight: 700; }
  .relation-link:hover { text-decoration: underline; }

  .subtask-row {
    display: grid;
    grid-template-columns: 1.55rem minmax(0, 1fr) auto auto;
    gap: .35rem;
    border-radius: .4rem;
    padding: .18rem .3rem;
  }

  .subtask-row:hover { background: #f0eee7; }
  .subtask-row.finished { color: var(--muted); }
  .subtask-row small { color: var(--muted); font-size: .7rem; }
  .subtask-row :global(.relation-remove) { min-height: 1.55rem; padding: .2rem .45rem; font-size: .7rem; }

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

  .inherited-tags { color: var(--muted); font-size: .72rem; }
  .inherited-tags summary { width: fit-content; cursor: pointer; color: var(--forest-2); font-weight: 700; }
  .inherited-tag-list { display: flex; flex-wrap: wrap; gap: .3rem; margin-top: .35rem; }
  .compact-details { margin-top: 0; padding-top: .5rem; }
  .compact-details dl { display: flex; flex-wrap: wrap; gap: .4rem 1.1rem; }
  .compact-details dl > div { display: flex; grid-template-columns: none; gap: .35rem; padding: 0; font-size: .75rem; }


  .editor-actions {
    bottom: -1rem;
    grid-template-columns: 1fr repeat(3, auto);
    margin: .65rem -1rem -1rem;
    padding: .7rem 1rem;
  }

  @media (max-width: 800px) {
    .metadata-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  }

  @media (max-width: 600px) {
    .metadata-row { grid-template-columns: 1fr; }
    .editor-actions { bottom: -.75rem; margin: .6rem -.75rem -.75rem; padding: .65rem .75rem; }
  }
</style>
