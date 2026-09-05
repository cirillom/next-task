<script lang="ts">
  import { onMount } from 'svelte';
  import { ApiError, api } from './lib/api/client';
  import type { User, Workspace } from './lib/api/types';
  import Login from './pages/Login.svelte';
  import Next from './pages/Next.svelte';
  import Focus from './pages/Focus.svelte';
  import Settings from './pages/Settings.svelte';
  import Tags from './pages/Tags.svelte';
  import TextToTask from './lib/components/TextToTask.svelte';
  import TaskEditor from './pages/TaskEditor.svelte';
  import Tasks from './pages/Tasks.svelte';
  import Workspaces from './pages/Workspaces.svelte';

  type View = 'next' | 'tasks' | 'tags' | 'workspaces' | 'settings' | 'focus';
  const views: View[] = ['next', 'tasks', 'tags', 'workspaces', 'settings', 'focus'];
  const nav: Array<{ id: Exclude<View, 'focus'>; label: string; icon: string }> = [
    { id: 'next', label: 'Next', icon: '◆' },
    { id: 'tasks', label: 'Tasks', icon: '☷' },
    { id: 'tags', label: 'Tags', icon: '#' },
    { id: 'workspaces', label: 'Workspaces', icon: '◫' },
    { id: 'settings', label: 'Settings', icon: '⚙' }
  ];

  let user: User | null = null;
  let workspaces: Workspace[] = [];
  let workspace: Workspace | null = null;
  let view: View = 'next';
  let loading = true;
  let error = '';
  let editorTaskId: number | null = null;
  let textToTaskOpen = false;
  let refreshKey = 0;
  let focusTaskVersion = 0;
  let focusTagId: number | null = null;
  let firstWorkspaceName = '';

  async function loadWorkspaces(preferredId?: number) {
    workspaces = await api.workspaces();
    const storedId = Number(localStorage.getItem('next-task-workspace'));
    workspace = workspaces.find((item) => item.id === (preferredId || storedId)) || workspaces[0] || null;
    if (workspace) localStorage.setItem('next-task-workspace', String(workspace.id));
  }

  async function initialize() {
    try { user = await api.me(); await loadWorkspaces(); }
    catch (reason) {
      if (!(reason instanceof ApiError) || reason.status !== 401) error = reason instanceof Error ? reason.message : 'Could not start Next Task';
      user = null;
    } finally { loading = false; }
  }

  function readHash() {
    const requested = location.hash.replace('#/', '') as View;
    view = views.includes(requested) ? requested : 'next';
  }
  function navigate(nextView: View) { location.hash = `/${nextView}`; view = nextView; }
  function selectWorkspace(id: number) {
    workspace = workspaces.find((item) => item.id === id) || workspace;
    if (workspace) localStorage.setItem('next-task-workspace', String(workspace.id));
    refreshKey += 1;
  }
  function workspaceDeleted(id: number) {
    const deletedIndex = workspaces.findIndex((item) => item.id === id);
    const remaining = workspaces.filter((item) => item.id !== id);
    workspaces = remaining;
    workspace = remaining[Math.min(Math.max(deletedIndex, 0), remaining.length - 1)] || null;
    editorTaskId = null;
    textToTaskOpen = false;
    focusTagId = null;
    if (workspace) localStorage.setItem('next-task-workspace', String(workspace.id));
    else localStorage.removeItem('next-task-workspace');
    refreshKey += 1;
  }
  async function createFirstWorkspace() {
    try { const created = await api.createWorkspace(firstWorkspaceName); workspaces = [created]; selectWorkspace(created.id); }
    catch (reason) { error = reason instanceof Error ? reason.message : 'Could not create workspace'; }
  }
  async function logout() { await api.logout(); user = null; workspaces = []; workspace = null; }

  function taskEditorChanged() {
    if (view === 'focus') focusTaskVersion += 1;
    else refreshKey += 1;
  }

  function taskEditorSaved() {
    editorTaskId = null;
    taskEditorChanged();
  }

  function taskEditorDeleted() {
    editorTaskId = null;
    taskEditorChanged();
  }

  function startFocus(tagId: number | null) {
    focusTagId = tagId;
    focusTaskVersion = 0;
    navigate('focus');
  }

  function endFocus() {
    editorTaskId = null;
    focusTagId = null;
    navigate('next');
  }

  onMount(() => {
    readHash(); window.addEventListener('hashchange', readHash); void initialize();
    return () => window.removeEventListener('hashchange', readHash);
  });
