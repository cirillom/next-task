<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { Member, Role, Workspace } from '../lib/api/types';
  import AppButton from '../lib/components/AppButton.svelte';
  import TextField from '../lib/components/TextField.svelte';
  import TextArea from '../lib/components/TextArea.svelte';

  export let workspace: Workspace;
  export let workspaces: Workspace[];
  const dispatch = createEventDispatcher<{
    select: number;
    created: Workspace;
    updated: Workspace;
    deleted: number;
  }>();

  let members: Member[] = [];
  let workspaceName = workspace.name;
  let formula = workspace.scoring_formula || '';
  let newWorkspaceName = '';
  let memberEmail = '';
  let memberRole: Role = 'editor';
  let error = '';
  let notice = '';
  let deleting = false;

  async function load() {
    try {
      members = await api.members(workspace.id);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load workspace settings';
    }
  }

  async function createWorkspace() {
    try {
      const created = await api.createWorkspace(newWorkspaceName);
      newWorkspaceName = '';
      dispatch('created', created);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not create workspace';
    }
  }

  async function saveWorkspace() {
    try {
      const updated = await api.updateWorkspace(workspace.id, {
        name: workspaceName,
        scoring_formula: formula
      });
      notice = 'Workspace settings saved.';
      dispatch('updated', updated);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not save workspace';
    }
  }

  async function deleteWorkspace() {
    if (
      !window.confirm(
        `Delete workspace “${workspace.name}”?\n\n` +
          'This permanently deletes all tasks, subtasks, tags, workspace memberships, assignments, task-tag links, and blocking history in this workspace.\n\n' +
          'User accounts will not be deleted. This action cannot be undone.'
      )
    ) return;
    deleting = true;
    error = '';
    try {
      await api.deleteWorkspace(workspace.id);
      dispatch('deleted', workspace.id);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not delete workspace';
    } finally {
      deleting = false;
    }
  }

  async function addMember() {
    try {
      await api.addMember(workspace.id, memberEmail, memberRole);
      memberEmail = '';
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not add member';
    }
  }

  async function changeRole(member: Member, role: Role) {
    try {
      await api.updateMember(workspace.id, member.user_id, role);
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not change role';
      await load();
    }
  }

  async function removeMember(member: Member) {
    if (!window.confirm(`Remove ${member.display_name} from this workspace?`)) return;
    try {
      await api.removeMember(workspace.id, member.user_id);
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not remove member';
    }
  }

  onMount(load);
</script>

<div class="page-heading"><div><p class="eyebrow">People and workflow</p><h1>Workspaces</h1></div></div>

{#if error}<p class="error" role="alert">{error}</p>{/if}
{#if notice}<p class="notice">{notice}</p>{/if}

<div class="settings-layout">
  <aside class="panel workspace-list">
    <h2>Your workspaces</h2>
    {#each workspaces as item}<button class:active={item.id === workspace.id} on:click={() => dispatch('select', item.id)}>{item.name}<small>{item.role}</small></button>{/each}
    <form on:submit|preventDefault={createWorkspace}><label>New workspace<TextField bind:value={newWorkspaceName} required placeholder="Workspace name" /></label><AppButton type="submit" variant="primary">Create</AppButton></form>
  </aside>

  <div class="settings-stack">
    {#if workspace.role === 'owner'}
      <section class="panel"><h2>Workspace settings</h2><form on:submit|preventDefault={saveWorkspace}><label>Name<TextField bind:value={workspaceName} required /></label><label>Scoring formula<TextArea className="code-input" bind:value={formula} rows="4" /></label><p class="help">Variables: priority, ageDays, idleDays, dueOffsetDays, hasDueDate, tagValue. tagValue sums assigned tags and their parents once each. Supports arithmetic, comparisons, exp(), and Python-style conditional expressions.</p><AppButton type="submit" variant="primary">Save settings</AppButton></form></section>
    {/if}

    <section class="panel"><h2>Members</h2><div class="member-list">{#each members as member}<div><span><strong>{member.display_name}</strong><small>{member.email}</small></span>{#if workspace.role === 'owner'}<select value={member.role} on:change={(event) => changeRole(member, event.currentTarget.value as Role)}><option value="owner">Owner</option><option value="editor">Editor</option><option value="viewer">Viewer</option></select><AppButton variant="danger" on:click={() => removeMember(member)}>Remove</AppButton>{:else}<span class="role-badge">{member.role}</span>{/if}</div>{/each}</div>{#if workspace.role === 'owner'}<form class="inline-control" on:submit|preventDefault={addMember}><TextField bind:value={memberEmail} placeholder="Existing username or email" autocomplete="off" required /><select bind:value={memberRole}><option value="editor">Editor</option><option value="viewer">Viewer</option><option value="owner">Owner</option></select><AppButton type="submit">Add member</AppButton></form>{/if}</section>

    {#if workspace.role === 'owner'}
      <section class="panel danger-zone">
        <p class="danger-kicker">Danger zone</p>
        <h2>Delete workspace</h2>
        <div class="danger-warning">
          <strong>This permanently deletes everything stored in “{workspace.name}”.</strong>
          <p>All tasks and subtasks, tags, workspace memberships, assignments, task-tag links, and blocking history in this workspace will be removed.</p>
          <p><strong>User accounts will not be deleted.</strong> This action cannot be undone.</p>
        </div>
        <AppButton variant="danger-solid" className="delete-workspace-button" disabled={deleting} on:click={deleteWorkspace}>{deleting ? 'Deleting workspace…' : 'Delete workspace permanently'}</AppButton>
      </section>
    {/if}
  </div>
</div>

<style>
  .danger-zone {
    border-color: color-mix(in srgb, var(--danger) 45%, var(--line));
  }

  .danger-kicker {
    margin-bottom: .35rem;
    color: var(--danger);
    font-size: .72rem;
    font-weight: 800;
    letter-spacing: .13em;
    text-transform: uppercase;
  }

  .danger-zone h2 {
    margin-bottom: .85rem;
  }

  .danger-warning {
    border: 1px solid color-mix(in srgb, var(--danger) 28%, var(--line));
    border-radius: .7rem;
    background: color-mix(in srgb, var(--danger) 8%, var(--paper));
    color: #6f2923;
    padding: 1rem;
    line-height: 1.5;
  }

  .danger-warning p {
    margin: .55rem 0 0;
  }

  :global(.delete-workspace-button) { margin-top: 1rem; }
</style>
