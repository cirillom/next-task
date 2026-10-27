<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { NextScope, Tag, Task } from '../lib/api/types';
  import NextTaskCard from '../lib/components/NextTaskCard.svelte';
  import AppButton from '../lib/components/AppButton.svelte';
  import PomodoroLauncher from '../lib/components/PomodoroLauncher.svelte';
  import TagScopeFilters from '../lib/components/TagScopeFilters.svelte';
  import TaskQueue from '../lib/components/TaskQueue.svelte';
  import ScoringWarning from '../lib/components/ScoringWarning.svelte';
  import { cleanTagScope, emptyTagScope } from '../lib/tagScope';

  export let userId: number;
  const dispatch = createEventDispatcher<{ openTask: number; startFocus: NextScope; createBlocker: { taskId: number; title: string } }>();

  let tasks: Task[] = [];
  let tags: Tag[] = [];
  let tagsLoaded = false;
  let scope: NextScope = emptyTagScope();
  let filtersOpen = false;
  let error = '';
  let loading = true;
  let refreshTimer: number;
  let taskRequest = 0;

  async function loadTasks(showLoading = true) {
    const request = ++taskRequest;
    if (showLoading) loading = true;
    error = '';
    try {
      const ranked = await api.tasks({
        finished: false,
        blocked: false,
        actionable: true,
        include_tag_id: scope.include_tag_ids,
        exclude_tag_id: scope.exclude_tag_ids,
        tag_match: scope.tag_match
      });
      if (request === taskRequest) tasks = ranked;
    } catch (reason) {
      if (request === taskRequest) error = reason instanceof Error ? reason.message : 'Could not load tasks';
    } finally {
      if (request === taskRequest) loading = false;
    }
  }

  function updateScope(next: NextScope) {
    scope = cleanTagScope(next, new Set(tags.map((tag) => tag.id)));
    localStorage.setItem(`next-task-scope:${userId}`, JSON.stringify(scope));
    void loadTasks();
  }

  async function replaceTask(_updated: Task) {
    await loadTasks(false);
  }

  onMount(() => {
    void (async () => {
      try {
        tags = await api.tags();
        tagsLoaded = true;
        let saved: Partial<NextScope> | null = null;
        try {
          saved = JSON.parse(localStorage.getItem(`next-task-scope:${userId}`) || 'null') as Partial<NextScope> | null;
        } catch {
          localStorage.removeItem(`next-task-scope:${userId}`);
        }
        const valid = new Set(tags.map((tag) => tag.id));
        scope = cleanTagScope(saved, valid);
        await loadTasks();
      } catch (reason) {
        error = reason instanceof Error ? reason.message : 'Could not load tasks';
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
  <AppButton variant="primary" on:click={() => dispatch('openTask', 0)}>+ New task</AppButton>
</div>

<div class="next-filters">
  <button type="button" disabled={!tagsLoaded} aria-expanded={filtersOpen} on:click={() => (filtersOpen = !filtersOpen)}>Tag filters {scope.include_tag_ids.length + scope.exclude_tag_ids.length ? `(${scope.include_tag_ids.length + scope.exclude_tag_ids.length} active)` : ''}</button>
  {#if filtersOpen}
    <div class="filter-panel" aria-label="Tag filters">
      <TagScopeFilters {tags} {scope} matchName="next-tag-match" on:change={(event) => updateScope(event.detail)} />
    </div>
  {/if}
</div>

{#if error}<p class="error" role="alert">{error}</p>{/if}
<ScoringWarning message={tasks[0]?.scoring_warning ?? null} />

{#if loading}
  <p class="empty">Ranking your tasks…</p>
{/if}

<section class:has-recommendation={!loading && tasks.length > 0} class="next-focus-block" aria-label="Pomodoro and recommended task">
  <PomodoroLauncher
    recommendedTaskTitle={tasks[0]?.title || ''}
    on:start={() => dispatch('startFocus', scope)}
  />

  {#if !loading && tasks.length === 0}
    <section class="empty"><strong>Nothing actionable right now.</strong><span>Try another tag filter, add a task, or check Tasks for blocked work.</span></section>
  {:else if !loading}
    <NextTaskCard
      task={tasks[0]}

      on:changed={(event) => void replaceTask(event.detail)}
      on:open={(event) => dispatch('openTask', event.detail)}
      on:createBlocker={(event) => dispatch('createBlocker', event.detail)}
      on:error={(event) => (error = event.detail)}
    />
  {/if}
</section>

{#if !loading && tasks.length > 1}
  <section class="queue" aria-label="Task queue">
    <div class="queue__heading">
      <h2>Queue</h2>
      <span>{tasks.length - 1} more</span>
    </div>

    <TaskQueue
      tasks={tasks.slice(1)}
      on:open={(event) => dispatch('openTask', event.detail)}
    />
  </section>
{/if}

<style>
  .next-filters { margin-bottom: .8rem; }
  .next-filters > button { border: 1px solid var(--line); border-radius: .5rem; background: #fff; color: var(--forest-2); padding: .45rem .65rem; font: inherit; font-size: .85rem; font-weight: 700; cursor: pointer; }
  .filter-panel { width: min(34rem, 100%); max-height: 22rem; overflow-y: auto; margin-top: .5rem; border: 1px solid var(--line); border-radius: .65rem; background: #fff; padding: .75rem; }
  .next-focus-block {
    margin-bottom: 1.5rem;
  }

  .next-focus-block :global(.pomodoro-launcher) {
    margin-bottom: 0;
  }

  .next-focus-block.has-recommendation :global(.pomodoro-launcher) {
    border-bottom-right-radius: 0;
    border-bottom-left-radius: 0;
    box-shadow: 0 8px 26px rgba(60, 44, 34, .08);
  }

  .next-focus-block.has-recommendation :global(.recommended-card) {
    margin-top: -1px;
    border-top-left-radius: 0;
    border-top-right-radius: 0;
    box-shadow: 0 14px 38px rgba(30, 48, 39, .1);
  }

  .next-focus-block > .empty {
    margin-top: .75rem;
  }

  .queue {
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
