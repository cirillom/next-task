<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { Member, Role, Status, Workspace } from '../lib/api/types';

  export let workspace: Workspace;
  export let workspaces: Workspace[];
  const dispatch = createEventDispatcher<{ select: number; created: Workspace; updated: Workspace }>();

  let members: Member[] = [];
  let statuses: Status[] = [];
  let workspaceName = workspace.name;
  let formula = workspace.scoring_formula || '';
  let newWorkspaceName = '';
  let memberEmail = '';
  let memberRole: Role = 'editor';
  let statusName = '';
  let statusValue = 0;
  let error = '';
  let notice = '';

  async function load() {
    try {
      [members, statuses] = await Promise.all([
        api.members(workspace.id),
        api.statuses(workspace.id)
      ]);
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

  async function addStatus() {
    try {
      await api.createStatus(workspace.id, statusName, statusValue);
      statusName = '';
      statusValue = 0;
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not create status';
    }
  }

  async function saveStatus(item: Status) {
    try {
      await api.updateStatus(workspace.id, item.id, {
        name: item.name,
        score_value: item.score_value
      });
      notice = 'Status saved.';
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not save status';
      await load();
    }
  }

  async function removeStatus(item: Status) {
    if (!window.confirm(`Delete status “${item.name}”?`)) return;
    try {
      await api.deleteStatus(workspace.id, item.id);
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not delete status';
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
    <form on:submit|preventDefault={createWorkspace}><label>New workspace<input bind:value={newWorkspaceName} required placeholder="Workspace name" /></label><button class="primary">Create</button></form>
  </aside>

  <div class="settings-stack">
    {#if workspace.role === 'owner'}
      <section class="panel"><h2>Workspace settings</h2><form on:submit|preventDefault={saveWorkspace}><label>Name<input bind:value={workspaceName} required /></label><label>Scoring formula<textarea class="code-input" bind:value={formula} rows="4"></textarea></label><p class="help">Variables: priority, ageDays, idleDays, dueOffsetDays, statusValue. Supports arithmetic, comparisons, and Python-style conditional expressions.</p><button class="primary">Save settings</button></form></section>
    {/if}

    <section class="panel"><h2>Statuses</h2><div class="editable-list">{#each statuses as item}<div class="editable-row"><input bind:value={item.name} disabled={workspace.role === 'viewer'} aria-label="Status name" /><input type="number" step="any" bind:value={item.score_value} disabled={workspace.role === 'viewer'} aria-label="Score value" />{#if workspace.role !== 'viewer'}<button on:click={() => saveStatus(item)}>Save</button><button class="danger-subtle" on:click={() => removeStatus(item)}>Delete</button>{/if}</div>{/each}</div>{#if workspace.role !== 'viewer'}<form class="inline-control" on:submit|preventDefault={addStatus}><input bind:value={statusName} placeholder="New status" required /><input type="number" step="any" bind:value={statusValue} aria-label="Score value" /><button>Add status</button></form>{/if}</section>

    <section class="panel"><h2>Members</h2><div class="member-list">{#each members as member}<div><span><strong>{member.display_name}</strong><small>{member.email}</small></span>{#if workspace.role === 'owner'}<select value={member.role} on:change={(event) => changeRole(member, event.currentTarget.value as Role)}><option value="owner">Owner</option><option value="editor">Editor</option><option value="viewer">Viewer</option></select><button class="danger-subtle" on:click={() => removeMember(member)}>Remove</button>{:else}<span class="role-badge">{member.role}</span>{/if}</div>{/each}</div>{#if workspace.role === 'owner'}<form class="inline-control" on:submit|preventDefault={addMember}><input bind:value={memberEmail} placeholder="Existing username or email" autocomplete="off" required /><select bind:value={memberRole}><option value="editor">Editor</option><option value="viewer">Viewer</option><option value="owner">Owner</option></select><button>Add member</button></form>{/if}</section>
  </div>
</div>
