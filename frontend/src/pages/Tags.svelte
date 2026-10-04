<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { Tag, TagMergePreview, Workspace } from '../lib/api/types';
  import { tagHierarchyOrder, tagHierarchyPaths, tagHierarchyRows } from '../lib/tagHierarchy';
  import TagBadge from '../lib/components/TagBadge.svelte';
  import AppButton from '../lib/components/AppButton.svelte';
  import TextField from '../lib/components/TextField.svelte';
  import TagSelect from '../lib/components/TagSelect.svelte';
  import TextArea from '../lib/components/TextArea.svelte';
  import NumberField from '../lib/components/NumberField.svelte';

  const SUGGESTED_TAG_COLORS = [
    '#587b6a',
    '#5f6f8f',
    '#8a6f5a',
    '#7b658e',
    '#4f7f86',
    '#8c625e',
    '#6f7f4f',
    '#9a7048',
    '#536f83',
    '#8a6678',
    '#607b73',
    '#7d7150'
  ];

  function randomTagColor(): string {
    return SUGGESTED_TAG_COLORS[Math.floor(Math.random() * SUGGESTED_TAG_COLORS.length)];
  }

  export let workspace: Workspace;

  let tags: Tag[] = [];
  let search = '';
  let selectedId = 0;
  let expandedIds = new Set<number>();
  let expandedInitialized = false;

  let creating = false;
  let createName = '';
  let createDescription = '';
  let createColor = randomTagColor();
  let createScoreValue = 0;
  let createParentChoice = 0;
  let parentDraft: { tagId: number; name: string; description: string; color: string; scoreValue: number; parentChoice: number } | null = null;

  let editName = '';
  let editDescription = '';
  let editColor = '';
  let editScoreValue = 0;
  let parentChoice = 0;

  let mergeOpen = false;
  let mergeDestinationId = 0;
  let mergePreview: TagMergePreview | null = null;
  let mergeError = '';
  let mergeLoading = false;

  let error = '';
  let busy = false;

  $: selectedTag = tags.find((tag) => tag.id === selectedId) || null;
  $: parentTagValue = selectedTag?.ancestors.reduce((sum, ancestor) => sum + ancestor.score_value, 0) ?? 0;
  $: hierarchyRows = tagHierarchyRows(tags, search);
  $: visibleRows = search.trim()
    ? hierarchyRows
    : hierarchyRows.filter((row) =>
        row.ancestorIds.every((ancestorId) => expandedIds.has(ancestorId))
      );
  $: parentOptions = selectedTag
    ? tagHierarchyOrder(tags).filter(
        ({ tag: candidate }) =>
          candidate.id !== selectedTag!.id &&
          !selectedTag!.parents.some((parent) => parent.id === candidate.id) &&
          !candidate.ancestors.some((ancestor) => ancestor.id === selectedTag!.id)
      )
    : [];
  $: mergeOptions = selectedTag
    ? tags
        .filter((candidate) => candidate.id !== selectedTag!.id)
        .sort((left, right) => left.name.localeCompare(right.name))
    : [];
  $: mergeDestination =
    tags.find((tag) => tag.id === Number(mergeDestinationId)) || null;

  function setEditFields(tag: Tag) {
    editName = tag.name;
    editDescription = tag.description || '';
    editColor = tag.color || '#587b6a';
    editScoreValue = tag.score_value;
    parentChoice = 0;
  }

  function selectTag(tag: Tag) {
    creating = false;
    mergeOpen = false;
    mergeDestinationId = 0;
    mergePreview = null;
    mergeError = '';
    selectedId = tag.id;
    setEditFields(tag);
  }

  function selectTagById(tagId: number) {
    const tag = tags.find((item) => item.id === tagId);
    if (tag) selectTag(tag);
  }

  function toggleExpanded(tagId: number) {
    const next = new Set(expandedIds);
    if (next.has(tagId)) next.delete(tagId);
    else next.add(tagId);
    expandedIds = next;
  }

  async function load(preferredId = selectedId) {
    try {
      const loaded = await api.tags(workspace.id);
      tags = loaded;

      if (!expandedInitialized) {
        expandedIds = new Set(loaded.map((tag) => tag.id));
        expandedInitialized = true;
      }

      const selected = loaded.find((tag) => tag.id === preferredId) || loaded[0] || null;
      if (selected) selectTag(selected);
      else selectedId = 0;
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load tags';
    }
  }

  function startCreate() {
    parentDraft = null;
    const searchedName = search.trim();
    const existingTag = tags.some((tag) => tag.name.toLowerCase() === searchedName.toLowerCase());

    creating = true;
    selectedId = 0;
    createName = searchedName && !existingTag ? searchedName : '';
    search = '';
    createDescription = '';
    createColor = randomTagColor();
    createScoreValue = 0;
    createParentChoice = 0;
    error = '';
  }

  function startCreateParent(name: string) {
    if (!creating && !selectedTag) return;
    parentDraft = creating
      ? { tagId: 0, name: createName, description: createDescription, color: createColor, scoreValue: createScoreValue, parentChoice: createParentChoice }
      : { tagId: selectedTag!.id, name: editName, description: editDescription, color: editColor, scoreValue: editScoreValue, parentChoice: parentChoice };
    createName = name;
    createDescription = '';
    createColor = randomTagColor();
    createScoreValue = 0;
    createParentChoice = 0;
    creating = true;
    error = '';
  }

  function restoreParentDraft(newParentId = 0) {
    if (!parentDraft) return;
    if (parentDraft.tagId) {
      selectedId = parentDraft.tagId;
      editName = parentDraft.name;
      editDescription = parentDraft.description;
      editColor = parentDraft.color;
      editScoreValue = parentDraft.scoreValue;
      parentChoice = parentDraft.parentChoice;
      creating = false;
    } else {
      selectedId = 0;
      createName = parentDraft.name;
      createDescription = parentDraft.description;
      createColor = parentDraft.color;
      createScoreValue = parentDraft.scoreValue;
      createParentChoice = newParentId || parentDraft.parentChoice;
      creating = true;
    }
    parentDraft = null;
  }

  async function create() {
    busy = true;
    error = '';
    try {
      const created = await api.createTag(workspace.id, {
        name: createName,
        description: createDescription,
        color: createColor,
        score_value: createScoreValue,
        parent_tag_id: createParentChoice || null
      });
      if (parentDraft) {
        const draft = parentDraft;
        if (draft.tagId) {
          try {
            await api.addTagParent(workspace.id, draft.tagId, created.id);
          } finally {
            await load(draft.tagId);
            restoreParentDraft();
          }
        } else {
          tags = await api.tags(workspace.id);
          restoreParentDraft(created.id);
        }
      } else {
        await load(created.id);
      }
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not create tag';
    } finally {
      busy = false;
    }
  }

  async function saveEdit() {
    if (!selectedTag) return;
    busy = true;
    error = '';
    try {
      await api.updateTag(workspace.id, selectedTag.id, {
        name: editName,
        description: editDescription,
        color: editColor,
        score_value: editScoreValue
      });
      await load(selectedTag.id);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not update tag';
    } finally {
      busy = false;
    }
  }

  async function addParent(parentId: number) {
    if (!selectedTag || !parentId) return;
    const tagId = selectedTag.id;
    const draft = { name: editName, description: editDescription, color: editColor, scoreValue: editScoreValue };
    busy = true;
    error = '';
    try {
      await api.addTagParent(workspace.id, tagId, parentId);
      await load(tagId);
      editName = draft.name;
      editDescription = draft.description;
      editColor = draft.color;
      editScoreValue = draft.scoreValue;
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not add parent';
    } finally {
      busy = false;
    }
  }

  async function removeParent(parentId: number) {
    if (!selectedTag) return;
    busy = true;
    error = '';
    try {
      await api.removeTagParent(workspace.id, selectedTag.id, parentId);
      await load(selectedTag.id);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not remove parent';
    } finally {
      busy = false;
    }
  }

  function startMerge() {
    mergeOpen = true;
    mergeDestinationId = 0;
    mergePreview = null;
    mergeError = '';
  }

  function cancelMerge() {
    mergeOpen = false;
    mergeDestinationId = 0;
    mergePreview = null;
    mergeError = '';
  }

  async function loadMergePreview() {
    if (!selectedTag || !mergeDestinationId) {
      mergePreview = null;
      mergeError = '';
      return;
    }

    mergeLoading = true;
    mergePreview = null;
    mergeError = '';
    try {
      mergePreview = await api.tagMergePreview(
        workspace.id,
        selectedTag.id,
        Number(mergeDestinationId)
      );
    } catch (reason) {
      mergeError = reason instanceof Error ? reason.message : 'Could not preview tag merge';
    } finally {
      mergeLoading = false;
    }
  }

  async function confirmMerge() {
    if (!selectedTag || !mergeDestination || !mergePreview) return;
    busy = true;
    mergeError = '';
    try {
      const merged = await api.mergeTag(workspace.id, selectedTag.id, mergeDestination.id);
      mergeOpen = false;
      await load(merged.id);
    } catch (reason) {
      mergeError = reason instanceof Error ? reason.message : 'Could not merge tags';
    } finally {
      busy = false;
    }
  }

  async function remove() {
    if (!selectedTag || !window.confirm(`Delete ${selectedTag.name}? It will be removed from tasks.`)) {
      return;
    }

    busy = true;
    error = '';
    try {
      await api.deleteTag(workspace.id, selectedTag.id);
      selectedId = 0;
      await load(0);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not delete tag';
    } finally {
      busy = false;
    }
  }

  onMount(() => void load());
