<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { NextScope, Tag, Task } from '../lib/api/types';
  import TaskCard from '../lib/components/TaskCard.svelte';
  import TagScopeFilters from '../lib/components/TagScopeFilters.svelte';
  import { emptyTagScope } from '../lib/tagScope';
  import AppButton from '../lib/components/AppButton.svelte';
  import TextField from '../lib/components/TextField.svelte';
  import ScoringWarning from '../lib/components/ScoringWarning.svelte';

  type FinishedFilter = 'unfinished' | 'finished' | 'all';
  type BlockedFilter = 'all' | 'blocked' | 'unblocked';
  type SortField = 'score' | 'finished_at' | 'last_worked_at' | 'due_date' | 'created_at';
  type SortDirection = 'asc' | 'desc';

  const dispatch = createEventDispatcher<{ openTask: number; createBlocker: { taskId: number; title: string } }>();

  let tasks: Task[] = [];
  let tags: Tag[] = [];
  let search = '';
  let finishedFilter: FinishedFilter = 'unfinished';
  let blockedFilter: BlockedFilter = 'all';
  let tagScope: NextScope = emptyTagScope();
  let sortField: SortField = 'score';
  let sortDirection: SortDirection = 'desc';
  let filtersOpen = false;
  let sortOpen = false;
  let error = '';
  let loading = true;
  let searchTimer: number;
  let taskRequest = 0;

  $: activeFilterCount = [
    finishedFilter !== 'unfinished',
    blockedFilter !== 'all',
    tagScope.include_tag_ids.length > 0,
    tagScope.exclude_tag_ids.length > 0
  ].filter(Boolean).length;

  function taskParams(finished: boolean) {
    return {
      finished,
      search,
      include_tag_id: tagScope.include_tag_ids,
      exclude_tag_id: tagScope.exclude_tag_ids,
      tag_match: tagScope.tag_match,
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
        api.tasks(taskParams(false)),
        api.tasks(taskParams(true))
      ]);
      return [...unfinished, ...finished];
    }

    const finished = finishedFilter === 'finished';
    return api.tasks(taskParams(finished));
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
    const request = ++taskRequest;
    loading = true;
    error = '';
    try {
      const [loadedTags, loadedTasks] = await Promise.all([
        api.tags(),
        loadTasks()
      ]);
      tags = loadedTags;
      if (request === taskRequest) tasks = loadedTasks;
    } catch (reason) {
      if (request === taskRequest) error = reason instanceof Error ? reason.message : 'Could not load tasks';
    } finally {
      if (request === taskRequest) loading = false;
    }
  }

  async function refreshTasks() {
    const request = ++taskRequest;
    error = '';
    try {
      const refreshed = await loadTasks();
      if (request === taskRequest) tasks = refreshed;
    } catch (reason) {
      if (request === taskRequest) error = reason instanceof Error ? reason.message : 'Could not refresh tasks';
    } finally {
      if (request === taskRequest) loading = false;
    }
  }

  function searchSoon() {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(refreshTasks, 250);
  }

  function toggleFilters() {
    filtersOpen = !filtersOpen;
    sortOpen = false;
  }

  function toggleSort() {
    sortOpen = !sortOpen;
    filtersOpen = false;
  }

  function closePopovers() {
    filtersOpen = false;
    sortOpen = false;
  }

  function clearFilters() {
    finishedFilter = 'unfinished';
    blockedFilter = 'all';
    tagScope = emptyTagScope();
    void refreshTasks();
  }

  function setTagScope(next: NextScope) {
    tagScope = next;
    void refreshTasks();
  }

  function setSortDirection(direction: SortDirection) {
    sortDirection = direction;
  }

  onMount(load);
</script>

<div class="page-heading">
  <div><p class="eyebrow">Browse and search</p><h1>Tasks</h1></div>
  <AppButton variant="primary" on:click={() => dispatch('openTask', 0)}>+ New task</AppButton>
</div>

