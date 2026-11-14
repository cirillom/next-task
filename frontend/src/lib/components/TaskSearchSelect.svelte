<script lang="ts">
  import { pickerEscape } from '../keyboard';
  import { text } from '../i18n';
  import { createEventDispatcher } from 'svelte';
  import type { TaskSummary } from '../api/types';
  import TextField from './TextField.svelte';
  import TaskSearchResults from './TaskSearchResults.svelte';

  export let tasks: TaskSummary[] = [];
  export let excludeIds: number[] = [];
  export let placeholder = 'ui.taskSearchSelect.searchTask';
  export let disabled = false;
  export let allowCreate = true;

  const dispatch = createEventDispatcher<{ select: TaskSummary; create: string }>();
  let search = '';
  let open = false;

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

</script>

<div class="task-search" use:pickerEscape={{open: () => open, close: () => {open = false;}}}>
  <TextField
    bind:value={search}
    placeholder={$text(placeholder)}
    autocomplete="off"
    role="combobox"
    aria-label={$text(placeholder)}
    aria-autocomplete="list"
    aria-expanded={open}
    {disabled}
    on:focus={() => (open = true)}
    on:input={() => (open = true)}
    on:blur={() => (open = false)}
  />
  {#if open && !disabled}
    <TaskSearchResults {tasks} query={search} {excludeIds} {allowCreate} on:select={(event) => select(event.detail)} on:create={(event) => create(event.detail)} />
  {/if}
</div>

<style>
  .task-search { position: relative; min-width: 0; }
</style>