</script>

{#if loading}
  <main class="splash"><div class="brand-mark">✓</div><h1>Next Task</h1><p>Opening your workspace…</p></main>
{:else if !user}
  <Login on:authenticated={async (event) => { user = event.detail; await loadWorkspaces(); }} />
{:else if workspace && view === 'focus'}
  <Focus
    {workspace}
    taskVersion={focusTaskVersion}
    sessionTagId={focusTagId}
    on:openTask={(event) => (editorTaskId = event.detail)}
    on:end={endFocus}
  />
{:else}
  <div class="app-shell">
    <header class="topbar">
      <button class="brand" on:click={() => navigate('next')}><span class="brand-mark small">✓</span><strong>Next Task</strong></button>
      {#if workspace}
        <div class="workspace-tools">
          <label class="workspace-switcher"><span>Workspace</span><select value={workspace.id} on:change={(event) => selectWorkspace(Number(event.currentTarget.value))}>{#each workspaces as item}<option value={item.id}>{item.name}</option>{/each}</select></label>
          {#if workspace.role !== 'viewer'}<button class="primary ai-task-button" on:click={() => (textToTaskOpen = true)}>✨ <span>Text to task</span></button>{/if}
        </div>
      {/if}
      <div class="account"><span>{user.display_name}</span><button on:click={logout}>Sign out</button></div>
    </header>
    <aside class="sidebar"><nav aria-label="Primary navigation">{#each nav as item}<button class:active={view === item.id} on:click={() => navigate(item.id)}><span>{item.icon}</span>{item.label}</button>{/each}</nav>{#if workspace}<div class="role-badge">{workspace.role}</div>{/if}</aside>
    <main class="content">
      {#if error}<p class="error">{error}</p>{/if}
      {#if !workspace}
        <section class="onboarding panel"><p class="eyebrow">Start here</p><h1>Create your first workspace</h1><p>A workspace keeps its tasks, statuses, tags, members, and score formula together.</p><form on:submit|preventDefault={createFirstWorkspace}><label>Workspace name<input bind:value={firstWorkspaceName} required placeholder="Personal" /></label><button class="primary">Create workspace</button></form></section>
      {:else}
        {#key `${workspace.id}-${view}-${refreshKey}`}
          {#if view === 'next'}<Next {workspace} on:openTask={(event) => (editorTaskId = event.detail)} on:startFocus={(event) => startFocus(event.detail)} />
          {:else if view === 'tasks'}<Tasks {workspace} on:openTask={(event) => (editorTaskId = event.detail)} />
          {:else if view === 'tags'}<Tags {workspace} />
          {:else if view === 'workspaces'}<Workspaces {workspace} {workspaces} on:select={(event) => selectWorkspace(event.detail)} on:created={(event) => { workspaces = [...workspaces, event.detail]; selectWorkspace(event.detail.id); }} on:updated={(event) => { workspaces = workspaces.map((item) => item.id === event.detail.id ? event.detail : item); workspace = event.detail; }} on:deleted={(event) => workspaceDeleted(event.detail)} />
          {:else}<Settings {user} />{/if}
        {/key}
      {/if}
    </main>
    <nav class="mobile-nav" aria-label="Primary navigation">{#each nav as item}<button class:active={view === item.id} on:click={() => navigate(item.id)}><span>{item.icon}</span><small>{item.label}</small></button>{/each}</nav>
  </div>
  {#if workspace && textToTaskOpen}<TextToTask {workspace} on:close={() => (textToTaskOpen = false)} on:saved={() => { textToTaskOpen = false; refreshKey += 1; }} />{/if}
{/if}

{#if workspace && editorTaskId !== null}
  <TaskEditor
    {workspace}
    taskId={editorTaskId}
    on:close={() => (editorTaskId = null)}
    on:changed={taskEditorChanged}
    on:saved={taskEditorSaved}
    on:deleted={taskEditorDeleted}
  />
{/if}

<style>
  .workspace-tools { min-width: 0; display: flex; align-items: center; gap: .7rem; }
  .workspace-tools .workspace-switcher { flex: 1; }
  .ai-task-button { flex: 0 0 auto; white-space: nowrap; padding: .55rem .75rem; }
  @media (max-width: 760px) {
    .workspace-tools { min-width: 0; }
    .ai-task-button span { display: none; }
    .ai-task-button { padding: .5rem .6rem; }
  }
</style>
