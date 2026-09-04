<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { PomodoroSettings, Status, Task, Workspace } from '../lib/api/types';
  import TaskCard from '../lib/components/TaskCard.svelte';

  type Phase = 'focus' | 'short-break' | 'long-break';

  export let workspace: Workspace;
  export let taskVersion = 0;

  const dispatch = createEventDispatcher<{ openTask: number; end: void }>();

  let settings: PomodoroSettings | null = null;
  let statuses: Status[] = [];
  let currentTask: Task | null = null;
  let phase: Phase = 'focus';
  let remainingSeconds = 0;
  let deadline = 0;
  let focusStartedAt = 0;
  let shortBreaksTaken = 0;
  let breakComplete = false;
  let loading = true;
  let selecting = false;
  let error = '';
  let timer: number;
  let seenTaskVersion = taskVersion;

  function durationSeconds(): number {
    if (!settings) return 0;
    if (phase === 'focus') return settings.focus_minutes * 60;
    if (phase === 'short-break') return settings.short_break_minutes * 60;
    return settings.long_break_minutes * 60;
  }

  function startTimer(minutes: number) {
    deadline = Date.now() + minutes * 60_000;
    remainingSeconds = minutes * 60;
  }

  function formatTime(total: number): string {
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }

  function phaseLabel(): string {
    if (phase === 'focus') return 'FOCUS';
    if (phase === 'long-break') return 'LONG BREAK';
    return 'SHORT BREAK';
  }

  async function selectNextTask() {
    selecting = true;
    error = '';
    try {
      const ranked = await api.tasks(workspace.id, { finished: false, blocked: false });
      currentTask = ranked[0] ?? null;
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not select the next task';
    } finally {
      selecting = false;
    }
  }

  async function startFocusInterval() {
    if (!settings) return;
    breakComplete = false;
    phase = 'focus';
    currentTask = null;
    await selectNextTask();
    focusStartedAt = Date.now();
    startTimer(settings.focus_minutes);
  }

  function startBreak() {
    if (!settings || phase !== 'focus') return;
    currentTask = null;
    breakComplete = false;

    if (shortBreaksTaken >= settings.short_breaks_before_long) {
      phase = 'long-break';
      shortBreaksTaken = 0;
      startTimer(settings.long_break_minutes);
    } else {
      phase = 'short-break';
      shortBreaksTaken += 1;
      startTimer(settings.short_break_minutes);
    }
  }

  function tick() {
    if (!deadline || breakComplete) return;
    remainingSeconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    if (remainingSeconds > 0) return;

    if (phase === 'focus') {
      startBreak();
    } else {
      breakComplete = true;
    }
  }

  async function handleTaskChanged(updated: Task) {
    if (!currentTask || updated.id !== currentTask.id || !settings) return;

    if (updated.finished_at) {
      const elapsed = Date.now() - focusStartedAt;
      if (elapsed > settings.focus_minutes * 60_000 / 2) {
        startBreak();
      } else {
        await selectNextTask();
      }
      return;
    }

    if (updated.current_block) {
      await selectNextTask();
      return;
    }

    // Keep the same selected task even if its score-affecting fields changed.
    currentTask = updated;
  }

  async function reconcileExternalTaskChange() {
    if (phase !== 'focus') return;
    if (!currentTask) {
      await selectNextTask();
      return;
    }

    try {
      const refreshed = await api.task(currentTask.id);
      if (refreshed.finished_at || refreshed.current_block) {
        await selectNextTask();
      } else {
        currentTask = refreshed;
      }
    } catch {
      await selectNextTask();
    }
  }

  $: if (taskVersion !== seenTaskVersion) {
    seenTaskVersion = taskVersion;
    void reconcileExternalTaskChange();
  }

  onMount(() => {
    timer = window.setInterval(tick, 250);
    void (async () => {
      try {
        [settings, statuses] = await Promise.all([
          api.pomodoroSettings(),
          api.statuses(workspace.id)
        ]);
        await startFocusInterval();
      } catch (reason) {
        error = reason instanceof Error ? reason.message : 'Could not start focus mode';
      } finally {
        loading = false;
      }
    })();

    return () => window.clearInterval(timer);
  });
</script>

