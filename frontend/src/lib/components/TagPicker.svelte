<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Tag } from '../api/types';
  import { hierarchicalTagResults, tagHierarchyPaths } from '../tagHierarchy';

  export let tags: Tag[] = [];
  export let selectedIds: number[] = [];
  export let suggestedNames: string[] = [];
  export let disabled = false;
  export let creating = false;
  export let allowCreate = true;

  const dispatch = createEventDispatcher<{
    change: number[];
    create: { name: string; parent_tag_id: number | null; color: string };
  }>();

  let search = '';
  let open = false;
  let createOpen = false;
  let createName = '';
  let createParentId = 0;
  let createColor = '#587b6a';

  $: selectedTags = tags.filter((tag) => selectedIds.includes(tag.id));
  $: filteredTags = hierarchicalTagResults(tags, search);
  $: normalizedSearch = search.trim().toLowerCase();
  $: exactMatch = tags.some((tag) => tag.name.toLowerCase() === normalizedSearch);

  function toggle(tagId: number) {
    const next = selectedIds.includes(tagId)
      ? selectedIds.filter((id) => id !== tagId)
      : [...selectedIds, tagId];
    dispatch('change', next);
  }

  function remove(tagId: number) {
    dispatch('change', selectedIds.filter((id) => id !== tagId));
  }

  function chooseSuggestion(name: string) {
    search = name;
    open = true;
  }

  function requestCreate() {
    if (!allowCreate || !normalizedSearch || exactMatch || creating) return;
    createName = search.trim();
    createParentId = 0;
    createColor = '#587b6a';
    createOpen = true;
    open = false;
  }

  function cancelCreate() {
    createOpen = false;
  }

  function submitCreate() {
    const name = createName.trim();
    if (!name || creating) return;
    dispatch('create', {
      name,
      parent_tag_id: createParentId || null,
      color: createColor
    });
    createOpen = false;
    search = '';
  }

  function parentLabel(tag: Tag): string {
    return tagHierarchyPaths(tag, tags)[0] || tag.name;
  }

  function contextPaths(tag: Tag): string[] {
    return tagHierarchyPaths(tag, tags).filter((path) => path !== tag.name);
  }
</script>

