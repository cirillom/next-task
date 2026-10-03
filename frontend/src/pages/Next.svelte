<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { NextScope, Tag, Task } from '../lib/api/types';
  import NextTaskCard from '../lib/components/NextTaskCard.svelte';
  import AppButton from '../lib/components/AppButton.svelte';
  import PomodoroLauncher from '../lib/components/PomodoroLauncher.svelte';
  import TaskQueue from '../lib/components/TaskQueue.svelte';

  export let userId: number;
  const dispatch = createEventDispatcher<{ openTask: number; startFocus: NextScope; createBlocker: { taskId: number; title: string } }>();

  let tasks: Task[] = [];
  let tags: Tag[] = [];
  let scope: NextScope = { include_tag_ids: [], exclude_tag_ids: [], tag_match: 'all' };
  let filtersOpen = false;
  let error = '';
  let loading = true;
  let refreshTimer: number;

  async function loadTasks(showLoading = true) {
    if (showLoading) loading = true;
    error = '';
    try {
      tasks = await api.tasks({
        finished: false,
        blocked: false,
        actionable: true,
        include_tag_id: scope.include_tag_ids,
        exclude_tag_id: scope.exclude_tag_ids,
        tag_match: scope.tag_match
      });
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load tasks';
    } finally {
      if (showLoading) loading = false;
    }
  }

  function updateScope(next: NextScope) {
    scope = next;
    localStorage.setItem(`next-task-scope:${userId}`, JSON.stringify(scope));
    void loadTasks();
  }

  function toggleTag(tagId: number, kind: 'include' | 'exclude') {
    const include = new Set(scope.include_tag_ids);
    const exclude = new Set(scope.exclude_tag_ids);
    const target = kind === 'include' ? include : exclude;
    const other = kind === 'include' ? exclude : include;
    if (target.has(tagId)) target.delete(tagId);
    else { target.add(tagId); other.delete(tagId); }
    updateScope({ ...scope, include_tag_ids: [...include], exclude_tag_ids: [...exclude] });
  }

  async function replaceTask(_updated: Task) {
    await loadTasks(false);
  }

  onMount(() => {
    void (async () => {
      try {
        tags = await api.tags();
        let saved: Partial<NextScope> | null = null;
        try {
          saved = JSON.parse(localStorage.getItem(`next-task-scope:${userId}`) || 'null') as Partial<NextScope> | null;
        } catch {
          localStorage.removeItem(`next-task-scope:${userId}`);
        }
        const valid = new Set(tags.map((tag) => tag.id));
        scope = {
          include_tag_ids: saved?.include_tag_ids?.filter((id) => valid.has(id)) ?? [],
          exclude_tag_ids: saved?.exclude_tag_ids?.filter((id) => valid.has(id)) ?? [],
          tag_match: saved?.tag_match === 'any' ? 'any' : 'all'
        };
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
  <button type="button" aria-expanded={filtersOpen} on:click={() => (filtersOpen = !filtersOpen)}>Tag filters {scope.include_tag_ids.length + scope.exclude_tag_ids.length ? `(${scope.include_tag_ids.length + scope.exclude_tag_ids.length})` : ''}</button>
  {#if filtersOpen}
    <div class="filter-panel" aria-label="Tag filters">
      <label>Match included tags
        <select value={scope.tag_match} on:change={(event) => updateScope({ ...scope, tag_match: event.currentTarget.value as 'all' | 'any' })}>
          <option value="all">All</option><option value="any">Any</option>
        </select>
      </label>
      {#each tags as tag (tag.id)}
        <div class="tag-filter-row"><span>{tag.name}</span><label><input type="checkbox" checked={scope.include_tag_ids.includes(tag.id)} on:change={() => toggleTag(tag.id, 'include')} /> Include</label><label><input type="checkbox" checked={scope.exclude_tag_ids.includes(tag.id)} on:change={() => toggleTag(tag.id, 'exclude')} /> Exclude</label></div>
      {/each}
    </div>
  {/if}
</div>

{#if error}<p class="error" role="alert">{error}</p>{/if}

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
  .filter-panel { display: grid; gap: .5rem; max-height: 22rem; overflow-y: auto; margin-top: .5rem; border: 1px solid var(--line); border-radius: .65rem; background: #fff; padding: .75rem; }
  .filter-panel > label { display: flex; align-items: center; gap: .5rem; font-size: .82rem; }
  .tag-filter-row { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; gap: .75rem; align-items: center; font-size: .82rem; }
  .tag-filter-row > span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tag-filter-row label { display: flex; align-items: center; gap: .25rem; cursor: pointer; }
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