</script>

<div class="page-heading">
  <div>
    <p class="eyebrow">Tag Studio</p>
    <h1>Tags</h1>
  </div>
</div>
<p class="page-intro">Browse the tag hierarchy, inspect direct usage, and reorganize parent relationships.</p>

{#if error}<p class="error" role="alert">{error}</p>{/if}

<div class="tag-manager">
  <aside class="panel hierarchy-browser">
    <div class="browser-toolbar">
      <TextField bind:value={search} type="search" aria-label="Search tags" placeholder="Search tags" />
      {#if workspace.role !== 'viewer'}
        <AppButton variant="primary" on:click={startCreate}>New tag</AppButton>
      {/if}
    </div>

    {#if !tags.length}
      <p class="empty">No tags yet.</p>
    {:else if !visibleRows.length}
      <p class="empty">No matching tags.</p>
    {:else}
      <div class="tag-tree" role="tree" aria-label="Tag hierarchy">
        {#each visibleRows as row (row.key)}
          <div
            class="tree-row"
            class:selected={row.tag.id === selectedId}
            style:--tag-depth={`${row.depth}rem`}
            role="treeitem"
            aria-level={row.depth + 1}
            aria-selected={row.tag.id === selectedId}
          >
            {#if row.hasChildren}
              <button
                type="button"
                class="expand-button"
                aria-label={expandedIds.has(row.tag.id) ? `Collapse ${row.tag.name}` : `Expand ${row.tag.name}`}
                on:click={() => toggleExpanded(row.tag.id)}
              >{expandedIds.has(row.tag.id) || search.trim() ? '▾' : '▸'}</button>
            {:else}
              <span class="expand-spacer"></span>
            {/if}
            <button type="button" class="tag-select" on:click={() => selectTag(row.tag)}>
              <span class="tree-copy">
                <TagBadge tag={row.tag} selected={row.tag.id === selectedId} />
                {#if search.trim() || row.tag.parents.length > 1}<small>{row.path}</small>{/if}
              </span>
              <span class="usage-badge" title="Direct task usage">{row.tag.direct_task_count}</span>
            </button>
          </div>
        {/each}
      </div>
    {/if}
  </aside>

  <section class="panel tag-details">
    {#if creating}
      <header class="details-heading">
        <div>
          <p class="eyebrow">New tag</p>
          <h2>Create tag</h2>
        </div>
      </header>
      <form class="detail-form" on:submit|preventDefault={create}>
        <label>Name<TextField bind:value={createName} maxlength="120" required /></label>
        <label class="color-field">Color<input type="color" bind:value={createColor} /></label>
        <label>Tag value<NumberField step="any" bind:value={createScoreValue} required /></label>
        <p class="wide muted">Tag values contribute to task ranking through tagValue. Parent tag values are included once.</p>
        <label class="wide">Description<TextArea bind:value={createDescription} rows="4" /></label>
        <label class="wide">Parent tags
          <TagSelect bind:value={createParentChoice} options={tagHierarchyOrder(tags)} existingNames={tags.map((tag) => tag.name)} searchable allowCreate={!parentDraft} emptyLabel="Choose a parent tag..." label="Parent tag" disabled={busy} on:create={(event) => startCreateParent(event.detail)} />
        </label>
        <div class="detail-actions">
          <AppButton on:click={() => { creating = false; restoreParentDraft(); }}>Cancel</AppButton>
          <AppButton type="submit" variant="primary" disabled={busy}>Create tag</AppButton>
        </div>
      </form>
    {:else if selectedTag}
      <header class="details-heading">
        <div>
          <p class="eyebrow">Tag details</p>
          <h2><TagBadge tag={selectedTag} /></h2>
        </div>
        <span class="usage-summary">{selectedTag.direct_task_count} direct {selectedTag.direct_task_count === 1 ? 'task' : 'tasks'}</span>
      </header>

      {#if tagHierarchyPaths(selectedTag, tags).some((path) => path !== selectedTag.name)}
        <div class="path-list">
          <strong>Hierarchy paths</strong>
          {#each tagHierarchyPaths(selectedTag, tags) as path}
            <span>{path}</span>
          {/each}
        </div>
      {/if}

      <form class="detail-form" on:submit|preventDefault={saveEdit}>
        <label>Name<TextField bind:value={editName} maxlength="120" required disabled={workspace.role === 'viewer'} /></label>
        <label class="color-field">Color<input type="color" bind:value={editColor} disabled={workspace.role === 'viewer'} /></label>
        <label>Tag value<NumberField step="any" bind:value={editScoreValue} required disabled={workspace.role === 'viewer'} /></label>
        <p class="wide muted">Parent tag values (all levels): {parentTagValue}. Current total: {selectedTag.score_value + parentTagValue}.</p>
        <label class="wide">Description<TextArea bind:value={editDescription} rows="4" disabled={workspace.role === 'viewer'} /></label>
        {#if workspace.role !== 'viewer'}
          <div class="detail-actions wide">
            <AppButton type="submit" variant="primary" disabled={busy}>Save details</AppButton>
          </div>
        {/if}
      </form>

      <div class="relationship-section">
        <div class="relationship-heading">
          <strong>Parent tags</strong>
          <span>{selectedTag.parents.length}</span>
        </div>
        {#if selectedTag.parents.length}
          <div class="relationship-tags">
            {#each selectedTag.parents as parent}
              <span>
                <button type="button" class="relationship-link" on:click={() => selectTagById(parent.id)}><TagBadge tag={parent} /></button>
                {#if workspace.role !== 'viewer'}
                  <button type="button" class="remove-relation" aria-label={`Remove parent ${parent.name}`} disabled={busy} on:click={() => void removeParent(parent.id)}>×</button>
                {/if}
              </span>
            {/each}
          </div>
        {:else}
          <p class="muted">No parent tags.</p>
        {/if}

        {#if workspace.role !== 'viewer'}
          <TagSelect bind:value={parentChoice} options={parentOptions} existingNames={tags.map((tag) => tag.name)} searchable emptyLabel="Choose a parent tag..." label="Parent tag" disabled={busy} on:change={(event) => void addParent(Number(event.detail))} on:create={(event) => startCreateParent(event.detail)} />
        {/if}
      </div>

      <div class="relationship-section">
        <div class="relationship-heading">
          <strong>Direct children</strong>
          <span>{selectedTag.children.length}</span>
        </div>
        {#if selectedTag.children.length}
          <div class="children-list">
            {#each selectedTag.children as child}
              <button type="button" on:click={() => selectTagById(child.id)}><TagBadge tag={child} /></button>
            {/each}
          </div>
        {:else}
          <p class="muted">No direct children.</p>
        {/if}
      </div>

      {#if workspace.role !== 'viewer'}
        {#if mergeOpen}
          <section class="merge-panel" aria-label="Merge tag">
            <div class="relationship-heading">
              <strong>Merge into…</strong>
              <AppButton disabled={busy} on:click={cancelMerge}>Cancel</AppButton>
            </div>

            <TagSelect
              bind:value={mergeDestinationId}
              options={mergeOptions.map((tag) => ({ tag }))}
              emptyLabel="Choose destination tag…"
              label="Merge destination tag"
              disabled={busy || mergeLoading}
              on:change={() => void loadMergePreview()}
            />

            {#if mergeLoading}
              <p class="muted">Checking merge…</p>
            {:else if mergeError}
              <p class="error merge-error" role="alert">{mergeError}</p>
            {:else if mergePreview && mergeDestination}
              <div class="merge-summary">
                <strong>Merge “{selectedTag.name}” into “{mergeDestination.name}”</strong>
                <span>{mergePreview.task_assignments} task {mergePreview.task_assignments === 1 ? 'assignment' : 'assignments'} will move</span>
                <span>{mergePreview.parent_relationships} parent {mergePreview.parent_relationships === 1 ? 'relationship' : 'relationships'} will move</span>
                <span>{mergePreview.child_relationships} child {mergePreview.child_relationships === 1 ? 'relationship' : 'relationships'} will move</span>
                <span>“{selectedTag.name}” will be deleted</span>
              </div>
              <div class="merge-actions">
                <AppButton disabled={busy} on:click={cancelMerge}>Cancel</AppButton>
                <AppButton variant="danger" disabled={busy} on:click={() => void confirmMerge()}>
                  {busy ? 'Merging…' : 'Merge tags'}
                </AppButton>
              </div>
            {/if}
          </section>
        {/if}

        <div class="danger-zone">
          <AppButton disabled={busy || mergeOpen} on:click={startMerge}>Merge into…</AppButton>
          <AppButton variant="danger" disabled={busy || mergeOpen} on:click={() => void remove()}>Delete tag</AppButton>
        </div>
      {/if}
    {:else}
      <p class="empty">Select a tag to inspect it.</p>
    {/if}
  </section>
</div>

<style>
  .tag-manager {
    display: grid;
    grid-template-columns: minmax(18rem, 1fr) minmax(24rem, 1.45fr);
    gap: 1rem;
    align-items: start;
  }

  .hierarchy-browser,
  .tag-details { min-width: 0; }

  .browser-toolbar {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: .55rem;
    margin-bottom: .75rem;
  }

  .tag-tree {
    display: grid;
    max-height: 65vh;
    overflow-y: auto;
    padding: .15rem;
  }

  .tree-row {
    display: grid;
    grid-template-columns: 1.4rem minmax(0, 1fr);
    align-items: stretch;
    padding-left: var(--tag-depth);
    border-radius: .5rem;
  }

  .tree-row:hover,
  .tree-row.selected { background: #f2f3ef; }

  .expand-button {
    width: 1.4rem;
    border: 0;
    background: transparent;
    color: var(--muted);
    padding: 0;
    font-size: .78rem;
  }

  .expand-spacer { width: 1.4rem; }

  .tag-select {
    display: grid;
    width: 100%;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: .45rem;
    border: 0;
    background: transparent;
    color: var(--ink);
    padding: .45rem .5rem;
    text-align: left;
  }

  .tree-copy { display: grid; min-width: 0; gap: .08rem; }
  .tree-copy small { overflow: hidden; color: var(--muted); font-size: .67rem; text-overflow: ellipsis; white-space: nowrap; }

  .usage-badge {
    min-width: 1.35rem;
    border-radius: 999px;
    background: #eceee9;
    color: var(--muted);
    padding: .12rem .38rem;
    font-size: .68rem;
    font-weight: 750;
    text-align: center;
  }

  .details-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    border-bottom: 1px solid var(--line);
    padding-bottom: .8rem;
  }

  .details-heading h2 { margin: .1rem 0 0; }
  .usage-summary {
    flex: 0 0 auto;
    border-radius: 999px;
    background: #eef2ef;
    color: var(--forest-2);
    padding: .32rem .55rem;
    font-size: .72rem;
    font-weight: 750;
  }

  .path-list {
    display: grid;
    gap: .25rem;
    margin-top: .8rem;
    color: var(--muted);
    font-size: .75rem;
  }

  .path-list strong { color: var(--ink); }
  .path-list span { padding-left: .15rem; }

  .detail-form {
    display: grid;
    grid-template-columns: minmax(0, 1fr) 7rem;
    gap: .65rem;
    margin-top: .9rem;
  }

  .detail-form label { display: grid; gap: .3rem; font-weight: 700; }
  .detail-form .wide { grid-column: 1 / -1; }
  .color-field input { width: 100%; min-height: 2.4rem; padding: .2rem; }
  .detail-actions { display: flex; justify-content: flex-end; gap: .45rem; }
  .detail-actions.wide { grid-column: 1 / -1; }

  .relationship-section {
    display: grid;
    gap: .55rem;
    margin-top: 1rem;
    border-top: 1px solid var(--line);
    padding-top: .85rem;
  }

  .relationship-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .75rem;
  }

  .relationship-heading span { color: var(--muted); font-size: .75rem; }

  .relationship-tags,
  .children-list {
    display: flex;
    flex-wrap: wrap;
    gap: .35rem;
  }

  .relationship-tags > span {
    display: inline-flex;
    align-items: center;
    overflow: hidden;
    border: 0;
    border-radius: 999px;
    background: transparent;
  }

  .relationship-link,
  .children-list button { border: 0; background: transparent; padding: 0; }

  .relationship-link:hover,
  .children-list button:hover { text-decoration: underline; text-underline-offset: .12rem; }

  .remove-relation {
    width: 1.45rem;
    align-self: stretch;
    border: 0;
    border-left: 1px solid #d7d8d2;
    border-radius: 0;
    background: transparent;
    color: var(--muted);
    padding: 0;
  }

  .muted { margin: 0; color: var(--muted); font-size: .8rem; }

  .merge-panel {
    display: grid;
    gap: .6rem;
    margin-top: 1rem;
    border: 1px solid #d7d8d2;
    border-radius: .65rem;
    background: #f8f8f5;
    padding: .75rem;
  }

  .merge-summary {
    display: grid;
    gap: .25rem;
    border-radius: .5rem;
    background: #fff;
    padding: .65rem;
    color: var(--muted);
    font-size: .76rem;
  }

  .merge-summary strong { color: var(--ink); margin-bottom: .1rem; }
  .merge-error { margin: 0; }

  .merge-actions {
    display: flex;
    justify-content: flex-end;
    gap: .45rem;
  }

  .danger-zone {
    display: flex;
    justify-content: flex-end;
    gap: .45rem;
    margin-top: 1rem;
    border-top: 1px solid var(--line);
    padding-top: .85rem;
  }

  @media (max-width: 800px) {
    .tag-manager { grid-template-columns: 1fr; }
    .tag-tree { max-height: 45vh; }
  }

  @media (max-width: 520px) {
    .browser-toolbar,
    .detail-form { grid-template-columns: 1fr; }
    .detail-form .wide,
    .detail-actions.wide { grid-column: auto; }
    .details-heading { align-items: flex-start; flex-direction: column; }
  }
</style>
