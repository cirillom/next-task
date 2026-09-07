<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { Tag, Task, Workspace } from '../lib/api/types';
  import NextTaskCard from '../lib/components/NextTaskCard.svelte';
  import PomodoroLauncher from '../lib/components/PomodoroLauncher.svelte';
  import TaskQueue from '../lib/components/TaskQueue.svelte';

  export let workspace: Workspace;
  const dispatch = createEventDispatcher<{ openTask: number; startFocus: number | null }>();

  let tasks: Task[] = [];
  let tags: Tag[] = [];
  let sessionTagId: number | null = null;
  let error = '';
  let loading = true;
  let refreshTimer: number;

  async function loadTasks(showLoading = true) {
    if (showLoading) loading = true;
    error = '';
    try {
      tasks = await api.tasks(workspace.id, {
        finished: false,
        blocked: false,
        tag_id: sessionTagId
      });
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load tasks';
    } finally {
      if (showLoading) loading = false;
    }
  }

  async function changeSessionScope(tagId: number | null) {
    sessionTagId = tagId;
    await loadTasks();
  }

  function replaceTask(updated: Task) {
    if (updated.finished_at || updated.current_block) {
      tasks = tasks.filter((task) => task.id !== updated.id);
      return;
    }

    tasks = tasks
      .map((task) => (task.id === updated.id ? updated : task))
      .sort((a, b) => b.score - a.score || a.id - b.id);
  }

  onMount(() => {
    void (async () => {
      try {
        [tags] = await Promise.all([api.tags(workspace.id), loadTasks()]);
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

{#if error}<p class="error" role="alert">{error}</p>{/if}

{#if loading}
  <p class="empty">Ranking your tasks…</p>
{:else if tasks.length === 0}
  <section class="empty"><strong>Nothing actionable right now.</strong><span>Try another session tag, add a task, or check Tasks for blocked work.</span></section>
{:else}
  <section class="recommendation" aria-label="Recommended next task">
    <NextTaskCard
      task={tasks[0]}
      readOnly={workspace.role === 'viewer'}
      on:changed={(event) => replaceTask(event.detail)}
      on:open={(event) => dispatch('openTask', event.detail)}
      on:error={(event) => (error = event.detail)}
    />
  </section>
{/if}

<PomodoroLauncher
  {tags}
  recommendedTaskTitle={tasks[0]?.title || ''}
  on:scopeChange={(event) => changeSessionScope(event.detail)}
  on:start={(event) => dispatch('startFocus', event.detail)}
/>

{#if !loading && tasks.length > 1}
  <section class="queue" aria-label="Ranked task queue">
    <div class="queue__heading">
      <h2>Queue</h2>
      <span>{tasks.length - 1} more</span>
    </div>

    <TaskQueue
      tasks={tasks.slice(1)}
      startRank={2}
      on:open={(event) => dispatch('openTask', event.detail)}
    />
  </section>
{/if}

<style>
  .recommendation {
    margin-bottom: 1rem;
  }

  .queue {
    margin-top: 1.5rem;
    padding-top: 1.25rem;
    border-top: 1px solid var(--line);
  }

  .queue__heading {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: .75rem;
  }

  .queue__heading h2 {
    margin: 0;
    font-size: 1.15rem;
  }

  .queue__heading > span {
    color: var(--muted);
    font-size: .75rem;
    font-weight: 700;
  }
</style>
