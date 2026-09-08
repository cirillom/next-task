<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../api/client';
  import type { Task } from '../api/types';

  export let workspaceId: number;
  export let taskId: number;
  export let taskTitle: string;
  export let busy = false;

  type TreeRow = { task: Task; depth: number };

  const dispatch = createEventDispatcher<{ close: void; confirm: void }>();
  let rows: TreeRow[] = [];
  let loading = true;
  let error = '';

  $: unfinishedCount = rows.filter((row) => !row.task.finished_at).length;

  function flattenDescendants(tasks: Task[]): TreeRow[] {
    const children = new Map<number, Task[]>();
    for (const task of tasks) {
      if (task.parent_task_id === null) continue;
      const siblings = children.get(task.parent_task_id) || [];
      siblings.push(task);
      children.set(task.parent_task_id, siblings);
    }

    const flattened: TreeRow[] = [];
    const walk = (parentId: number, depth: number) => {
      for (const child of children.get(parentId) || []) {
        flattened.push({ task: child, depth });
        walk(child.id, depth + 1);
      }
    };
    walk(taskId, 0);
    return flattened;
  }

  onMount(async () => {
    try {
      const [unfinished, finished] = await Promise.all([
        api.tasks(workspaceId, { finished: false }),
        api.tasks(workspaceId, { finished: true })
      ]);
      rows = flattenDescendants([...unfinished, ...finished]);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load child tasks';
    } finally {
      loading = false;
    }
  });
</script>

<div class="modal-backdrop completion-backdrop" role="presentation" on:click|self={() => dispatch('close')}>
  <section
    class="completion-dialog"
    role="dialog"
    aria-modal="true"
    aria-labelledby="completion-dialog-title"
    aria-describedby="completion-dialog-description"
  >
    <header class="completion-header">
      <div>
        <p class="eyebrow">Task hierarchy</p>
        <h2 id="completion-dialog-title">Finish this task tree?</h2>
      </div>
      <button type="button" class="icon-button" aria-label="Close" on:click={() => dispatch('close')}>×</button>
    </header>

    <div class="completion-summary">
      <strong>{taskTitle}</strong>
      <p id="completion-dialog-description">
        Finishing this task also finishes every unfinished task below it, so completed parents never leave unfinished work behind.
      </p>
    </div>

    <div class="tree-panel">
      <div class="tree-heading">
        <strong>Child tasks</strong>
        {#if !loading && !error}<span>{unfinishedCount} will be finished</span>{/if}
      </div>

      {#if loading}
        <p class="tree-state">Loading task tree…</p>
      {:else if error}
        <p class="error" role="alert">{error}</p>
      {:else if rows.length === 0}
        <p class="tree-state">No child tasks found.</p>
      {:else}
        <ul class="completion-tree">
          {#each rows as row (row.task.id)}
            <li class:already-finished={!!row.task.finished_at} style={`--depth: ${row.depth}`}>
              <span class="branch" aria-hidden="true">•</span>
              {#if row.task.finished_at}
                <span class="state-icon finished" title="Already finished">✓</span>
              {:else}
                <span class="state-icon will-finish" title="Unfinished task that will be finished">○→✓</span>
              {/if}
              <span class="tree-title">{row.task.title} <small>#{row.task.id}</small></span>
              {#if !row.task.finished_at}<span class="will-finish-chip">Will finish</span>{/if}
            </li>
          {/each}
        </ul>
      {/if}
    </div>

    <footer class="completion-actions">
      <button type="button" disabled={busy} on:click={() => dispatch('close')}>Cancel</button>
      <button
        type="button"
        class="primary"
        disabled={busy || loading || !!error}
        on:click={() => dispatch('confirm')}
      >
        {busy ? 'Finishing…' : `Finish task${unfinishedCount ? ` + ${unfinishedCount} child${unfinishedCount === 1 ? '' : ' tasks'}` : ''}`}
      </button>
    </footer>
  </section>
</div>

<style>
  .completion-backdrop { z-index: 80; }

  .completion-dialog {
    width: min(100%, 34rem);
    max-height: min(42rem, calc(100vh - 2rem));
    overflow: auto;
    border: 1px solid var(--line);
    border-radius: .9rem;
    background: var(--paper);
    box-shadow: 0 24px 70px rgba(20, 32, 26, .24);
  }

  .completion-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    border-bottom: 1px solid var(--line);
    padding: 1rem 1.1rem .85rem;
  }

  .completion-header .eyebrow { margin-bottom: .25rem; }
  .completion-header h2 { margin: 0; font-size: 1.25rem; }

  .completion-summary {
    border-bottom: 1px solid #e8e3d9;
    background: #faf7ef;
    padding: .85rem 1.1rem;
  }

  .completion-summary strong { color: var(--ink); }
  .completion-summary p {
    margin: .25rem 0 0;
    color: var(--muted);
    font-size: .82rem;
    line-height: 1.45;
  }

  .tree-panel { padding: .9rem 1.1rem 1rem; }

  .tree-heading {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: .55rem;
  }

  .tree-heading span {
    color: #8a5b20;
    font-size: .72rem;
    font-weight: 800;
  }

  .tree-state {
    margin: .75rem 0;
    color: var(--muted);
    font-size: .82rem;
  }

  .completion-tree {
    display: grid;
    gap: .15rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .completion-tree li {
    display: grid;
    grid-template-columns: .6rem 2.2rem minmax(0, 1fr) auto;
    align-items: center;
    gap: .35rem;
    min-height: 2rem;
    margin-left: calc(var(--depth) * 1.15rem);
    border-radius: .45rem;
    padding: .3rem .4rem;
    font-size: .8rem;
  }

  .completion-tree li:not(.already-finished) { background: #fff8e9; }
  .completion-tree li.already-finished { color: var(--muted); }

  .branch { color: #b7b1a4; }

  .state-icon {
    display: inline-grid;
    min-width: 2rem;
    place-items: center;
    font-size: .72rem;
    font-weight: 900;
  }

  .state-icon.finished { color: var(--forest-2); }
  .state-icon.will-finish { color: #95641f; }

  .tree-title {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .tree-title small { color: var(--muted); font-size: .68rem; }

  .will-finish-chip {
    border: 1px solid #e2c78d;
    border-radius: 999px;
    background: #fff3d8;
    color: #805719;
    padding: .12rem .38rem;
    font-size: .65rem;
    font-weight: 800;
    white-space: nowrap;
  }

  .completion-actions {
    display: flex;
    justify-content: flex-end;
    gap: .6rem;
    border-top: 1px solid var(--line);
    padding: .8rem 1.1rem;
  }

  .completion-actions > button:not(.primary) {
    border: 1px solid #cbc8be;
    border-radius: .5rem;
    background: #fff;
    color: var(--ink);
    padding: .55rem .8rem;
  }

  @media (max-width: 600px) {
    .completion-tree li {
      grid-template-columns: .45rem 1.8rem minmax(0, 1fr);
      margin-left: calc(var(--depth) * .75rem);
    }

    .will-finish-chip { display: none; }
  }
</style>
