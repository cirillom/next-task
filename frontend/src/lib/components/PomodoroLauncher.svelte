<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../api/client';
  import type { PomodoroSession, PomodoroSettings, Tag } from '../api/types';

  export let tags: Tag[] = [];
  export let recommendedTaskTitle = '';

  const dispatch = createEventDispatcher<{ start: number | null; scopeChange: number | null }>();
  let settings: PomodoroSettings | null = null;
  let activeSession: PomodoroSession | null = null;
  let activeRemainingSeconds = 0;
  let serverClockOffset = 0;
  let refreshTicks = 0;
  let timer: number;
  let selectedTagId = '';
  let error = '';

  function updateRemaining() {
    if (activeSession?.state !== 'running' || !activeSession.ends_at) {
      activeRemainingSeconds = 0;
      return;
    }
    activeRemainingSeconds = Math.max(
      0,
      Math.ceil((Date.parse(activeSession.ends_at) - (Date.now() + serverClockOffset)) / 1000)
    );
  }

  async function refreshSession() {
    try {
      activeSession = await api.pomodoroSession();
      if (activeSession) serverClockOffset = Date.parse(activeSession.server_now) - Date.now();
      updateRemaining();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load Pomodoro settings';
    }
  }

  function activePhaseLabel(): string {
    if (!activeSession) return '';
    if (activeSession.phase === 'focus') return 'Focus';
    if (activeSession.phase === 'long-break') return 'Long break';
    return 'Short break';
  }

  function formatTime(total: number): string {
    return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
  }

  onMount(() => {
    void (async () => {
      try {
        settings = await api.pomodoroSettings();
        await refreshSession();
      } catch (reason) {
        error = reason instanceof Error ? reason.message : 'Could not load Pomodoro settings';
      }
    })();
    timer = window.setInterval(() => {
      updateRemaining();
      refreshTicks += 1;
      if (refreshTicks % 5 === 0) void refreshSession();
    }, 1000);
    return () => window.clearInterval(timer);
  });

  function selectedScope(): number | null {
    return selectedTagId ? Number(selectedTagId) : null;
  }

  function changeScope() {
    dispatch('scopeChange', selectedScope());
  }

  function startSession() {
    dispatch('start', selectedScope());
  }
</script>

<section class="pomodoro-launcher" aria-label="Pomodoro session">
  <div class="pomodoro-icon" aria-hidden="true">
    <svg viewBox="0 0 24 24">
      <circle cx="12" cy="13" r="7.5" />
      <path d="M9.5 4.8c.7-1 1.55-1.55 2.5-1.8.1 1.2-.15 2.15-.75 2.85" />
      <path d="M12.2 5.3c1.15-.7 2.25-.8 3.3-.35" />
    </svg>
  </div>

  <div class="pomodoro-copy">
    <p class="eyebrow">Pomodoro</p>
    {#if activeSession?.state === 'running'}
      <p>{activePhaseLabel()} · {formatTime(activeRemainingSeconds)} remaining · synced across devices</p>
    {:else if activeSession?.state === 'ringing'}
      <p>Alarm ringing · continue to dismiss it</p>
    {:else if activeSession}
      <p>{activePhaseLabel()} ready · synced across devices</p>
    {:else if settings}
      <p>{settings.focus_minutes} min focus · {settings.short_break_minutes} min break · {settings.long_break_minutes} min long break</p>
    {:else if error}
      <p class="error">{error}</p>
    {:else}
      <p>Loading focus settings…</p>
    {/if}
  </div>

  <label class="tag-filter">
    <span>Session tag</span>
    <select bind:value={selectedTagId} disabled={!!activeSession} on:change={changeScope}>
      <option value="">All tags</option>
      {#each tags as tag}
        <option value={tag.id}>#{tag.name}</option>
      {/each}
    </select>
    <small>{activeSession ? 'The active session keeps its original scope.' : 'Includes child tags.'}</small>
  </label>

  <button
    class="primary start-button"
    disabled={!settings || (!activeSession && !recommendedTaskTitle)}
    aria-label={activeSession ? 'Continue active Pomodoro' : recommendedTaskTitle ? `Start Pomodoro with ${recommendedTaskTitle}` : 'Start Pomodoro'}
    title={activeSession ? 'Continue the Pomodoro active on your account' : recommendedTaskTitle ? `Start with ${recommendedTaskTitle}` : 'No recommended task in this scope'}
    on:click={startSession}
  >
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 7 8 5-8 5Z" /></svg>
    {activeSession ? 'Continue Pomodoro' : 'Start Pomodoro'}
  </button>
</section>

<style>
  .pomodoro-launcher {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) minmax(10rem, 14rem) auto;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
    padding: .85rem 1.1rem;
    border: 1px solid #e3c9bd;
    border-left: 5px solid #a65038;
    border-radius: .85rem;
    background: linear-gradient(135deg, #fff9f5, #fffdf9);
    box-shadow: 0 8px 24px rgba(80, 50, 35, .05);
  }

  .pomodoro-icon {
    display: grid;
    width: 2.5rem;
    height: 2.5rem;
    place-items: center;
    border-radius: .7rem;
    background: #f8e2d8;
    color: #9a4d36;
  }

  .pomodoro-icon svg,
  .start-button svg {
    width: 1.2rem;
    height: 1.2rem;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
  }

  .start-button svg {
    width: 1rem;
    height: 1rem;
    fill: currentColor;
    stroke: none;
  }

  .pomodoro-copy .eyebrow,
  .pomodoro-copy p {
    margin: 0;
  }

  .pomodoro-copy p:last-child {
    margin-top: .2rem;
    color: var(--muted);
    font-size: .8rem;
  }

  .tag-filter {
    display: grid;
    gap: .2rem;
    margin: 0;
    font-size: .72rem;
    font-weight: 800;
  }

  .tag-filter select {
    min-width: 0;
  }

  .tag-filter small {
    color: var(--muted);
    font-size: .68rem;
    font-weight: 500;
  }

  .start-button {
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    white-space: nowrap;
  }

  @media (max-width: 840px) {
    .pomodoro-launcher {
      grid-template-columns: auto 1fr;
    }

    .tag-filter {
      grid-column: 1 / -1;
    }

    .start-button {
      grid-column: 1 / -1;
      justify-content: center;
    }
  }
</style>
