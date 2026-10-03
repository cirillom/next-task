<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { NextScope, Tag, Task, Workspace } from '../lib/api/types';
  import NextTaskCard from '../lib/components/NextTaskCard.svelte';
  import AppButton from '../lib/components/AppButton.svelte';
  import PomodoroLauncher from '../lib/components/PomodoroLauncher.svelte';
  import TagPicker from '../lib/components/TagPicker.svelte';
  import TaskQueue from '../lib/components/TaskQueue.svelte';

  export let workspaces: Workspace[];
  export let userId: number;
  const dispatch = createEventDispatcher<{ openTask: number; newTask: number[]; scopeChange: NextScope; startFocus: NextScope; createBlocker: { taskId: number; title: string } }>();

  let tasks: Task[] = [];
  let tags: Tag[] = [];
  let scope: NextScope = { workspace_ids: [], include_tag_ids: [], exclude_tag_ids: [], tag_match: 'all' };
  let workspaceFilterOpen = false;
  let tagFilterOpen = false;
  let loadToken = 0;
  let tagLoadToken = 0;
  let error = '';
  let loading = true;
  let refreshTimer: number;

  $: workspaceNames = Object.fromEntries(workspaces.map((item) => [item.id, item.name]));
  $: tagNames = Object.fromEntries(tags.map((tag) => [tag.id, tagName(tag)]));
  $: editableWorkspaceIds = scope.workspace_ids.filter((id) => workspaces.find((item) => item.id === id)?.role !== 'viewer');

  function storageKey() { return `next-task-next-scope-${userId}`; }

  function tagName(tag: Tag): string {
    const duplicate = tags.some((item) => item.id !== tag.id && item.name.toLowerCase() === tag.name.toLowerCase());
    return duplicate ? `${tag.name} (${workspaceNames[tag.workspace_id] || 'Workspace'})` : tag.name;
  }

  async function loadTasks(showLoading = true) {
    const token = ++loadToken;
    if (showLoading) loading = true;
    error = '';
    try {
      const loaded = await api.nextTasks(scope, tags);
      if (token === loadToken) tasks = loaded;
    } catch (reason) {
      if (token === loadToken) error = reason instanceof Error ? reason.message : 'Could not load tasks';
    } finally {
      if (token === loadToken) loading = false;
    }
  }

  async function updateScope(next: NextScope, reloadTags = false) {
    scope = next;
    dispatch('scopeChange', scope);
    localStorage.setItem(storageKey(), JSON.stringify({ ...scope, all_workspaces: scope.workspace_ids.length === workspaces.length }));
    if (reloadTags) {
      const token = ++tagLoadToken;
      try {
        const loaded = (await Promise.all(scope.workspace_ids.map((id) => api.tags(id)))).flat();
        if (token !== tagLoadToken) return;
        tags = loaded;
      } catch (reason) {
        if (token !== tagLoadToken) return;
        error = reason instanceof Error ? reason.message : 'Could not load tags';
        loading = false;
        return;
      }
      const ids = new Set(tags.map((tag) => tag.id));
      scope = { ...scope, include_tag_ids: scope.include_tag_ids.filter((id) => ids.has(id)), exclude_tag_ids: scope.exclude_tag_ids.filter((id) => ids.has(id)) };
      dispatch('scopeChange', scope);
      localStorage.setItem(storageKey(), JSON.stringify({ ...scope, all_workspaces: scope.workspace_ids.length === workspaces.length }));
    }
    await loadTasks();
  }

  function toggleWorkspace(id: number) {
    const workspace_ids = scope.workspace_ids.includes(id)
      ? scope.workspace_ids.filter((item) => item !== id)
      : workspaces.filter((item) => scope.workspace_ids.includes(item.id) || item.id === id).map((item) => item.id);
    void updateScope({ ...scope, workspace_ids }, true);
  }

  function setTags(kind: 'include_tag_ids' | 'exclude_tag_ids', ids: number[]) {
    void updateScope({ ...scope, [kind]: ids });
  }

  onMount(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey()) || 'null') as (Partial<NextScope> & { all_workspaces?: boolean }) | null;
      const valid = new Set(workspaces.map((item) => item.id));
      scope = {
        workspace_ids: saved?.all_workspaces ? workspaces.map((item) => item.id) : saved?.workspace_ids?.filter((id) => valid.has(id)) ?? workspaces.map((item) => item.id),
        include_tag_ids: saved?.include_tag_ids ?? [],
        exclude_tag_ids: saved?.exclude_tag_ids ?? [],
        tag_match: saved?.tag_match === 'any' ? 'any' : 'all'
      };
    } catch {
      scope = { workspace_ids: workspaces.map((item) => item.id), include_tag_ids: [], exclude_tag_ids: [], tag_match: 'all' };
    }
    void updateScope(scope, true);

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
  {#if editableWorkspaceIds.length}<AppButton variant="primary" on:click={() => dispatch('newTask', editableWorkspaceIds)}>+ New task</AppButton>{/if}
</div>

<div class="next-filters" aria-label="Next task filters">
  <div class="filter-control">
    <button type="button" aria-expanded={workspaceFilterOpen} on:click={() => { workspaceFilterOpen = !workspaceFilterOpen; tagFilterOpen = false; }}>
      Workspaces <strong>{scope.workspace_ids.length === workspaces.length ? 'All' : `${scope.workspace_ids.length} selected`}</strong>
    </button>
    {#if workspaceFilterOpen}
      <div class="filter-panel" role="group" aria-label="Workspaces">
        {#each workspaces as item (item.id)}
          <label><input type="checkbox" checked={scope.workspace_ids.includes(item.id)} on:change={() => toggleWorkspace(item.id)} /> {item.name}</label>
        {/each}
      </div>
    {/if}
  </div>
  <div class="filter-control">
    <button type="button" aria-expanded={tagFilterOpen} on:click={() => { tagFilterOpen = !tagFilterOpen; workspaceFilterOpen = false; }}>
      Tags <strong>{scope.include_tag_ids.length + scope.exclude_tag_ids.length || 'All'}</strong>
    </button>
    {#if tagFilterOpen}
      <div class="filter-panel tag-panel" role="group" aria-label="Tag filters">
        <span>Include tags</span>
        <TagPicker {tags} displayName={tagName} selectedIds={scope.include_tag_ids} allowCreate={false} on:change={(event) => setTags('include_tag_ids', event.detail)} />
        <fieldset>
          <legend>Match included tags within each workspace</legend>
          <label><input type="radio" name="next-tag-match" checked={scope.tag_match === 'all'} on:change={() => void updateScope({ ...scope, tag_match: 'all' })} /> All</label>
          <label><input type="radio" name="next-tag-match" checked={scope.tag_match === 'any'} on:change={() => void updateScope({ ...scope, tag_match: 'any' })} /> Any</label>
        </fieldset>
        <span>Exclude tags</span>
        <TagPicker {tags} displayName={tagName} selectedIds={scope.exclude_tag_ids} allowCreate={false} on:change={(event) => setTags('exclude_tag_ids', event.detail)} />
        <small>Child tags are included in each match.</small>
      </div>
    {/if}
  </div>
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
    <section class="empty"><strong>Nothing actionable right now.</strong><span>Try another workspace or tag filter, add a task, or check Tasks for blocked work.</span></section>
  {:else if !loading}
    <NextTaskCard
      task={tasks[0]}
      workspaceName={workspaceNames[tasks[0].workspace_id] || ''}
      {tagNames}
      readOnly={workspaces.find((item) => item.id === tasks[0].workspace_id)?.role === 'viewer'}
      on:changed={() => void loadTasks(false)}
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
      {workspaceNames}
      on:open={(event) => dispatch('openTask', event.detail)}
    />
  </section>
{/if}

<style>
  .next-filters { display: flex; flex-wrap: wrap; gap: .6rem; margin: -.3rem 0 1rem; }
  .filter-control { position: relative; }
  .filter-control > button { display: flex; gap: .75rem; align-items: center; border: 1px solid var(--line); border-radius: .55rem; padding: .55rem .7rem; background: var(--paper); color: var(--ink); }
  .filter-control > button strong { color: var(--forest-2); }
  .filter-panel { position: absolute; z-index: 20; top: calc(100% + .3rem); left: 0; display: grid; gap: .6rem; min-width: 14rem; max-width: min(90vw, 25rem); border: 1px solid var(--line); border-radius: .6rem; padding: .8rem; background: white; box-shadow: 0 12px 28px rgba(20, 27, 23, .16); }
  .filter-panel:not(.tag-panel) { max-height: 22rem; overflow-y: auto; }
  .filter-panel label { display: flex; align-items: center; gap: .4rem; white-space: nowrap; }
  .tag-panel { min-width: min(85vw, 22rem); }
  .tag-panel > span, .tag-panel legend { font-size: .75rem; font-weight: 800; }
  .tag-panel small { color: var(--muted); }
  .tag-panel fieldset { display: flex; gap: .8rem; border: 0; padding: 0; margin: 0; }
  .tag-panel fieldset legend { margin-bottom: .3rem; }
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
  @media (max-width: 640px) {
    .next-filters { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .filter-control > button { width: 100%; justify-content: space-between; }
    .filter-control:last-child .filter-panel { left: auto; right: 0; }
  }
</style>
