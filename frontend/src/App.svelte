<script lang="ts">
  import { onMount } from 'svelte';
  import { ApiError, api } from './lib/api/client';
  import type { User } from './lib/api/types';
  import AppButton from './lib/components/AppButton.svelte';
  import Login from './pages/Login.svelte';
  import Next from './pages/Next.svelte';
  import Focus from './pages/Focus.svelte';
  import Drafts from './pages/Drafts.svelte';
  import Settings from './pages/Settings.svelte';
  import Tags from './pages/Tags.svelte';
  import QuickCapture from './lib/components/QuickCapture.svelte';
  import TaskEditor from './pages/TaskEditor.svelte';
  import Tasks from './pages/Tasks.svelte';

  type View = 'next' | 'tasks' | 'drafts' | 'tags' | 'settings' | 'focus';
  const views: View[] = ['next', 'tasks', 'drafts', 'tags', 'settings', 'focus'];
  const nav: Array<{ id: Exclude<View, 'focus'>; label: string; icon: string }> = [
    { id: 'next', label: 'Next', icon: '◆' },
    { id: 'tasks', label: 'Tasks', icon: '☷' },
    { id: 'drafts', label: 'Drafts', icon: '✎' },
    { id: 'tags', label: 'Tags', icon: '#' },
    { id: 'settings', label: 'Settings', icon: '⚙' }
  ];

  let user: User | null = null;
  let view: View = 'next';
  let loading = true;
  let error = '';
  let editorTaskId: number | null = null;
  let editorBlockerTitle = '';
  let quickCaptureOpen = false;
  let draftCount = 0;
  let refreshKey = 0;
  let focusTaskVersion = 0;
  let focusTagId: number | null = null;

  async function loadDraftCount() {
    try {
      draftCount = (await api.drafts()).length;
    } catch {
      draftCount = 0;
    }
  }

  async function initialize() {
    try {
      user = await api.me();
      if (view === 'focus') {
        const activeSession = await api.pomodoroSession();
        if (activeSession) {
          focusTagId = activeSession.tag_id;
        }
      }
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
  async function logout() { await api.logout(); user = null; draftCount = 0; }

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
    editorBlockerTitle = '';
  }

  function createBlocker(request: { taskId: number; title: string }) {
    editorBlockerTitle = request.title;
    editorTaskId = request.taskId;
  }

  function quickCaptureSaved() {
    quickCaptureOpen = false;
    taskEditorChanged();
  }

  async function startFocus(tagId: number | null) {
    try {
      const activeSession = await api.pomodoroSession();
      if (activeSession) {
        focusTagId = activeSession.tag_id;
      } else {
        focusTagId = tagId;
      }
      focusTaskVersion = 0;
      navigate('focus');
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not open the Pomodoro session';
    }
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
  <main class="splash"><div class="brand-mark">✓</div><h1>Next Task</h1><p>Opening your tasks…</p></main>
{:else if !user}
  <Login on:authenticated={async (event) => { user = event.detail; await loadDraftCount(); }} />
{:else if view === 'focus'}
  <Focus
    taskVersion={focusTaskVersion}
    sessionTagId={focusTagId}
    on:openTask={(event) => openTask(event.detail)}
    on:createBlocker={(event) => createBlocker(event.detail)}
    on:end={endFocus}
  />
{:else}
  <div class="app-shell">
    <header class="topbar">
      <button class="brand" on:click={() => navigate('next')}><span class="brand-mark small">✓</span><strong>Next Task</strong></button>
      <AppButton variant="primary" className="new-task-button" on:click={() => (quickCaptureOpen = true)}>+ <span>New task</span></AppButton>
      <div class="account"><span>{user.display_name}</span><AppButton on:click={logout}>Sign out</AppButton></div>
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
    </aside>
    <main class="content">
      {#if error}<p class="error">{error}</p>{/if}
        {#key `${view}-${refreshKey}`}
          {#if view === 'next'}<Next on:openTask={(event) => openTask(event.detail)} on:createBlocker={(event) => createBlocker(event.detail)} on:startFocus={(event) => startFocus(event.detail)} />
          {:else if view === 'tasks'}<Tasks on:openTask={(event) => openTask(event.detail)} on:createBlocker={(event) => createBlocker(event.detail)} />
          {:else if view === 'drafts'}<Drafts on:openTask={(event) => openTask(event.detail)} />
          {:else if view === 'tags'}<Tags />
          {:else}<Settings {user} />{/if}
        {/key}
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
{/if}

{#if quickCaptureOpen}<QuickCapture on:close={() => (quickCaptureOpen = false)} on:saved={quickCaptureSaved} />{/if}

{#if editorTaskId !== null}
  {#key editorTaskId}
    <TaskEditor
      taskId={editorTaskId}
      initialBlockerTitle={editorBlockerTitle}
      on:close={() => (editorTaskId = null)}
      on:changed={taskEditorChanged}
      on:saved={taskEditorSaved}
      on:deleted={taskEditorDeleted}
      on:openTask={(event) => openTask(event.detail)}
    />
  {/key}
{/if}

<style>
  :global(.new-task-button) { flex: 0 0 auto; white-space: nowrap; padding: .55rem .75rem; }
  .draft-count { margin-left: auto; min-width: 1.35rem; border-radius: 999px; background: #e9eee9; padding: .08rem .38rem; color: var(--forest-2); font-size: .68rem; font-weight: 800; text-align: center; }
  .mobile-nav-icon { position: relative; }
  .mobile-nav-icon b { position: absolute; top: -.45rem; right: -.7rem; min-width: 1rem; border-radius: 999px; background: var(--forest); padding: .02rem .25rem; color: #fff; font-size: .55rem; line-height: 1rem; }

  @media (max-width: 760px) {
    :global(.new-task-button span) { display: none; }
    :global(.new-task-button) { padding: .5rem .65rem; }
  }
</style>
