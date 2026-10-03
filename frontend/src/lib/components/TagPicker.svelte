<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Tag } from '../api/types';
  import { hierarchicalTagResults, tagHierarchyPaths } from '../tagHierarchy';
  import TagBadge from './TagBadge.svelte';
  import AppButton from './AppButton.svelte';
  import TextField from './TextField.svelte';
  import TagSelect from './TagSelect.svelte';

  export let tags: Tag[] = [];
  export let selectedIds: number[] = [];
  export let suggestedNames: string[] = [];
  export let disabled = false;
  export let creating = false;
  export let allowCreate = true;
  export let displayName: (tag: Tag) => string = (tag) => tag.name;
  export let createdParentId = 0;

  const dispatch = createEventDispatcher<{
    change: number[];
    create: { name: string; parent_tag_id: number | null; color: string; asParent?: boolean };
  }>();

  let search = '';
  let open = false;
  let createOpen = false;
  let createName = '';
  let createParentId = 0;
  let createColor = '#587b6a';
  let childDraft: { name: string; parentId: number; color: string } | null = null;

  $: if (createdParentId && childDraft) {
    createName = childDraft.name;
    createParentId = createdParentId;
    createColor = childDraft.color;
    childDraft = null;
    createdParentId = 0;
  }

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
    if (childDraft) {
      createName = childDraft.name;
      createParentId = childDraft.parentId;
      createColor = childDraft.color;
      childDraft = null;
    } else {
      createOpen = false;
    }
  }

  function requestCreateParent(name: string) {
    childDraft = { name: createName, parentId: createParentId, color: createColor };
    createdParentId = 0;
    createName = name;
    createParentId = 0;
    createColor = '#587b6a';
  }

  function submitCreate() {
    const name = createName.trim();
    if (!name || creating) return;
    dispatch('create', {
      name,
      parent_tag_id: createParentId || null,
      color: createColor,
      asParent: !!childDraft
    });
    if (!childDraft) {
      createOpen = false;
      search = '';
    }
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
        <TagBadge {tag} selected>
          {displayName(tag)}
          {#if !disabled}
            <button type="button" aria-label={`Remove ${displayName(tag)}`} on:click={() => remove(tag.id)}>×</button>
          {/if}
        </TagBadge>
      {/each}
    </div>
  {/if}

  <div class="picker-control">
    <TextField
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
              <TagBadge tag={result.tag} selected={selectedIds.includes(result.tag.id)}>{displayName(result.tag)}</TagBadge>
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
            <span class="option-copy"><strong>{creating ? 'Creating…' : `Create ${search.trim()}`}</strong></span>
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
        <TextField bind:value={createName} maxlength="120" disabled={creating} />
      </label>
      <label>
        Parent tags
        <TagSelect
          bind:value={createParentId}
          options={[...tags].sort((left, right) => left.name.localeCompare(right.name)).map((tag) => ({ tag, context: tagHierarchyPaths(tag, tags)[0] }))}
          emptyLabel="Choose a parent tag..."
          label="Parent tag"
          searchable
          allowCreate={!childDraft}
          on:create={(event) => requestCreateParent(event.detail)}
          disabled={creating}
        />
      </label>
      <label class="color-input">
        Color
        <input type="color" bind:value={createColor} disabled={creating} />
      </label>
      <div class="inline-create-actions">
        <AppButton disabled={creating} on:click={cancelCreate}>Cancel</AppButton>
        <AppButton variant="primary" disabled={creating || !createName.trim()} on:click={submitCreate}>
          {creating ? 'Creating…' : 'Create and select'}
        </AppButton>
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

  .picker-control { position: relative; }

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

  .inline-tag-create input {
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

  @media (max-width: 640px) {
    .inline-tag-create { grid-template-columns: 1fr; }
    .inline-create-actions { grid-column: auto; }
  }
</style>
