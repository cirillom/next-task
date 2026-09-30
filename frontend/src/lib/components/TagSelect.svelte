<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { TagSummary } from '../api/types';
  import TagBadge from './TagBadge.svelte';
  import TextField from './TextField.svelte';

  export let options: { tag: TagSummary; depth?: number; context?: string }[] = [];
  export let value: number | '' = 0;
  export let emptyValue: number | '' = 0;
  export let emptyLabel = 'Choose a tag';
  export let disabled = false;
  export let label = 'Tag';
  export let searchable = false;
  export let allowCreate = true;
  export let existingNames: string[] = [];

  const dispatch = createEventDispatcher<{ change: number | ''; create: string }>();
  let open = false;
  let search = '';
  let dirty = false;
  let root: HTMLDivElement;
  $: selectedOption = options.find(({ tag }) => tag.id === Number(value));
  $: query = search.trim().toLowerCase();
  $: filteredOptions = searchable && dirty && query
    ? options.filter(({ tag }) => tag.name.toLowerCase().includes(query))
    : options;
  $: canCreate = searchable && allowCreate && dirty && query && ![...existingNames, ...options.map(({ tag }) => tag.name)]
    .some((name) => name.toLowerCase() === query);

  function choose(next: number | '') {
    value = next;
    open = false;
    search = '';
    dirty = false;
    dispatch('change', next);
  }

  function create() {
    dispatch('create', search.trim());
    open = false;
    search = '';
    dirty = false;
  }

  function focusSearch(event: FocusEvent) {
    open = true;
    dirty = false;
    (event.currentTarget as HTMLInputElement).select();
  }

  function filterSearch(event: Event) {
    search = (event.currentTarget as HTMLInputElement).value;
    dirty = true;
    value = emptyValue;
    open = true;
    dispatch('change', value);
  }

  function closeSearch() {
    open = false;
    search = '';
    dirty = false;
  }

  function closeOnBlur(event: FocusEvent) {
    if (!root.contains(event.relatedTarget as Node | null)) open = false;
  }

  function closeOnOutsideClick(event: MouseEvent) {
    if (open && root && !root.contains(event.target as Node)) {
      if (searchable) closeSearch();
      else open = false;
    }
  }

  function keepSearchFocus(event: MouseEvent) {
    if (searchable) event.preventDefault();
  }

</script>

<svelte:window on:click={closeOnOutsideClick} />

<div class="tag-select-control" bind:this={root} on:focusout={closeOnBlur}>
  {#if searchable}
    <TextField
      value={dirty ? search : (selectedOption?.tag.name || '')}
      placeholder={emptyLabel}
      autocomplete="off"
      role="combobox"
      aria-label={label}
      aria-autocomplete="list"
      aria-expanded={open}
      {disabled}
      on:focus={focusSearch}
      on:click={() => (open = true)}
      on:input={filterSearch}
      on:blur={closeSearch}
      on:keydown={(event) => { if (event.key === 'Escape') closeSearch(); if (event.key === 'Enter') event.preventDefault(); }}
    />
  {:else}
    <button type="button" class="tag-select-trigger" {disabled} aria-label={label} aria-expanded={open} aria-haspopup="listbox" on:click={() => (open = !open)} on:keydown={(event) => { if (event.key === 'Escape') open = false; }}>
      {#if selectedOption}<span class="option-copy"><TagBadge tag={selectedOption.tag} />{#if selectedOption.context && selectedOption.context !== selectedOption.tag.name}<small>{selectedOption.context}</small>{/if}</span>{:else}<span>{emptyLabel}</span>{/if}
      <span aria-hidden="true">⌄</span>
    </button>
  {/if}
  {#if open && !disabled}
    <div class="tag-select-options" class:search-options={searchable} role="listbox" aria-label={label}>
      {#if !searchable}
        <button type="button" role="option" aria-selected={value === emptyValue} class:chosen={value === emptyValue} on:click={() => choose(emptyValue)} on:keydown={(event) => { if (event.key === 'Escape') open = false; }}>{emptyLabel}</button>
      {/if}
      {#each filteredOptions as option}
        <button type="button" role="option" aria-selected={value === option.tag.id} class:chosen={value === option.tag.id} style:--depth={`${option.depth || 0}rem`} on:mousedown={keepSearchFocus} on:click={() => choose(option.tag.id)} on:keydown={(event) => { if (event.key === 'Escape') open = false; }}>
          <span class="option-copy"><TagBadge tag={option.tag} selected={value === option.tag.id} />{#if option.context && option.context !== option.tag.name}<small>{option.context}</small>{/if}</span>
        </button>
      {/each}
      {#if canCreate}
        <button type="button" on:mousedown={keepSearchFocus} on:click={create}>+ Create “{search.trim()}”</button>
      {:else if searchable && !filteredOptions.length}
        <span class="tag-select-empty">No matching tags</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .tag-select-control { position: relative; min-width: 0; }
  .tag-select-trigger { display: flex; width: 100%; min-height: 2.55rem; align-items: center; justify-content: space-between; gap: .5rem; border: 1px solid #cfcbbf; border-radius: .55rem; background: #fff; color: var(--ink); padding: .35rem .65rem; text-align: left; }
  .tag-select-trigger:focus-visible, .tag-select-options button:focus-visible { outline: 2px solid var(--gold); outline-offset: 1px; }
  .tag-select-options { position: absolute; z-index: 15; top: calc(100% + .2rem); right: 0; left: 0; max-height: 16rem; overflow-y: auto; border: 1px solid var(--line); border-radius: .55rem; background: #fff; padding: .3rem; box-shadow: var(--shadow); }
  .tag-select-options button { display: flex; width: 100%; align-items: center; border: 0; border-radius: .35rem; background: transparent; color: var(--ink); padding: .35rem .5rem .35rem calc(.5rem + var(--depth)); text-align: left; }
  .tag-select-options button:hover, .tag-select-options button.chosen { background: #f2f3ef; }
  .tag-select-options.search-options { max-height: 15rem; }
  .tag-select-options.search-options button { padding: .5rem .6rem .5rem calc(.6rem + var(--depth)); font: inherit; }
  .tag-select-empty { display: block; padding: .4rem .5rem; color: var(--muted); font-size: .78rem; }
  .option-copy { display: grid; min-width: 0; gap: .12rem; justify-items: start; }
  .option-copy small { overflow: hidden; max-width: 100%; color: var(--muted); font-size: .68rem; text-overflow: ellipsis; white-space: nowrap; }
</style>
