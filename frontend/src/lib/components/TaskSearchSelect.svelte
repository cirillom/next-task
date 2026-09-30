<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { TaskSummary } from '../api/types';
  import TextField from './TextField.svelte';
  import TaskSearchResults from './TaskSearchResults.svelte';

  export let tasks: TaskSummary[] = [];
  export let excludeIds: number[] = [];
  export let placeholder = 'Search task...';
  export let disabled = false;
  export let allowCreate = true;

  const dispatch = createEventDispatcher<{ select: TaskSummary; create: string }>();
  let search = '';
  let open = false;
  let results: TaskSearchResults;

  function select(task: TaskSummary) {
    dispatch('select', task);
    search = '';
    open = false;
  }

  function create(title: string) {
    dispatch('create', title);
    search = '';
    open = false;
  }

  function keydown(event: KeyboardEvent) {
    if (event.key === 'Escape') open = false;
    if (event.key !== 'Enter' || !open) return;
    event.preventDefault();
    results?.selectFirst();
  }
</script>

<div class="task-search">
  <TextField
    bind:value={search}
    {placeholder}
    autocomplete="off"
    role="combobox"
    aria-label={placeholder}
    aria-autocomplete="list"
    aria-expanded={open}
    {disabled}
    on:focus={() => (open = true)}
    on:input={() => (open = true)}
    on:blur={() => (open = false)}
    on:keydown={keydown}
  />
  {#if open && !disabled}
    <TaskSearchResults bind:this={results} {tasks} query={search} {excludeIds} {allowCreate} on:select={(event) => select(event.detail)} on:create={(event) => create(event.detail)} />
  {/if}
</div>

<style>
  .task-search { position: relative; min-width: 0; }
</style>