<section class="filter-bar tasks-toolbar">
  <label class="search-field">
    Search
    <TextField type="search" bind:value={search} on:input={searchSoon} placeholder="Title or description" />
  </label>

  <div class="popover-control">
    <button
      type="button"
      class="toolbar-icon"
      class:active={filtersOpen || activeFilterCount > 0}
      aria-label="Filter tasks"
      aria-expanded={filtersOpen}
      title="Filter tasks"
      on:click={toggleFilters}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4" /></svg>
      {#if activeFilterCount > 0}<span class="filter-count">{activeFilterCount}</span>{/if}
    </button>

    {#if filtersOpen}
      <div class="toolbar-popover filter-popover" role="dialog" aria-label="Task filters">
        <div class="popover-header">
          <strong>Filters</strong>
          {#if activeFilterCount > 0}<button type="button" class="clear-button" on:click={clearFilters}>Clear</button>{/if}
        </div>

        <div class="filter-grid">
          <label>
            Completion
            <select bind:value={finishedFilter} on:change={refreshTasks}>
              <option value="all">All</option>
              <option value="unfinished">Unfinished</option>
              <option value="finished">Finished</option>
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


          <div class="tag-filter">
            <TagScopeFilters {tags} scope={tagScope} matchName="tasks-tag-match" on:change={(event) => setTagScope(event.detail)} />
          </div>
        </div>
      </div>
    {/if}
  </div>

  <div class="popover-control">
    <button
      type="button"
      class="toolbar-icon"
      class:active={sortOpen || sortField !== 'score' || sortDirection !== 'desc'}
      aria-label="Sort tasks"
      aria-expanded={sortOpen}
      title="Sort tasks"
      on:click={toggleSort}
    >
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M8 6h12M8 12h9M8 18h6" /><path d="m4 5-2 2 2 2M2 7h4" /></svg>
    </button>

    {#if sortOpen}
      <div class="toolbar-popover sort-popover" role="dialog" aria-label="Task sorting">
        <div class="popover-header"><strong>Sort</strong></div>
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

        <div class="direction-options" aria-label="Sort direction">
          <button
            type="button"
            class:active={sortDirection === 'asc'}
            on:click={() => setSortDirection('asc')}
          >↑ Ascending</button>
          <button
            type="button"
            class:active={sortDirection === 'desc'}
            on:click={() => setSortDirection('desc')}
          >↓ Descending</button>
        </div>
      </div>
    {/if}
  </div>
</section>

{#if filtersOpen || sortOpen}
  <button class="popover-backdrop" aria-label="Close task options" on:click={closePopovers}></button>
{/if}

{#if error}<p class="error">{error}</p>{/if}
<ScoringWarning message={tasks.find((task) => task.scoring_warning)?.scoring_warning ?? null} />
{#if loading}<p class="empty">Loading tasks…</p>{:else if !orderedTasks.length}<p class="empty">No matching tasks.</p>{/if}
<div class="task-list">
  {#each orderedTasks as task (task.id)}
    <TaskCard
      {task}

      on:changed={() => void refreshTasks()}
      on:open={(event) => dispatch('openTask', event.detail)}
      on:createBlocker={(event) => dispatch('createBlocker', event.detail)}
      on:error={(event) => (error = event.detail)}
    />
  {/each}
</div>

<style>
  .tasks-toolbar {
    position: relative;
    z-index: 21;
    display: flex;
    align-items: end;
    gap: .55rem;
  }

  .search-field {
    width: min(34rem, 100%);
    flex: 1 1 24rem;
  }

  .popover-control {
    position: relative;
    flex: 0 0 auto;
  }

  .toolbar-icon {
    position: relative;
    display: grid;
    width: 2.7rem;
    height: 2.55rem;
    place-items: center;
    border: 1px solid #cbc8be;
    border-radius: .55rem;
    background: #fff;
    color: var(--ink);
    padding: 0;
  }

  .toolbar-icon:hover,
  .toolbar-icon.active {
    border-color: var(--forest);
    background: #f5f8f5;
    color: var(--forest);
  }

  .toolbar-icon svg {
    width: 1.25rem;
    height: 1.25rem;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.9;
  }

  .filter-count {
    position: absolute;
    top: -.38rem;
    right: -.38rem;
    display: grid;
    min-width: 1.15rem;
    height: 1.15rem;
    place-items: center;
    border: 2px solid var(--paper);
    border-radius: 999px;
    background: var(--forest);
    color: #fff;
    padding: 0 .2rem;
    font-size: .62rem;
    font-weight: 800;
    line-height: 1;
  }

  .toolbar-popover {
    position: absolute;
    top: calc(100% + .5rem);
    right: 0;
    z-index: 23;
    border: 1px solid var(--line);
    border-radius: .75rem;
    background: var(--paper);
    box-shadow: 0 .75rem 2rem rgba(31, 37, 33, .16);
    padding: .85rem;
  }

  .filter-popover {
    width: min(30rem, calc(100vw - 2rem));
  }

  .sort-popover {
    width: min(20rem, calc(100vw - 2rem));
  }

  .popover-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .75rem;
    margin-bottom: .7rem;
  }

  .popover-header strong {
    font-size: .9rem;
  }

  .clear-button {
    border: 0;
    background: transparent;
    color: var(--forest-2);
    padding: .15rem .25rem;
    font-size: .75rem;
    font-weight: 750;
  }

  .clear-button:hover {
    text-decoration: underline;
    text-underline-offset: .12rem;
  }

  .filter-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: .65rem;
  }

  .filter-grid label,
  .sort-popover label {
    min-width: 0;
  }

  .filter-grid select,
  .sort-popover select {
    width: 100%;
  }

  .tag-filter {
    display: grid;
    grid-column: 1 / -1;
    gap: .4rem;
    border-top: 1px solid var(--line);
    padding-top: .65rem;
  }

  .direction-options {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: .45rem;
    margin-top: .7rem;
  }

  .direction-options button {
    border: 1px solid #cbc8be;
    border-radius: .5rem;
    background: #fff;
    color: var(--ink);
    padding: .6rem .55rem;
    font-size: .76rem;
    font-weight: 700;
  }

  .direction-options button:hover,
  .direction-options button.active {
    border-color: var(--forest);
    background: #f5f8f5;
    color: var(--forest);
  }

  .popover-backdrop {
    position: fixed;
    inset: 0;
    z-index: 20;
    border: 0;
    background: transparent;
    padding: 0;
    cursor: default;
  }

  @media (max-width: 640px) {
    .tasks-toolbar {
      align-items: end;
    }

    .search-field {
      min-width: 0;
    }

    .toolbar-popover {
      position: fixed;
      top: auto;
      right: 1rem;
      bottom: 1rem;
      left: 1rem;
      width: auto;
      max-height: calc(100vh - 2rem);
      overflow: auto;
    }

    .filter-grid {
      grid-template-columns: 1fr;
    }

    .tag-filter {
      grid-column: auto;
    }
  }
</style>