<div class:break-mode={phase !== 'focus'} class="focus-screen">
  <header class="focus-header">
    <div class="focus-brand"><span class="focus-dot"></span><strong>Next Task</strong></div>
    <div class="focus-header-actions">
      {#if workspace.role !== 'viewer' && phase === 'focus'}
        <button class="quiet-button" on:click={() => dispatch('openTask', 0)}>+ New task</button>
      {/if}
      <button class="quiet-button" on:click={() => dispatch('end')}>End session</button>
    </div>
  </header>

  <main class="focus-content">
    <div class="phase-chip">{phaseLabel()}</div>
    <div class="timer" aria-live="polite">{formatTime(remainingSeconds)}</div>

    {#if settings}
      <div class="cycle-dots" aria-label={`${shortBreaksTaken} short breaks before the next long break`}>
        {#each Array(settings.short_breaks_before_long) as _, index}
          <span class:done={index < shortBreaksTaken}></span>
        {/each}
        <span class="long-dot" title="Long break"></span>
      </div>
    {/if}

    {#if error}<p class="error" role="alert">{error}</p>{/if}

    {#if loading}
      <section class="focus-placeholder">Preparing your focus session…</section>
    {:else if phase === 'focus'}
      <section class="focus-task-area">
        <div class="focus-task-heading">
          <div>
            <p class="eyebrow">Your task for this interval</p>
            <h1>{currentTask ? 'Focus on this' : 'Nothing actionable right now'}</h1>
          </div>
          {#if currentTask}<span class="locked-task">Pinned for this interval</span>{/if}
        </div>

        {#if selecting}
          <div class="focus-placeholder">Ranking your tasks…</div>
        {:else if currentTask}
          <TaskCard
            task={currentTask}
            {statuses}
            readOnly={workspace.role === 'viewer'}
            on:changed={(event) => handleTaskChanged(event.detail)}
            on:open={(event) => dispatch('openTask', event.detail)}
            on:error={(event) => (error = event.detail)}
          />
          <p class="session-rule">
            Finishing this task after halfway moves you to break. Before halfway—or when you block it—Focus picks the next highest-scoring task without resetting the timer.
          </p>
        {:else}
          <div class="empty-focus">
            <p>No unfinished, unblocked tasks are available.</p>
            {#if workspace.role !== 'viewer'}
              <button class="primary" on:click={() => dispatch('openTask', 0)}>Create a task</button>
            {/if}
          </div>
        {/if}
      </section>
    {:else}
      <section class="break-card">
        <div class="break-icon" aria-hidden="true">☕</div>
        <h1>{breakComplete ? 'Break complete' : phase === 'long-break' ? 'Take a proper break' : 'Take a short break'}</h1>
        <p>{breakComplete ? 'Start the next focus interval when you are ready.' : 'Step away from the task. Your next focus interval will re-rank the queue.'}</p>
        <button class="primary" on:click={startFocusInterval}>
          {breakComplete ? 'Start next focus' : 'Skip break and focus'}
        </button>
      </section>
    {/if}
  </main>
</div>

<style>
  .focus-screen {
    min-height: 100vh;
    background: radial-gradient(circle at top, #f5efe1 0, #f7f5ee 38%, #efede6 100%);
    color: var(--ink);
  }

  .focus-screen.break-mode {
    background: radial-gradient(circle at top, #e8f0ec 0, #f4f6f2 42%, #ecefe9 100%);
  }

  .focus-header {
    display: flex;
    max-width: 980px;
    margin: 0 auto;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    padding: 1rem 1.25rem;
  }

  .focus-brand,
  .focus-header-actions {
    display: flex;
    align-items: center;
    gap: .65rem;
  }

  .focus-dot {
    width: .72rem;
    height: .72rem;
    border-radius: 50%;
    background: #a65038;
    box-shadow: 0 0 0 .3rem rgba(166, 80, 56, .12);
  }

  .quiet-button {
    border: 1px solid rgba(80, 75, 65, .18);
    border-radius: .55rem;
    background: rgba(255, 255, 255, .45);
    color: var(--muted);
    padding: .48rem .7rem;
    font-size: .8rem;
    font-weight: 700;
  }

  .quiet-button:hover {
    background: rgba(255, 255, 255, .8);
    color: var(--ink);
  }

  .focus-content {
    width: min(900px, calc(100% - 2rem));
    margin: 0 auto;
    padding: 2rem 0 4rem;
    text-align: center;
  }

  .phase-chip {
    display: inline-flex;
    border: 1px solid rgba(120, 80, 60, .18);
    border-radius: 999px;
    background: rgba(255, 255, 255, .62);
    color: #8e4b37;
    padding: .35rem .7rem;
    font-size: .72rem;
    font-weight: 900;
    letter-spacing: .12em;
  }

  .break-mode .phase-chip {
    color: var(--forest-2);
  }

  .timer {
    margin-top: .5rem;
    font-size: clamp(4.5rem, 13vw, 8.5rem);
    font-weight: 800;
    letter-spacing: -.06em;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }

  .cycle-dots {
    display: flex;
    justify-content: center;
    gap: .4rem;
    margin: .85rem 0 2.2rem;
  }

  .cycle-dots span {
    width: .48rem;
    height: .48rem;
    border-radius: 50%;
    background: #d4d0c5;
  }

  .cycle-dots span.done {
    background: #a65038;
  }

  .cycle-dots .long-dot {
    width: .7rem;
    border-radius: .2rem;
    background: #9daf9f;
  }

  .focus-task-area {
    text-align: left;
  }

  .focus-task-heading {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: .8rem;
  }

  .focus-task-heading .eyebrow,
  .focus-task-heading h1 {
    margin: 0;
  }

  .focus-task-heading h1 {
    margin-top: .15rem;
    font-size: 1.45rem;
  }

  .locked-task {
    border-radius: 999px;
    background: #e9e5da;
    color: var(--muted);
    padding: .3rem .55rem;
    font-size: .72rem;
    font-weight: 700;
    white-space: nowrap;
  }

  .focus-placeholder,
  .empty-focus,
  .break-card {
    border: 1px solid rgba(100, 95, 80, .14);
    border-radius: .9rem;
    background: rgba(255, 255, 255, .7);
    padding: 2rem;
    box-shadow: 0 14px 40px rgba(65, 60, 50, .06);
  }

  .session-rule {
    margin: .65rem .2rem 0;
    color: var(--muted);
    font-size: .78rem;
    line-height: 1.45;
  }

  .empty-focus {
    text-align: center;
  }

  .break-card {
    max-width: 540px;
    margin: 2rem auto 0;
  }

  .break-icon {
    font-size: 2.4rem;
  }

  .break-card h1 {
    margin: .5rem 0 .35rem;
  }

  .break-card p {
    margin: 0 auto 1rem;
    color: var(--muted);
    line-height: 1.5;
  }

  @media (max-width: 640px) {
    .focus-header {
      align-items: flex-start;
    }

    .focus-header-actions {
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    .focus-content {
      padding-top: 1rem;
    }

    .focus-task-heading {
      align-items: flex-start;
      flex-direction: column;
    }
  }
</style>
