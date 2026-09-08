<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { Status, Task, Workspace } from '../lib/api/types';
  import TaskCard from '../lib/components/TaskCard.svelte';

  type FinishedFilter = 'unfinished' | 'finished' | 'all';

  export let workspace: Workspace;
  const dispatch = createEventDispatcher<{ openTask: number }>();
  let tasks: Task[] = [];
  let statuses: Status[] = [];
  let search = '';
  let finishedFilter: FinishedFilter = 'all';
  let error = '';
  let loading = true;
  let searchTimer: number;

  async function loadTasks(): Promise<Task[]> {
    if (finishedFilter === 'all') {
      const [unfinished, finished] = await Promise.all([
        api.tasks(workspace.id, { finished: false, search }),
        api.tasks(workspace.id, { finished: true, search })
      ]);
      return [...unfinished, ...finished];
    }

    return api.tasks(workspace.id, {
      finished: finishedFilter === 'finished',
      search
    });
  }

  async function load() {
    loading = true;
    error = '';
    try {
      [statuses, tasks] = await Promise.all([
        api.statuses(workspace.id),
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
    searchTimer = window.setTimeout(load, 250);
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
    <select bind:value={finishedFilter} on:change={load}>
      <option value="all">All</option>
      <option value="unfinished">Unfinished</option>
      <option value="finished">Finished</option>
    </select>
  </label>
</section>

<p class="ranking-note" title="A parent task raises its unfinished descendants to at least its own ranking level. Descendants still keep their real score, and siblings at the same inherited level are ordered by their own score.">
  <span aria-hidden="true">ⓘ</span>
  <span><strong>Hierarchy-aware ranking:</strong> subtasks inherit their highest unfinished ancestor's ranking level; siblings at the same level stay ordered by their own score.</span>
</p>

{#if error}<p class="error">{error}</p>{/if}
{#if loading}<p class="empty">Loading tasks…</p>{:else if !tasks.length}<p class="empty">No matching tasks.</p>{/if}
<div class="task-list">
  {#each tasks as task (task.id)}
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
  .ranking-note {
    display: flex;
    align-items: flex-start;
    gap: .45rem;
    margin: -.25rem 0 1rem;
    color: var(--muted);
    font-size: .78rem;
    line-height: 1.45;
  }

  .ranking-note > span:first-child {
    flex: 0 0 auto;
    color: var(--forest-2);
    font-size: .9rem;
  }

  .ranking-note strong { color: #45514b; }
</style>
