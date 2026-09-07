<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { Tag, Task, Workspace } from '../lib/api/types';
  import NextTaskCard from '../lib/components/NextTaskCard.svelte';
  import PomodoroLauncher from '../lib/components/PomodoroLauncher.svelte';

  export let workspace: Workspace;
  const dispatch = createEventDispatcher<{ openTask: number; startFocus: number | null }>();

  let tasks: Task[] = [];
  let tags: Tag[] = [];
  let error = '';
  let loading = true;
  let refreshTimer: number;

  async function loadTasks(showLoading = true) {
    if (showLoading) loading = true;
    error = '';
    try {
      tasks = await api.tasks(workspace.id, {
        finished: false,
        blocked: false
      });
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load tasks';
    } finally {
      if (showLoading) loading = false;
    }
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
  <section class="empty"><strong>Nothing actionable right now.</strong><span>Add a task or check Tasks for blocked work.</span></section>
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

<PomodoroLauncher {tags} on:start={(event) => dispatch('startFocus', event.detail)} />

{#if !loading && tasks.length > 1}
  <section class="up-next" aria-label="Remaining ranked tasks">
    <div class="up-next__heading">
      <div><p class="eyebrow">Ranked queue</p><h2>Up next</h2></div>
      <span>{tasks.length - 1} more</span>
    </div>

    <div class="simple-task-list">
      {#each tasks.slice(1) as task (task.id)}
        <article class="simple-task-row">
          <button class="simple-task-title" on:click={() => dispatch('openTask', task.id)}>{task.title}</button>
          <div class="simple-task-meta">
            <span>Priority {task.priority}</span>
            <span>{task.status.name}</span>
            <span>Score {task.score.toFixed(1)}</span>
          </div>
        </article>
      {/each}
    </div>
  </section>
{/if}

<style>
  .recommendation {
    margin-bottom: 1rem;
  }

  .up-next {
    margin-top: 1.5rem;
    padding-top: 1.25rem;
    border-top: 1px solid var(--line);
  }

  .up-next__heading {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: .75rem;
  }

  .up-next__heading .eyebrow,
  .up-next__heading h2 {
    margin: 0;
  }

  .up-next__heading h2 {
    margin-top: .1rem;
    font-size: 1.15rem;
  }

  .up-next__heading > span {
    color: var(--muted);
    font-size: .75rem;
    font-weight: 700;
  }

  .simple-task-list {
    display: grid;
    gap: .45rem;
  }

  .simple-task-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    border: 1px solid rgba(100, 95, 80, .14);
    border-radius: .65rem;
    background: rgba(255, 255, 255, .62);
    padding: .7rem .8rem;
  }

  .simple-task-title {
    overflow: hidden;
    border: 0;
    background: transparent;
    color: var(--ink);
    padding: 0;
    font: inherit;
    font-weight: 750;
    text-align: left;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .simple-task-title:hover {
    color: var(--forest-2);
    text-decoration: underline;
    text-underline-offset: .15rem;
  }

  .simple-task-meta {
    display: flex;
    flex: 0 0 auto;
    align-items: center;
    gap: .4rem;
    color: var(--muted);
    font-size: .7rem;
  }

  .simple-task-meta > span {
    white-space: nowrap;
  }

  @media (max-width: 680px) {
    .simple-task-row {
      align-items: flex-start;
      flex-direction: column;
      gap: .45rem;
    }

    .simple-task-title {
      width: 100%;
    }

    .simple-task-meta {
      flex-wrap: wrap;
    }
  }
</style>
