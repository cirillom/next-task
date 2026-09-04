<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../api/client';
  import type { PomodoroSettings } from '../api/types';

  const dispatch = createEventDispatcher<{ start: void }>();
  let settings: PomodoroSettings | null = null;
  let error = '';

  onMount(async () => {
    try {
      settings = await api.pomodoroSettings();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load Pomodoro settings';
    }
  });
</script>

<section class="pomodoro-launcher" aria-label="Pomodoro focus">
  <div class="pomodoro-icon" aria-hidden="true">
    <svg viewBox="0 0 24 24">
      <circle cx="12" cy="13" r="7.5" />
      <path d="M9.5 4.8c.7-1 1.55-1.55 2.5-1.8.1 1.2-.15 2.15-.75 2.85" />
      <path d="M12.2 5.3c1.15-.7 2.25-.8 3.3-.35" />
    </svg>
  </div>
  <div class="pomodoro-copy">
    <p class="eyebrow">Focus mode</p>
    <h2>Start a Pomodoro</h2>
    {#if settings}
      <p>{settings.focus_minutes} min focus · {settings.short_break_minutes} min short break · {settings.long_break_minutes} min long break</p>
    {:else if error}
      <p class="error">{error}</p>
    {:else}
      <p>Loading your focus rhythm…</p>
    {/if}
  </div>
  <button class="primary start-button" disabled={!settings} on:click={() => dispatch('start')}>
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 7 8 5-8 5Z" /></svg>
    Start focus
  </button>
</section>

<style>
  .pomodoro-launcher {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
    align-items: center;
    gap: 1rem;
    margin-bottom: 1rem;
    padding: 1rem 1.1rem;
    border: 1px solid #e3c9bd;
    border-radius: .85rem;
    background: linear-gradient(135deg, #fff9f5, #fffdf9);
    box-shadow: 0 8px 24px rgba(80, 50, 35, .05);
  }

  .pomodoro-icon {
    display: grid;
    width: 2.8rem;
    height: 2.8rem;
    place-items: center;
    border-radius: .8rem;
    background: #f8e2d8;
    color: #9a4d36;
  }

  .pomodoro-icon svg,
  .start-button svg {
    width: 1.3rem;
    height: 1.3rem;
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
  .pomodoro-copy h2,
  .pomodoro-copy p {
    margin: 0;
  }

  .pomodoro-copy h2 {
    margin-top: .1rem;
    font-size: 1.05rem;
  }

  .pomodoro-copy p:last-child {
    margin-top: .25rem;
    color: var(--muted);
    font-size: .82rem;
  }

  .start-button {
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    white-space: nowrap;
  }

  @media (max-width: 680px) {
    .pomodoro-launcher {
      grid-template-columns: auto 1fr;
    }

    .start-button {
      grid-column: 1 / -1;
      justify-content: center;
    }
  }
</style>
