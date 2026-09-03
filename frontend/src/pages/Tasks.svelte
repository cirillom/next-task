<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { Status, Task, Workspace } from '../lib/api/types';
  import TaskCard from '../lib/components/TaskCard.svelte';

  export let workspace: Workspace;
  const dispatch = createEventDispatcher<{ openTask: number }>();
  let tasks: Task[] = [];
  let statuses: Status[] = [];
  let search = '';
  let showFinished = false;
  let error = '';
  let loading = true;
  let searchTimer: number;

  async function load() {
    loading = true;
    error = '';
    try {
      [statuses, tasks] = await Promise.all([
        api.statuses(workspace.id),
        api.tasks(workspace.id, { finished: showFinished, search })
      ]);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load tasks';
    } finally {
      loading = false;
    }
  }

  function searchSoon() {
    window.clearTimeout(searchTimer);
    searchTimer = window.setTimeout(load, 250);
  }

  function replaceTask(updated: Task) {
    if (Boolean(updated.finished_at) !== showFinished) {
      tasks = tasks.filter((task) => task.id !== updated.id);
    } else {
      tasks = tasks.map((task) => (task.id === updated.id ? updated : task));
    }
  }

  onMount(load);
</script>

<div class="page-heading">
  <div><p class="eyebrow">Browse and search</p><h1>Tasks</h1></div>
  {#if workspace.role !== 'viewer'}<button class="primary" on:click={() => dispatch('openTask', 0)}>+ New task</button>{/if}
</div>

<section class="filter-bar tasks-toolbar">
  <label class="search-field">Search<input type="search" bind:value={search} on:input={searchSoon} placeholder="Title or description" /></label>
  <label>Show<select bind:value={showFinished} on:change={load}><option value={false}>Unfinished</option><option value={true}>Finished</option></select></label>
</section>

{#if error}<p class="error">{error}</p>{/if}
{#if loading}<p class="empty">Loading tasks…</p>{:else if !tasks.length}<p class="empty">No matching tasks.</p>{/if}
<div class="task-list">
  {#each tasks as task (task.id)}
    <TaskCard
      {task}
      {statuses}
      readOnly={workspace.role === 'viewer'}
      on:changed={(event) => replaceTask(event.detail)}
      on:open={(event) => dispatch('openTask', event.detail)}
      on:error={(event) => (error = event.detail)}
    />
  {/each}
</div>

