<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { Member, Status, Tag, Task, Workspace } from '../lib/api/types';
  import PomodoroLauncher from '../lib/components/PomodoroLauncher.svelte';
  import TaskCard from '../lib/components/TaskCard.svelte';

  export let workspace: Workspace;
  const dispatch = createEventDispatcher<{ openTask: number; startFocus: number | null }>();

  let tasks: Task[] = [];
  let statuses: Status[] = [];
  let tags: Tag[] = [];
  let members: Member[] = [];
  let statusId = '';
  let tagId = '';
  let assigneeId = '';
  let blocked = 'false';
  let error = '';
  let loading = true;
  let refreshTimer: number;

  async function loadOptions() {
    [statuses, tags, members] = await Promise.all([
      api.statuses(workspace.id),
      api.tags(workspace.id),
      api.members(workspace.id)
    ]);
  }

  async function loadTasks(showLoading = true) {
    if (showLoading) loading = true;
    error = '';
    try {
      tasks = await api.tasks(workspace.id, {
        finished: false,
        status_id: statusId,
        tag_id: tagId,
        assignee_id: assigneeId,
        blocked
      });
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load tasks';
    } finally {
      if (showLoading) loading = false;
    }
  }

  function matchesBlockedFilter(task: Task): boolean {
    if (blocked === '') return true;
    return blocked === 'true' ? Boolean(task.current_block) : !task.current_block;
  }

  function replaceTask(updated: Task) {
    tasks = tasks
      .filter((task) => (!updated.finished_at && matchesBlockedFilter(updated)) || task.id !== updated.id)
      .map((task) => (task.id === updated.id ? updated : task))
      .sort((a, b) => b.score - a.score || a.id - b.id);
  }

  onMount(() => {
    void (async () => {
      try {
        await loadOptions();
        await loadTasks();
      } catch (reason) {
        error = reason instanceof Error ? reason.message : 'Could not load workspace';
        loading = false;
      }
    })();

    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') void loadTasks(false);
    };
    refreshTimer = window.setInterval(refreshWhenVisible, 60_000);
    document.addEventListener('visibilitychange', refreshWhenVisible);

    return () => {
      window.clearInterval(refreshTimer);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
    };
  });
</script>

<div class="page-heading">
  <div><p class="eyebrow">Ranked for you</p><h1>Next task</h1></div>
  {#if workspace.role !== 'viewer'}<button class="primary" on:click={() => dispatch('openTask', 0)}>+ New task</button>{/if}
</div>

<PomodoroLauncher {tags} on:start={(event) => dispatch('startFocus', event.detail)} />

<section class="filter-bar" aria-label="Task filters">
  <label>Status<select bind:value={statusId} on:change={() => loadTasks()}><option value="">All</option>{#each statuses as item}<option value={item.id}>{item.name}</option>{/each}</select></label>
  <label>Tag<select bind:value={tagId} on:change={() => loadTasks()}><option value="">All</option>{#each tags as item}<option value={item.id}>#{item.name}</option>{/each}</select></label>
  <label>Assignee<select bind:value={assigneeId} on:change={() => loadTasks()}><option value="">Anyone</option>{#each members as item}<option value={item.user_id}>{item.display_name}</option>{/each}</select></label>
  <label>Blocked<select bind:value={blocked} on:change={() => loadTasks()}><option value="false">Not blocked</option><option value="true">Blocked</option><option value="">Either</option></select></label>
</section>

{#if error}<p class="error" role="alert">{error}</p>{/if}
{#if loading}
  <p class="empty">Ranking your tasks…</p>
{:else if tasks.length === 0}
  <section class="empty"><strong>Nothing is waiting here.</strong><span>Adjust the filters or add a task.</span></section>
{:else}
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
{/if}
