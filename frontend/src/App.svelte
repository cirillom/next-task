<script lang="ts">
  import { onMount } from 'svelte';
  import { ApiError, api } from './lib/api/client';
  import type { User, Workspace } from './lib/api/types';
  import Login from './pages/Login.svelte';
  import Next from './pages/Next.svelte';
  import Focus from './pages/Focus.svelte';
  import Drafts from './pages/Drafts.svelte';
  import Settings from './pages/Settings.svelte';
  import Tags from './pages/Tags.svelte';
  import QuickCapture from './lib/components/QuickCapture.svelte';
  import TaskEditor from './pages/TaskEditor.svelte';
  import Tasks from './pages/Tasks.svelte';
  import Workspaces from './pages/Workspaces.svelte';

  type View = 'next' | 'tasks' | 'drafts' | 'tags' | 'workspaces' | 'settings' | 'focus';
  const views: View[] = ['next', 'tasks', 'drafts', 'tags', 'workspaces', 'settings', 'focus'];
  const nav: Array<{ id: Exclude<View, 'focus'>; label: string; icon: string }> = [
    { id: 'next', label: 'Next', icon: '◆' },
    { id: 'tasks', label: 'Tasks', icon: '☷' },
    { id: 'drafts', label: 'Drafts', icon: '✎' },
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
  let quickCaptureOpen = false;
  let draftCount = 0;
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

  async function loadDraftCount() {
    if (!workspace) {
      draftCount = 0;
      return;
    }
    try {
      draftCount = (await api.drafts(workspace.id)).length;
    } catch {
      draftCount = 0;
    }
  }

  async function initialize() {
    try {
      user = await api.me();
      await loadWorkspaces();
      await loadDraftCount();
    } catch (reason) {
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
    void loadDraftCount();
  }
  function workspaceDeleted(id: number) {
    const deletedIndex = workspaces.findIndex((item) => item.id === id);
    const remaining = workspaces.filter((item) => item.id !== id);
    workspaces = remaining;
    workspace = remaining[Math.min(Math.max(deletedIndex, 0), remaining.length - 1)] || null;
    editorTaskId = null;
    quickCaptureOpen = false;
    focusTagId = null;
    if (workspace) localStorage.setItem('next-task-workspace', String(workspace.id));
    else localStorage.removeItem('next-task-workspace');
    refreshKey += 1;
    void loadDraftCount();
  }
  async function createFirstWorkspace() {
    try { const created = await api.createWorkspace(firstWorkspaceName); workspaces = [created]; selectWorkspace(created.id); }
    catch (reason) { error = reason instanceof Error ? reason.message : 'Could not create workspace'; }
  }
  async function logout() { await api.logout(); user = null; workspaces = []; workspace = null; draftCount = 0; }

  function taskEditorChanged() {
    if (view === 'focus') focusTaskVersion += 1;
    else refreshKey += 1;
    void loadDraftCount();
  }

  function taskEditorSaved() {
    editorTaskId = null;
    taskEditorChanged();
  }

  function taskEditorDeleted() {
    editorTaskId = null;
    taskEditorChanged();
  }

  function openTask(taskId: number) {
    if (taskId === 0) {
      quickCaptureOpen = true;
      return;
    }
    editorTaskId = taskId;
  }

  function quickCaptureSaved() {
    quickCaptureOpen = false;
    refreshKey += 1;
    void loadDraftCount();
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
  <Login on:authenticated={async (event) => { user = event.detail; await loadWorkspaces(); await loadDraftCount(); }} />
{:else if workspace && view === 'focus'}
  <Focus
    {workspace}
    taskVersion={focusTaskVersion}
    sessionTagId={focusTagId}
    on:openTask={(event) => openTask(event.detail)}
    on:end={endFocus}
  />
{:else}
  <div class="app-shell">
    <header class="topbar">
      <button class="brand" on:click={() => navigate('next')}><span class="brand-mark small">✓</span><strong>Next Task</strong></button>
      {#if workspace}
        <div class="workspace-tools">
          <label class="workspace-switcher"><span>Workspace</span><select value={workspace.id} on:change={(event) => selectWorkspace(Number(event.currentTarget.value))}>{#each workspaces as item}<option value={item.id}>{item.name}</option>{/each}</select></label>
          {#if workspace.role !== 'viewer'}<button class="primary new-task-button" on:click={() => (quickCaptureOpen = true)}>+ <span>New task</span></button>{/if}
        </div>
      {/if}
      <div class="account"><span>{user.display_name}</span><button on:click={logout}>Sign out</button></div>
    </header>
    <aside class="sidebar">
      <nav aria-label="Primary navigation">
        {#each nav as item}
          <button class:active={view === item.id} on:click={() => navigate(item.id)}>
            <span>{item.icon}</span>{item.label}
            {#if item.id === 'drafts' && draftCount > 0}<span class="draft-count">{draftCount}</span>{/if}
          </button>
        {/each}
      </nav>
      {#if workspace}<div class="role-badge">{workspace.role}</div>{/if}
    </aside>
    <main class="content">
      {#if error}<p class="error">{error}</p>{/if}
      {#if !workspace}
        <section class="onboarding panel"><p class="eyebrow">Start here</p><h1>Create your first workspace</h1><p>A workspace keeps its tasks, statuses, tags, members, and score formula together.</p><form on:submit|preventDefault={createFirstWorkspace}><label>Workspace name<input bind:value={firstWorkspaceName} required placeholder="Personal" /></label><button class="primary">Create workspace</button></form></section>
      {:else}
        {#key `${workspace.id}-${view}-${refreshKey}`}
          {#if view === 'next'}<Next {workspace} on:openTask={(event) => openTask(event.detail)} on:startFocus={(event) => startFocus(event.detail)} />
          {:else if view === 'tasks'}<Tasks {workspace} on:openTask={(event) => openTask(event.detail)} />
          {:else if view === 'drafts'}<Drafts {workspace} on:openTask={(event) => openTask(event.detail)} />
          {:else if view === 'tags'}<Tags {workspace} />
          {:else if view === 'workspaces'}<Workspaces {workspace} {workspaces} on:select={(event) => selectWorkspace(event.detail)} on:created={(event) => { workspaces = [...workspaces, event.detail]; selectWorkspace(event.detail.id); }} on:updated={(event) => { workspaces = workspaces.map((item) => item.id === event.detail.id ? event.detail : item); workspace = event.detail; }} on:deleted={(event) => workspaceDeleted(event.detail)} />
          {:else}<Settings {user} />{/if}
        {/key}
      {/if}
    </main>
    <nav class="mobile-nav" aria-label="Primary navigation">
      {#each nav as item}
        <button class:active={view === item.id} on:click={() => navigate(item.id)}>
          <span class="mobile-nav-icon">{item.icon}{#if item.id === 'drafts' && draftCount > 0}<b>{draftCount}</b>{/if}</span>
          <small>{item.label}</small>
        </button>
      {/each}
    </nav>
  </div>
  {#if workspace && quickCaptureOpen}<QuickCapture {workspace} on:close={() => (quickCaptureOpen = false)} on:saved={quickCaptureSaved} />{/if}
{/if}

{#if workspace && editorTaskId !== null}
  {#key editorTaskId}
    <TaskEditor
      {workspace}
      taskId={editorTaskId}
      on:close={() => (editorTaskId = null)}
      on:changed={taskEditorChanged}
      on:saved={taskEditorSaved}
      on:deleted={taskEditorDeleted}
      on:openTask={(event) => openTask(event.detail)}
    />
  {/key}
{/if}

<style>
  .workspace-tools { min-width: 0; display: flex; align-items: center; gap: .7rem; }
  .workspace-tools .workspace-switcher { flex: 1; }
  .new-task-button { flex: 0 0 auto; white-space: nowrap; padding: .55rem .75rem; }
  .draft-count { margin-left: auto; min-width: 1.35rem; border-radius: 999px; background: #e9eee9; padding: .08rem .38rem; color: var(--forest-2); font-size: .68rem; font-weight: 800; text-align: center; }
  .mobile-nav-icon { position: relative; }
  .mobile-nav-icon b { position: absolute; top: -.45rem; right: -.7rem; min-width: 1rem; border-radius: 999px; background: var(--forest); padding: .02rem .25rem; color: #fff; font-size: .55rem; line-height: 1rem; }

  @media (max-width: 760px) {
    .workspace-tools { min-width: 0; }
    .new-task-button span { display: none; }
    .new-task-button { padding: .5rem .65rem; }
  }
</style>