<div class="tag-picker">
  {#if suggestedNames.length && !disabled}
    <div class="tag-suggestions">
      <small>Suggested new tags</small>
      {#each suggestedNames as suggestion}
        <button type="button" on:click={() => chooseSuggestion(suggestion)}>{suggestion}</button>
      {/each}
    </div>
  {/if}

  {#if selectedTags.length}
    <div class="selected-tags" aria-label="Selected direct tags">
      {#each selectedTags as tag (tag.id)}
        <span class="selected-tag" style:--tag-color={tag.color || '#73847c'}>
          {tag.name}
          {#if !disabled}
            <button type="button" aria-label={`Remove ${tag.name}`} on:click={() => remove(tag.id)}>×</button>
          {/if}
        </span>
      {/each}
    </div>
  {/if}

  <div class="picker-control">
    <input
      bind:value={search}
      aria-label="Search tags"
      placeholder="Search tags or hierarchy"
      autocomplete="off"
      disabled={disabled}
      on:focus={() => (open = true)}
      on:blur={() => (open = false)}
      on:keydown={(event) => event.key === 'Enter' && event.preventDefault()}
    />

    {#if open && !disabled}
      <div class="tag-options" role="listbox" aria-label="Tag options">
        {#each filteredTags as result (`${result.tag.id}-${result.depth}`)}
          <button
            type="button"
            class:selected={selectedIds.includes(result.tag.id)}
            style:--tag-indent={`${result.depth}rem`}
            on:mousedown|preventDefault={() => toggle(result.tag.id)}
          >
            <span class="option-check" aria-hidden="true">{selectedIds.includes(result.tag.id) ? '✓' : ''}</span>
            <span class="option-copy">
              <strong>{result.tag.name}</strong>
              {#each contextPaths(result.tag) as path}
                <small>{path}</small>
              {/each}
            </span>
          </button>
        {/each}

        {#if allowCreate && normalizedSearch && !exactMatch}
          <button
            type="button"
            class="create-tag"
            disabled={creating}
            on:mousedown|preventDefault={requestCreate}
          >
            <span class="option-check" aria-hidden="true">+</span>
            <span class="option-copy"><strong>{creating ? 'Creating…' : `Create ${normalizedSearch}`}</strong></span>
          </button>
        {:else if !filteredTags.length}
          <span class="tag-empty">No matching tags</span>
        {/if}
      </div>
    {/if}
  </div>

  {#if createOpen && allowCreate && !disabled}
    <div class="inline-tag-create" aria-label="Create tag">
      <label>
        Name
        <input bind:value={createName} maxlength="120" disabled={creating} />
      </label>
      <label>
        Parent
        <select bind:value={createParentId} disabled={creating}>
          <option value={0}>No parent</option>
          {#each [...tags].sort((left, right) => left.name.localeCompare(right.name)) as tag (tag.id)}
            <option value={tag.id}>{parentLabel(tag)}</option>
          {/each}
        </select>
      </label>
      <label class="color-input">
        Color
        <input type="color" bind:value={createColor} disabled={creating} />
      </label>
      <div class="inline-create-actions">
        <button type="button" disabled={creating} on:click={cancelCreate}>Cancel</button>
        <button type="button" class="primary" disabled={creating || !createName.trim()} on:click={submitCreate}>
          {creating ? 'Creating…' : 'Create and select'}
        </button>
      </div>
    </div>
  {/if}
</div>

<style>
  .tag-picker { display: grid; gap: .35rem; }
  .tag-suggestions, .selected-tags { display: flex; flex-wrap: wrap; align-items: center; gap: .3rem; }
  .tag-suggestions small { margin-right: .15rem; color: var(--muted); }
  .tag-suggestions button {
    border: 1px dashed #aeb9b2;
    border-radius: 999px;
    background: #f7f8f5;
    color: var(--forest-2);
    padding: .18rem .45rem;
    font-size: .72rem;
  }

  .selected-tag {
    display: inline-flex;
    align-items: center;
    gap: .25rem;
    border: 1px solid color-mix(in srgb, var(--tag-color) 30%, white);
    border-radius: 999px;
    background: color-mix(in srgb, var(--tag-color) 15%, white);
    color: color-mix(in srgb, var(--tag-color) 78%, black);
    padding: .2rem .3rem .2rem .5rem;
    font-size: .75rem;
    font-weight: 750;
  }

  .selected-tag button {
    display: grid;
    width: 1.15rem;
    height: 1.15rem;
    place-items: center;
    border: 0;
    border-radius: 50%;
    background: transparent;
    color: inherit;
    padding: 0;
    font-size: .9rem;
    line-height: 1;
  }

  .selected-tag button:hover { background: rgba(0, 0, 0, .08); }

  .picker-control { position: relative; }
  .picker-control input { width: 100%; }

  .tag-options {
    position: absolute;
    z-index: 10;
    top: calc(100% + .25rem);
    left: 0;
    right: 0;
    max-height: 18rem;
    overflow-y: auto;
    border: 1px solid #cbc8be;
    border-radius: .6rem;
    background: #fff;
    box-shadow: 0 14px 34px rgba(20, 27, 23, .18);
    padding: .3rem;
  }

  .tag-options > button {
    display: grid;
    width: 100%;
    grid-template-columns: 1rem minmax(0, 1fr);
    gap: .5rem;
    border: 0;
    border-radius: .45rem;
    background: transparent;
    color: var(--ink);
    padding: .48rem .55rem .48rem calc(.55rem + var(--tag-indent, 0rem));
    text-align: left;
  }

  .tag-options > button:hover,
  .tag-options > button.selected { background: #f2f3ef; }

  .option-check { color: var(--forest-2); font-weight: 900; }
  .option-copy { display: grid; min-width: 0; gap: .1rem; }
  .option-copy strong { font-size: .8rem; }
  .option-copy small {
    overflow: hidden;
    color: var(--muted);
    font-size: .68rem;
    line-height: 1.25;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .create-tag { border-top: 1px solid #ebe7dd !important; margin-top: .2rem; color: var(--forest-2) !important; }
  .tag-empty { display: block; padding: .6rem; color: var(--muted); font-size: .78rem; }

  .inline-tag-create {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) 5rem;
    gap: .45rem;
    border: 1px solid #d8d5ca;
    border-radius: .6rem;
    background: #f8f8f5;
    padding: .55rem;
  }

  .inline-tag-create label {
    display: grid;
    min-width: 0;
    gap: .2rem;
    color: var(--muted);
    font-size: .68rem;
    font-weight: 750;
  }

  .inline-tag-create input,
  .inline-tag-create select {
    width: 100%;
    min-width: 0;
  }

  .color-input input { min-height: 2.35rem; padding: .15rem; }

  .inline-create-actions {
    display: flex;
    grid-column: 1 / -1;
    justify-content: flex-end;
    gap: .4rem;
  }

  .inline-create-actions button:not(.primary) {
    border: 1px solid #cbc8be;
    border-radius: .5rem;
    background: #fff;
    color: var(--ink);
    padding: .45rem .65rem;
  }

  @media (max-width: 640px) {
    .inline-tag-create { grid-template-columns: 1fr; }
    .inline-create-actions { grid-column: auto; }
  }
</style>
