<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { TaskSummary } from '../api/types';

  export let tasks: TaskSummary[] = [];
  export let query = '';
  export let excludeIds: number[] = [];
  export let allowCreate = true;

  const dispatch = createEventDispatcher<{ select: TaskSummary; create: string }>();
  $: matches = tasks.filter((task) =>
    !excludeIds.includes(task.id) && (!query.trim() ||
      task.title.toLowerCase().includes(query.trim().toLowerCase()) ||
      String(task.id).includes(query.trim()))
  );

  export function selectFirst() {
    if (matches[0]) dispatch('select', matches[0]);
    else if (allowCreate && query.trim()) dispatch('create', query.trim());
  }
</script>

<div class="task-options" role="listbox">
  {#each matches as task (task.id)}
    <button type="button" on:mousedown|preventDefault={() => dispatch('select', task)}>{task.title} <small>#{task.id}</small></button>
  {/each}
  {#if allowCreate && query.trim()}
    <button type="button" class="create-option" on:mousedown|preventDefault={() => dispatch('create', query.trim())}>+ Create “{query.trim()}”</button>
  {:else if !matches.length}
    <span class="empty-option">No matching tasks</span>
  {/if}
</div>

<style>
  .task-options { position: absolute; z-index: 12; top: calc(100% + .25rem); right: 0; left: 0; max-height: 15rem; overflow: auto; border: 1px solid #cbc8be; border-radius: .55rem; background: #fff; padding: .3rem; box-shadow: 0 12px 28px rgba(20, 27, 23, .16); }
  .task-options button { display: block; width: 100%; border: 0; border-radius: .4rem; background: transparent; color: var(--ink); padding: .5rem .6rem; text-align: left; font: inherit; }
  .task-options button:hover { background: #f0eee7; }
  .task-options small { color: var(--muted); }
  .create-option { color: var(--forest-2) !important; font-weight: 750 !important; }
  .empty-option { display: block; padding: .55rem .6rem; color: var(--muted); font-size: .85rem; }
</style>
