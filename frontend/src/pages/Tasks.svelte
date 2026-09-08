<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { Member, Status, Tag, Task, Workspace } from '../lib/api/types';
  import TaskCard from '../lib/components/TaskCard.svelte';

  type FinishedFilter = 'unfinished' | 'finished' | 'all';
  type BlockedFilter = 'all' | 'blocked' | 'unblocked';
  type SortField = 'score' | 'finished_at' | 'last_worked_at' | 'due_date' | 'created_at';
  type SortDirection = 'asc' | 'desc';

  export let workspace: Workspace;
  const dispatch = createEventDispatcher<{ openTask: number }>();

  let tasks: Task[] = [];
  let statuses: Status[] = [];
  let tags: Tag[] = [];
  let members: Member[] = [];
  let search = '';
  let finishedFilter: FinishedFilter = 'all';
  let blockedFilter: BlockedFilter = 'all';
  let statusFilter = '';
  let tagFilter = '';
  let assigneeFilter = '';
  let sortField: SortField = 'score';
  let sortDirection: SortDirection = 'desc';
  let error = '';
  let loading = true;
  let searchTimer: number;

  function taskParams(finished: boolean) {
    return {
      finished,
      search,
      status_id: statusFilter ? Number(statusFilter) : null,
      tag_id: tagFilter ? Number(tagFilter) : null,
      assignee_id: assigneeFilter ? Number(assigneeFilter) : null,
      blocked:
        blockedFilter === 'all'
          ? null
          : blockedFilter === 'blocked'
            ? true
            : false
    };
  }

  async function loadTasks(): Promise<Task[]> {
    if (finishedFilter === 'all') {
      const [unfinished, finished] = await Promise.all([
        api.tasks(workspace.id, taskParams(false)),
        api.tasks(workspace.id, taskParams(true))
      ]);
      return [...unfinished, ...finished];
    }

    const finished = finishedFilter === 'finished';
    return api.tasks(workspace.id, taskParams(finished));
  }

  function timestampValue(value: string | null): number | null {
    if (!value) return null;
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? null : parsed;
  }

  function comparableValue(task: Task, field: SortField): number | null {
    switch (field) {
      case 'score':
        return task.ranking_score;
      case 'finished_at':
        return timestampValue(task.finished_at);
      case 'last_worked_at':
        return timestampValue(task.last_worked_at);
      case 'due_date':
        return timestampValue(task.due_date);
      case 'created_at':
        return timestampValue(task.created_at);
    }
  }

  function compareValues(
    a: Task,
    b: Task,
    field: SortField,
    directionValue: SortDirection
  ): number {
    const aValue = comparableValue(a, field);
    const bValue = comparableValue(b, field);

    if (aValue === null && bValue === null) return a.id - b.id;
    if (aValue === null) return 1;
    if (bValue === null) return -1;

    const direction = directionValue === 'asc' ? 1 : -1;
    if (aValue !== bValue) return (aValue - bValue) * direction;

    if (field === 'score' && a.score !== b.score) {
      return (a.score - b.score) * direction;
    }
    return a.id - b.id;
  }

  function scoreOrdered(source: Task[], direction: SortDirection): Task[] {
    const ids = new Set(source.map((task) => task.id));
    const byId = new Map(source.map((task) => [task.id, task]));
    const descendantsByTask = new Map<number, Set<number>>();

    for (const task of source) descendantsByTask.set(task.id, new Set());
    for (const task of source) {
      let parentId = task.parent_task_id;
      const visited = new Set<number>();
      while (parentId !== null && ids.has(parentId) && !visited.has(parentId)) {
        visited.add(parentId);
        if (!task.finished_at) descendantsByTask.get(parentId)?.add(task.id);
        parentId = byId.get(parentId)?.parent_task_id ?? null;
      }
    }

    const remaining = new Map(source.map((task) => [task.id, task]));
    const ordered: Task[] = [];
    while (remaining.size) {
      const remainingIds = new Set(remaining.keys());
      const available = [...remaining.values()].filter((task) => {
        if (task.finished_at) return true;
        const descendants = descendantsByTask.get(task.id);
        return !descendants || ![...descendants].some((id) => remainingIds.has(id));
      });
      const candidates = available.length ? available : [...remaining.values()];
      candidates.sort((a, b) => compareValues(a, b, 'score', direction));
      const chosen = candidates[0];
      ordered.push(chosen);
      remaining.delete(chosen.id);
    }
    return ordered;
  }

  function orderedTaskList(
    source: Task[],
    field: SortField,
    direction: SortDirection
  ): Task[] {
    if (field === 'score') return scoreOrdered(source, direction);
    return [...source].sort((a, b) => compareValues(a, b, field, direction));
  }

  $: orderedTasks = orderedTaskList(tasks, sortField, sortDirection);

  async function load() {
    loading = true;
    error = '';
    try {
      [statuses, tags, members, tasks] = await Promise.all([
        api.statuses(workspace.id),
        api.tags(workspace.id),
        api.members(workspace.id),
        loadTasks()
      ]);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load tasks';
    } finally {
      loading = false;
    }
  }

  async function refreshTasks() {
    error = '';
    try {
      tasks = await loadTasks();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not refresh tasks';
    }
  }

  function searchSoon() {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(refreshTasks, 250);
  }

  function toggleSortDirection() {
    sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
  }

  onMount(load);
