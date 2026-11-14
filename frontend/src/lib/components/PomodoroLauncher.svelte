<script lang="ts">
  import { t, text, errorMessage, type Message } from '../i18n';
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../api/client';
  import type { PomodoroSession, PomodoroSettings } from '../api/types';
  import AppButton from './AppButton.svelte';

  export let recommendedTaskTitle = '';

  const dispatch = createEventDispatcher<{ start: void }>();
  let settings: PomodoroSettings | null = null;
  let activeSession: PomodoroSession | null = null;
  let activeRemainingSeconds = 0;
  let serverClockOffset = 0;
  let refreshTicks = 0;
  let timer: number;
  let error: Message = '';

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
      error = errorMessage(reason, 'ui.pomodoroLauncher.couldNotLoadPomodoroSettings');
    }
  }

  function activePhaseLabel(): string {
    if (!activeSession) return '';
    if (activeSession.phase === 'focus') return $t('ui.pomodoroLauncher.focus');
    if (activeSession.phase === 'long-break') return $t('ui.pomodoroLauncher.longBreak');
    return $t('ui.pomodoroLauncher.shortBreak');
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
        error = errorMessage(reason, 'ui.pomodoroLauncher.couldNotLoadPomodoroSettings');
      }
    })();
    timer = window.setInterval(() => {
      updateRemaining();
      refreshTicks += 1;
      if (refreshTicks % 5 === 0) void refreshSession();
    }, 1000);
    return () => window.clearInterval(timer);
  });

  function startSession() {
    dispatch('start');
  }
</script>

<section class="pomodoro-launcher" aria-label={$t('ui.pomodoroLauncher.pomodoroSession')}>
  <div class="pomodoro-icon" aria-hidden="true">
    <svg viewBox="0 0 24 24">
      <circle cx="12" cy="13" r="7.5" />
      <path d="M9.5 4.8c.7-1 1.55-1.55 2.5-1.8.1 1.2-.15 2.15-.75 2.85" />
      <path d="M12.2 5.3c1.15-.7 2.25-.8 3.3-.35" />
    </svg>
  </div>

  <div class="pomodoro-copy">
    <p class="eyebrow">{$t('ui.pomodoroLauncher.pomodoro')}</p>
    {#if activeSession?.state === 'running'}
      <p>{$t('ui.pomodoroLauncher.remainingSyncedAcrossDevices', { value1: activePhaseLabel(), value2: formatTime(activeRemainingSeconds) })}</p>
    {:else if activeSession?.state === 'ringing'}
      <p>{$t('ui.pomodoroLauncher.alarmRingingContinueToDismissIt')}</p>
    {:else if activeSession}
      <p>{$t('ui.pomodoroLauncher.readySyncedAcrossDevices', { value1: activePhaseLabel() })}</p>
    {:else if settings}
      <p>{$t('ui.pomodoroLauncher.minFocusMinBreakMinLongBreak', { value1: settings.focus_minutes, value2: settings.short_break_minutes, value3: settings.long_break_minutes })}</p>
    {:else if error}
      <p class="error">{$text(error)}</p>
    {:else}
      <p>{$t('ui.pomodoroLauncher.loadingFocusSettings')}</p>
    {/if}
  </div>

  <AppButton
    variant="primary"
    className="start-button"
    disabled={!settings || (!activeSession && !recommendedTaskTitle)}
    aria-label={activeSession ? $t('ui.pomodoroLauncher.continueActivePomodoro') : recommendedTaskTitle ? $t('ui.pomodoroLauncher.startPomodoroWith', { value1: recommendedTaskTitle }) : $t('ui.pomodoroLauncher.startPomodoro')}
    title={activeSession ? $t('ui.pomodoroLauncher.continueThePomodoroActiveOnYourAccount') : recommendedTaskTitle ? $t('ui.pomodoroLauncher.startWith', { value1: recommendedTaskTitle }) : $t('ui.pomodoroLauncher.noRecommendedTaskInThisScope')}
    on:click={startSession}
  >
    <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 7 8 5-8 5Z" /></svg>
    {activeSession ? $t('ui.pomodoroLauncher.continuePomodoro') : $t('ui.pomodoroLauncher.startPomodoro')}
  </AppButton>
</section>

<style>
  .pomodoro-launcher {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto;
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
  :global(.start-button svg) {
    width: 1.2rem;
    height: 1.2rem;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
  }

  :global(.start-button svg) {
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

  :global(.start-button) {
    display: inline-flex;
    align-items: center;
    gap: .4rem;
    white-space: nowrap;
  }

  @media (max-width: 840px) {
    .pomodoro-launcher {
      grid-template-columns: auto 1fr;
    }

    :global(.start-button) {
      grid-column: 1 / -1;
      justify-content: center;
    }
  }
</style>
