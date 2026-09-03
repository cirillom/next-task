<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { Tag, Workspace } from '../lib/api/types';

  export let workspace: Workspace;
  let tags: Tag[] = [];
  let name = '';
  let description = '';
  let color = '#587b6a';
  let editing = 0;
  let editName = '';
  let editDescription = '';
  let editColor = '';
  let parentChoices: Record<number, number> = {};
  let error = '';
  let busy = false;

  async function load() {
    try {
      tags = await api.tags(workspace.id);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load tags';
    }
  }

  async function create() {
    busy = true;
    error = '';
    try {
      await api.createTag(workspace.id, { name, description, color });
      name = '';
      description = '';
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not create tag';
    } finally {
      busy = false;
    }
  }

  function startEdit(tag: Tag) {
    editing = tag.id;
    editName = tag.name;
    editDescription = tag.description || '';
    editColor = tag.color || '#587b6a';
  }

  async function saveEdit(tag: Tag) {
    busy = true;
    try {
      await api.updateTag(workspace.id, tag.id, {
        name: editName,
        description: editDescription,
        color: editColor
      });
      editing = 0;
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not update tag';
    } finally {
      busy = false;
    }
  }

  async function addParent(tag: Tag) {
    const parentId = Number(parentChoices[tag.id]);
    if (!parentId) return;
    try {
      await api.addTagParent(workspace.id, tag.id, parentId);
      parentChoices[tag.id] = 0;
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not relate tags';
    }
  }

  async function removeParent(tag: Tag, parentId: number) {
    try {
      await api.removeTagParent(workspace.id, tag.id, parentId);
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not remove relationship';
    }
  }

  async function remove(tag: Tag) {
    if (!window.confirm(`Delete #${tag.name}? It will be removed from tasks.`)) return;
    try {
      await api.deleteTag(workspace.id, tag.id);
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not delete tag';
    }
  }

  onMount(load);
</script>

<div class="page-heading"><div><p class="eyebrow">Tag Studio</p><h1>Tags</h1></div></div>
<p class="page-intro">Tasks store direct tags only. Parent tags are inherited automatically when filtering.</p>

{#if workspace.role !== 'viewer'}
  <form class="panel compact-form" on:submit|preventDefault={create}>
    <h2>Create tag</h2>
    <label>Name<input bind:value={name} placeholder="next-task" required /></label>
    <label>Description<input bind:value={description} placeholder="What belongs here?" /></label>
    <label>Color<input type="color" bind:value={color} /></label>
    <button class="primary" disabled={busy}>Add tag</button>
  </form>
{/if}

{#if error}<p class="error" role="alert">{error}</p>{/if}
{#if !tags.length}<p class="empty">No tags yet.</p>{/if}

<div class="tag-studio">
  {#each tags as tag (tag.id)}
    <article class="panel tag-card">
      {#if editing === tag.id}
        <div class="form-grid">
          <label>Name<input bind:value={editName} /></label>
          <label>Color<input type="color" bind:value={editColor} /></label>
          <label class="wide">Description<textarea bind:value={editDescription} rows="2"></textarea></label>
        </div>
        <div class="row-actions"><button on:click={() => (editing = 0)}>Cancel</button><button class="primary" disabled={busy} on:click={() => saveEdit(tag)}>Save</button></div>
      {:else}
        <header><div><h2><span class="color-dot" style:background={tag.color || '#73847c'}></span>#{tag.name}</h2><p>{tag.description || 'No description'}</p></div>{#if workspace.role !== 'viewer'}<div class="row-actions"><button on:click={() => startEdit(tag)}>Edit</button><button class="danger-subtle" on:click={() => remove(tag)}>Delete</button></div>{/if}</header>
      {/if}

      <div class="relationship-grid">
        <div><strong>Direct parents</strong>{#if tag.parents.length}<div class="tag-row">{#each tag.parents as parent}<span class="tag">#{parent.name}{#if workspace.role !== 'viewer'}<button aria-label={`Remove parent ${parent.name}`} on:click={() => removeParent(tag, parent.id)}>×</button>{/if}</span>{/each}</div>{:else}<p class="muted">None</p>{/if}</div>
        <div><strong>Children</strong>{#if tag.children.length}<p>{tag.children.map((item) => `#${item.name}`).join(', ')}</p>{:else}<p class="muted">None</p>{/if}</div>
        <div><strong>All inherited parents</strong>{#if tag.ancestors.length}<p>{tag.ancestors.map((item) => `#${item.name}`).join(' → ')}</p>{:else}<p class="muted">None</p>{/if}</div>
      </div>
      {#if workspace.role !== 'viewer'}
        <div class="inline-control"><select bind:value={parentChoices[tag.id]}><option value={0}>Choose a parent…</option>{#each tags.filter((candidate) => candidate.id !== tag.id && !tag.parents.some((parent) => parent.id === candidate.id)) as candidate}<option value={candidate.id}>#{candidate.name}</option>{/each}</select><button on:click={() => addParent(tag)}>Add parent</button></div>
      {/if}
    </article>
  {/each}
</div>