</script>

<div class="page-heading">
  <div><p class="eyebrow">Browse and search</p><h1>Tasks</h1></div>
  {#if workspace.role !== 'viewer'}<button class="primary" on:click={() => dispatch('openTask', 0)}>+ New task</button>{/if}
</div>

<section class="filter-bar tasks-toolbar">
  <label class="search-field">Search<input type="search" bind:value={search} on:input={searchSoon} placeholder="Title or description" /></label>

  <label>
    Completion
    <select bind:value={finishedFilter} on:change={refreshTasks}>
      <option value="all">All</option>
      <option value="unfinished">Unfinished</option>
      <option value="finished">Finished</option>
    </select>
  </label>

  <label>
    Assignee
    <select bind:value={assigneeFilter} on:change={refreshTasks}>
      <option value="">All</option>
      {#each members as member (member.user_id)}
        <option value={String(member.user_id)}>{member.display_name}</option>
      {/each}
    </select>
  </label>

  <label>
    Blocked
    <select bind:value={blockedFilter} on:change={refreshTasks}>
      <option value="all">All</option>
      <option value="blocked">Blocked</option>
      <option value="unblocked">Not blocked</option>
    </select>
  </label>

  <label>
    Status
    <select bind:value={statusFilter} on:change={refreshTasks}>
      <option value="">All</option>
      {#each statuses as status (status.id)}
        <option value={String(status.id)}>{status.name}</option>
      {/each}
    </select>
  </label>

  <label>
    Tag
    <select bind:value={tagFilter} on:change={refreshTasks}>
      <option value="">All</option>
      {#each tags as tag (tag.id)}
        <option value={String(tag.id)}>{tag.name}</option>
      {/each}
    </select>
  </label>

  <label>
    Order by
    <select bind:value={sortField}>
      <option value="score">Score</option>
      <option value="finished_at">Done date</option>
      <option value="last_worked_at">Last worked</option>
      <option value="due_date">Due date</option>
      <option value="created_at">Creation date</option>
    </select>
  </label>

  <button
    type="button"
    class="sort-direction"
    aria-label={sortDirection === 'asc' ? 'Sort ascending; click for descending' : 'Sort descending; click for ascending'}
    title={sortDirection === 'asc' ? 'Ascending' : 'Descending'}
    on:click={toggleSortDirection}
  >
    <span aria-hidden="true">{sortDirection === 'asc' ? '↑' : '↓'}</span>
    {sortDirection === 'asc' ? 'Ascending' : 'Descending'}
  </button>
</section>

{#if error}<p class="error">{error}</p>{/if}
{#if loading}<p class="empty">Loading tasks…</p>{:else if !orderedTasks.length}<p class="empty">No matching tasks.</p>{/if}
<div class="task-list">
  {#each orderedTasks as task (task.id)}
    <TaskCard
      {task}
      {statuses}
      readOnly={workspace.role === 'viewer'}
      on:changed={() => void refreshTasks()}
      on:open={(event) => dispatch('openTask', event.detail)}
      on:error={(event) => (error = event.detail)}
    />
  {/each}
</div>

<style>
  .tasks-toolbar {
    display: grid;
    grid-template-columns: minmax(12rem, 2fr) repeat(6, minmax(8rem, 1fr)) auto;
    align-items: end;
    gap: .6rem;
  }

  .tasks-toolbar label {
    min-width: 0;
  }

  .tasks-toolbar select,
  .tasks-toolbar input {
    width: 100%;
  }

  .sort-direction {
    display: inline-flex;
    height: 2.55rem;
    align-items: center;
    justify-content: center;
    gap: .35rem;
    border: 1px solid #cbc8be;
    border-radius: .5rem;
    background: #fff;
    color: var(--ink);
    padding: 0 .65rem;
    white-space: nowrap;
  }

  .sort-direction:hover {
    background: #f7f5ef;
  }

  @media (max-width: 1100px) {
    .tasks-toolbar {
      grid-template-columns: repeat(4, minmax(8rem, 1fr));
    }

    .search-field {
      grid-column: span 2;
    }
  }

  @media (max-width: 640px) {
    .tasks-toolbar {
      grid-template-columns: 1fr 1fr;
    }

    .search-field {
      grid-column: 1 / -1;
    }

    .sort-direction {
      width: 100%;
    }
  }
</style>
