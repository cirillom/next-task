<script lang="ts">
  import { createEventDispatcher, onDestroy, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { PomodoroSettings, Status, Tag, Task, Workspace } from '../lib/api/types';
  import MarkdownEditor from '../lib/components/MarkdownEditor.svelte';
  import TaskCard from '../lib/components/TaskCard.svelte';
  import TaskQueue from '../lib/components/TaskQueue.svelte';

  type Phase = 'focus' | 'short-break' | 'long-break';
  type BlockedFilter = '' | 'false' | 'true';
  type TaskResolution = 'finished' | 'blocked';
  type DescriptionSaveState = 'idle' | 'saving' | 'saved' | 'error';

  export let workspace: Workspace;
  export let taskVersion = 0;
  export let sessionTagId: number | null = null;

  const dispatch = createEventDispatcher<{ openTask: number; end: void }>();
  const baseDocumentTitle = typeof document === 'undefined' ? 'Next Task' : document.title;

  let settings: PomodoroSettings | null = null;
  let statuses: Status[] = [];
  let tags: Tag[] = [];
  let sessionTag: Tag | null = null;
  let currentTask: Task | null = null;
  let sessionTasks: Task[] = [];
  let taskListBlocked: BlockedFilter = '';
  let queueOpen = false;
  let phase: Phase = 'focus';
  let running = false;
  let remainingSeconds = 0;
  let deadline = 0;
  let shortBreaksTaken = 0;
  let loading = true;
  let selecting = false;
  let listLoading = false;
  let unblockingTaskId: number | null = null;
  let breakPrompt: TaskResolution | null = null;
  let audioContext: AudioContext | null = null;
  let error = '';
  let timer: number;
  let seenTaskVersion = taskVersion;

  let descriptionEditing = false;
  let descriptionDraft = '';
  let descriptionSaveState: DescriptionSaveState = 'idle';
  let descriptionSaveTimer: number;
  let descriptionSaveInFlight = false;
  let pendingDescriptionSave: { taskId: number; value: string } | null = null;

  function durationSeconds(targetPhase: Phase = phase): number {
    if (!settings) return 0;
    if (targetPhase === 'focus') return settings.focus_minutes * 60;
    if (targetPhase === 'short-break') return settings.short_break_minutes * 60;
    return settings.long_break_minutes * 60;
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

  function startLabel(): string {
    if (phase === 'focus') return 'Start focus';
    if (phase === 'long-break') return 'Start long break';
    return 'Start short break';
  }

  function tabStateLabel(): string {
    if (phase === 'focus') return running ? 'Focus' : 'Focus ready';
    if (phase === 'long-break') return running ? 'Long break' : 'Long break ready';
    return running ? 'Break' : 'Break ready';
  }

  function nextBreakLabel(): string {
    if (!settings) return 'Start break';
    return shortBreaksTaken >= settings.short_breaks_before_long ? 'Start long break' : 'Start short break';
  }

  function ensureAudioContext(): AudioContext | null {
    if (typeof AudioContext === 'undefined') return null;
    if (!audioContext) audioContext = new AudioContext();
    if (audioContext.state === 'suspended') void audioContext.resume();
    return audioContext;
  }

  function playNotificationSound(completedPhase: Phase) {
    const context = ensureAudioContext();
    if (!context) return;

    const frequencies = completedPhase === 'focus' ? [660, 880] : [880, 660];
    const now = context.currentTime;
    frequencies.forEach((frequency, index) => {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      const start = now + index * .17;
      oscillator.type = 'sine';
      oscillator.frequency.setValueAtTime(frequency, start);
      gain.gain.setValueAtTime(.0001, start);
      gain.gain.exponentialRampToValueAtTime(.16, start + .015);
      gain.gain.exponentialRampToValueAtTime(.0001, start + .15);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.start(start);
      oscillator.stop(start + .16);
    });
  }

  function resetDescriptionEditor(task: Task | null) {
    descriptionEditing = false;
    descriptionDraft = task?.description || '';
    descriptionSaveState = 'idle';
  }

  async function selectNextTask() {
    selecting = true;
    error = '';
    try {
      const ranked = await api.tasks(workspace.id, {
        finished: false,
        blocked: false,
        actionable: true,
        tag_id: sessionTagId
      });
      currentTask = ranked[0] ?? null;
      resetDescriptionEditor(currentTask);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not select the next task';
    } finally {
      selecting = false;
    }
  }

  function focusTask(task: Task) {
    if (task.finished_at || task.current_block) return;
    currentTask = task;
    resetDescriptionEditor(task);
    error = '';
  }

  async function loadSessionTasks() {
    listLoading = true;
    try {
      sessionTasks = await api.tasks(workspace.id, {
        finished: false,
        blocked: taskListBlocked,
        actionable: true,
        tag_id: sessionTagId
      });
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load session tasks';
    } finally {
      listLoading = false;
    }
  }

  async function unblockListedTask(task: Task) {
    if (!task.current_block || unblockingTaskId !== null) return;
    unblockingTaskId = task.id;
    error = '';
    try {
      await api.unblockTask(task.id);
      await loadSessionTasks();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not unblock task';
    } finally {
      unblockingTaskId = null;
    }
  }

  function toggleDescriptionEditor() {
    if (!currentTask) return;
    descriptionEditing = !descriptionEditing;
    descriptionDraft = currentTask.description || '';
    descriptionSaveState = 'idle';
  }

  function scheduleDescriptionSave(value: string) {
    if (!currentTask || workspace.role === 'viewer') return;
    descriptionDraft = value;
    descriptionSaveState = 'saving';
    window.clearTimeout(descriptionSaveTimer);
    const taskId = currentTask.id;
    descriptionSaveTimer = window.setTimeout(() => {
      pendingDescriptionSave = { taskId, value };
      void drainDescriptionSave();
    }, 650);
  }

  async function drainDescriptionSave() {
    if (descriptionSaveInFlight || !pendingDescriptionSave) return;
    const request = pendingDescriptionSave;
    pendingDescriptionSave = null;
    descriptionSaveInFlight = true;
    descriptionSaveState = 'saving';
    try {
      const updated = await api.updateTask(request.taskId, { description: request.value || null });
      if (currentTask?.id === request.taskId) currentTask = updated;
      sessionTasks = sessionTasks.map((task) => task.id === request.taskId ? updated : task);
      descriptionSaveState = 'saved';
    } catch (reason) {
      descriptionSaveState = 'error';
      error = reason instanceof Error ? reason.message : 'Could not save description';
    } finally {
      descriptionSaveInFlight = false;
      if (pendingDescriptionSave) void drainDescriptionSave();
    }
  }

  async function prepareFocus() {
    if (!settings) return;
    const completedLongBreak = phase === 'long-break';
    phase = 'focus';
    running = false;
    deadline = 0;
    remainingSeconds = durationSeconds('focus');
    if (completedLongBreak) shortBreaksTaken = 0;
    if (!currentTask) await selectNextTask();
  }

  function prepareBreak() {
    if (!settings || phase !== 'focus') return;
    breakPrompt = null;
    running = false;
    deadline = 0;

    if (shortBreaksTaken >= settings.short_breaks_before_long) {
      phase = 'long-break';
    } else {
      phase = 'short-break';
      shortBreaksTaken += 1;
    }
    remainingSeconds = durationSeconds();
  }

  async function startCurrentPeriod() {
    if (!settings || running) return;
    ensureAudioContext();
    if (phase === 'focus' && !currentTask) await selectNextTask();

    if (phase === 'focus' && currentTask && workspace.role !== 'viewer') {
      try {
        const updated = await api.updateTask(currentTask.id, { last_worked_at: new Date().toISOString() });
        currentTask = updated;
        sessionTasks = sessionTasks.map((task) => task.id === updated.id ? updated : task);
        void loadSessionTasks();
      } catch (reason) {
        error = reason instanceof Error ? reason.message : 'Could not record task work';
        return;
      }
    }

    running = true;
    deadline = Date.now() + durationSeconds() * 1000;
    remainingSeconds = durationSeconds();
  }

  async function advancePeriod() {
    if (phase === 'focus') prepareBreak();
    else await prepareFocus();
  }

  function cutPeriodShort() {
    if (!running) return;
    running = false;
    deadline = 0;
    void advancePeriod();
  }

  function tick() {
    if (!running || !deadline) return;
    remainingSeconds = Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
    if (remainingSeconds > 0) return;

    const completedPhase = phase;
    running = false;
    deadline = 0;
    breakPrompt = null;
    playNotificationSound(completedPhase);
    void advancePeriod();
  }

  async function startBreakAfterTask() {
    breakPrompt = null;
    prepareBreak();
    await startCurrentPeriod();
  }

  function keepFocusingAfterTask() {
    breakPrompt = null;
  }

  async function handleTaskChanged(updated: Task) {
    if (!currentTask || updated.id !== currentTask.id || !settings) return;

    if (updated.current_block || updated.finished_at) {
      const shouldAskForBreak = running && phase === 'focus';
      const resolution: TaskResolution = updated.current_block ? 'blocked' : 'finished';
      currentTask = null;
      resetDescriptionEditor(null);
      await selectNextTask();
      if (shouldAskForBreak) breakPrompt = resolution;
      return;
    }

    currentTask = updated;
    if (!descriptionEditing) descriptionDraft = updated.description || '';
  }

  async function handlePinnedTaskChanged(updated: Task) {
    await handleTaskChanged(updated);
    await loadSessionTasks();
  }

  async function reconcileExternalTaskChange() {
    if (!currentTask) {
      await selectNextTask();
      await loadSessionTasks();
      return;
    }

    try {
      const refreshed = await api.task(currentTask.id);
      if (refreshed.finished_at || refreshed.current_block) {
        await handleTaskChanged(refreshed);
      } else {
        currentTask = refreshed;
        if (!descriptionEditing) descriptionDraft = refreshed.description || '';
      }
    } catch {
      currentTask = null;
      resetDescriptionEditor(null);
      await selectNextTask();
    }
    await loadSessionTasks();
  }

  $: if (taskVersion !== seenTaskVersion) {
    seenTaskVersion = taskVersion;
    void reconcileExternalTaskChange();
  }

  $: if (typeof document !== 'undefined') {
    document.title = `${formatTime(remainingSeconds)} · ${tabStateLabel()} — Next Task`;
  }

  onMount(() => {
    timer = window.setInterval(tick, 250);
    void (async () => {
      try {
        [settings, statuses, tags] = await Promise.all([
          api.pomodoroSettings(),
          api.statuses(workspace.id),
          api.tags(workspace.id)
        ]);
        sessionTag = sessionTagId === null ? null : tags.find((tag) => tag.id === sessionTagId) ?? null;
        await Promise.all([prepareFocus(), loadSessionTasks()]);
      } catch (reason) {
        error = reason instanceof Error ? reason.message : 'Could not start focus mode';
      } finally {
        loading = false;
      }
    })();

    return () => {
      window.clearInterval(timer);
      document.title = baseDocumentTitle;
      if (audioContext) void audioContext.close();
    };
  });

  onDestroy(() => {
    window.clearTimeout(descriptionSaveTimer);
    if (descriptionEditing && currentTask && workspace.role !== 'viewer') {
      pendingDescriptionSave = { taskId: currentTask.id, value: descriptionDraft };
      void drainDescriptionSave();
    }
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

    <div class="period-controls">
      {#if running}
        <span class="running-label">Running</span>
        <button class="quiet-button period-button" on:click={cutPeriodShort}>
          {phase === 'focus' ? 'End focus early' : 'End break early'}
        </button>
      {:else}
        <button class="primary period-button" disabled={loading || selecting} on:click={startCurrentPeriod}>
          {startLabel()}
        </button>
      {/if}
    </div>

    {#if settings}
      <div class="cycle-dots" aria-label={`${shortBreaksTaken} short breaks before the next long break`}>
        {#each Array(settings.short_breaks_before_long) as _, index}
          <span class:done={index < shortBreaksTaken}></span>
        {/each}
        <span class="long-dot" title="Long break"></span>
      </div>
    {/if}

    <div class="session-scope">
      <span>Session scope</span>
      <strong>{sessionTag ? `#${sessionTag.name}` : 'All tags'}</strong>
      {#if sessionTag}<small>includes child tags</small>{/if}
    </div>

    {#if error}<p class="error" role="alert">{error}</p>{/if}

    {#if loading}
      <section class="focus-placeholder">Preparing your Pomodoro session…</section>
    {:else if phase === 'focus'}
      <section class="focus-task-area">
        <div class="focus-task-heading">
          <div>
            <p class="eyebrow">Your task for this session</p>
            <h1>{currentTask ? 'Focus on this' : 'Nothing actionable right now'}</h1>
          </div>
          {#if currentTask}<span class="locked-task">Current Pomodoro task</span>{/if}
        </div>

        {#if selecting}
          <div class="focus-placeholder">Ranking your tasks…</div>
        {:else if currentTask}
          <TaskCard
            task={currentTask}
            {statuses}
            readOnly={workspace.role === 'viewer'}
            on:changed={(event) => handlePinnedTaskChanged(event.detail)}
            on:open={(event) => dispatch('openTask', event.detail)}
            on:error={(event) => (error = event.detail)}
          />

          {#if workspace.role !== 'viewer'}
            <div class="description-tools">
              <button type="button" class="quiet-button" on:click={toggleDescriptionEditor}>
                {descriptionEditing ? 'Close description editor' : 'Edit description'}
              </button>
              {#if descriptionEditing && descriptionSaveState !== 'idle'}
                <span class:error-state={descriptionSaveState === 'error'} class="save-state" aria-live="polite">
                  {descriptionSaveState === 'saving' ? 'Saving…' : descriptionSaveState === 'saved' ? 'Saved' : 'Save failed'}
                </span>
              {/if}
            </div>

            {#if descriptionEditing}
              <section class="focus-description-editor" aria-label="Edit task description">
                <MarkdownEditor
                  bind:value={descriptionDraft}
                  label="Description"
                  on:input={(event) => scheduleDescriptionSave(event.detail)}
                />
              </section>
            {/if}
          {/if}

          <p class="session-rule">
            This task stays pinned across focus and break periods until you finish it, block it, or choose another task.
          </p>
        {:else}
          <div class="empty-focus">
            <p>No unfinished, unblocked tasks are available in this session scope.</p>
            {#if workspace.role !== 'viewer'}
              <button class="primary" on:click={() => dispatch('openTask', 0)}>Create a task</button>
            {/if}
          </div>
        {/if}

        <div class="choose-task-row">
          <button type="button" class="choose-task-toggle" aria-expanded={queueOpen} on:click={() => (queueOpen = !queueOpen)}>
            <span>{queueOpen ? 'Hide task queue' : 'Choose another task'}</span>
            <span class="queue-count">{sessionTasks.length}</span>
            <span aria-hidden="true">{queueOpen ? '▴' : '▾'}</span>
          </button>
        </div>

        {#if queueOpen}
          <section class="session-tasks" aria-label="Tasks in this Pomodoro session scope">
            <div class="session-tasks__heading">
              <h2>Queue</h2>
              <label class="blocked-filter">
                <span>Blocked</span>
                <select bind:value={taskListBlocked} on:change={loadSessionTasks}>
                  <option value="">Either</option>
                  <option value="false">Not blocked</option>
                  <option value="true">Blocked</option>
                </select>
              </label>
            </div>

            {#if listLoading}
              <p class="task-list-empty">Loading tasks…</p>
            {:else if sessionTasks.length === 0}
              <p class="task-list-empty">No matching unfinished tasks.</p>
            {:else}
              <TaskQueue
                tasks={sessionTasks}
                currentTaskId={currentTask?.id ?? null}
                allowFocus={true}
                allowUnblock={workspace.role !== 'viewer'}
                busyTaskId={unblockingTaskId}
                on:open={(event) => dispatch('openTask', event.detail)}
                on:focus={(event) => focusTask(event.detail)}
                on:unblock={(event) => unblockListedTask(event.detail)}
              />
            {/if}
          </section>
        {/if}
      </section>
    {:else}
      <section class="break-card">
        <div class="break-icon" aria-hidden="true">☕</div>
        <h1>{running ? 'Take your break' : 'Break ready when you are'}</h1>
        <p>
          {#if running}
            Step away until the timer ends, or end the break early when you are ready to move on.
          {:else}
            The break timer will not start until you start it explicitly.
          {/if}
        </p>
        {#if currentTask}
          <p class="pinned-note"><strong>{currentTask.title}</strong> remains pinned for the next focus period.</p>
        {:else}
          <p class="pinned-note">Your next task will be ranked within this session scope.</p>
        {/if}
      </section>
    {/if}
  </main>

  {#if breakPrompt}
    <div class="break-prompt-backdrop" role="presentation">
      <section class="break-prompt" role="dialog" aria-modal="true" aria-labelledby="break-prompt-title" aria-describedby="break-prompt-description">
        <p class="eyebrow">{breakPrompt === 'finished' ? 'Task completed' : 'Task blocked'}</p>
        <h2 id="break-prompt-title">Start a break?</h2>
        <p id="break-prompt-description">Take a break now, or keep the current focus timer running with the next task.</p>
        <div class="break-prompt-actions">
          <button type="button" class="quiet-button" on:click={keepFocusingAfterTask}>Keep focusing</button>
          <button type="button" class="primary" on:click={startBreakAfterTask}>{nextBreakLabel()}</button>
        </div>
      </section>
    </div>
  {/if}
</div>

<style>
  .focus-screen {
    min-height: 100vh;
    background: radial-gradient(circle at top, #f5efe1 0, #f7f5ee 38%, #efede6 100%);
    color: var(--ink);
  }

  .focus-screen.break-mode { background: radial-gradient(circle at top, #e8f0ec 0, #f4f6f2 42%, #ecefe9 100%); }

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
  .focus-header-actions,
  .period-controls { display: flex; align-items: center; gap: .65rem; }

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

  .quiet-button:hover { background: rgba(255, 255, 255, .8); color: var(--ink); }

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

  .break-mode .phase-chip { color: var(--forest-2); }

  .timer {
    margin-top: .5rem;
    font-size: clamp(4.5rem, 13vw, 8.5rem);
    font-weight: 800;
    letter-spacing: -.06em;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }

  .period-controls { justify-content: center; margin-top: 1rem; }
  .period-button { min-width: 9rem; }

  .running-label {
    border-radius: 999px;
    background: rgba(166, 80, 56, .1);
    color: #8e4b37;
    padding: .34rem .58rem;
    font-size: .72rem;
    font-weight: 800;
  }

  .break-mode .running-label { background: rgba(55, 95, 75, .1); color: var(--forest-2); }

  .cycle-dots { display: flex; justify-content: center; gap: .4rem; margin: .85rem 0 .8rem; }
  .cycle-dots span { width: .48rem; height: .48rem; border-radius: 50%; background: #d4d0c5; }
  .cycle-dots span.done { background: #a65038; }
  .cycle-dots .long-dot { width: .7rem; border-radius: .2rem; background: #9daf9f; }

  .session-scope {
    display: inline-flex;
    align-items: center;
    gap: .35rem;
    margin-bottom: 2rem;
    border-radius: 999px;
    background: rgba(255, 255, 255, .55);
    color: var(--muted);
    padding: .35rem .65rem;
    font-size: .72rem;
  }

  .session-scope strong { color: var(--forest-2); }
  .session-scope small { opacity: .8; }
  .focus-task-area { text-align: left; }

  .focus-task-heading {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: .8rem;
  }

  .focus-task-heading .eyebrow,
  .focus-task-heading h1,
  .session-tasks__heading h2 { margin: 0; }
  .focus-task-heading h1 { margin-top: .15rem; font-size: 1.45rem; }

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

  .description-tools {
    display: flex;
    min-height: 2rem;
    align-items: center;
    gap: .65rem;
    margin: .7rem .2rem 0;
  }

  .save-state { color: var(--forest-2); font-size: .75rem; font-weight: 750; }
  .save-state.error-state { color: var(--danger); }

  .focus-description-editor {
    margin-top: .6rem;
    border: 1px solid rgba(100, 95, 80, .15);
    border-radius: .8rem;
    background: rgba(255, 255, 255, .68);
    padding: .8rem;
  }

  .session-rule { margin: .65rem .2rem 0; color: var(--muted); font-size: .78rem; line-height: 1.45; }
  .empty-focus { text-align: center; }

  .choose-task-row { display: flex; justify-content: center; margin-top: 1.5rem; }

  .choose-task-toggle {
    display: inline-flex;
    align-items: center;
    gap: .5rem;
    border: 1px solid rgba(80, 75, 65, .18);
    border-radius: 999px;
    background: rgba(255, 255, 255, .55);
    color: var(--forest-2);
    padding: .48rem .75rem;
    font-size: .8rem;
    font-weight: 750;
  }

  .choose-task-toggle:hover { background: #fff; }
  .queue-count { min-width: 1.35rem; border-radius: 999px; background: #e8ede9; padding: .08rem .35rem; text-align: center; font-size: .7rem; }

  .session-tasks { margin-top: .85rem; padding-top: 1rem; border-top: 1px solid rgba(100, 95, 80, .16); }

  .session-tasks__heading {
    display: flex;
    align-items: end;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: .75rem;
  }

  .session-tasks__heading h2 { font-size: 1.15rem; }

  .blocked-filter {
    display: grid;
    min-width: 9.5rem;
    gap: .2rem;
    margin: 0;
    color: var(--muted);
    font-size: .7rem;
    font-weight: 800;
  }

  .blocked-filter select { min-width: 0; }
  .task-list-empty { margin: .6rem 0 0; color: var(--muted); font-size: .82rem; }

  .break-card { max-width: 540px; margin: 2rem auto 0; }
  .break-icon { font-size: 2.4rem; }
  .break-card h1 { margin: .5rem 0 .35rem; }
  .break-card p { margin: 0 auto 1rem; color: var(--muted); line-height: 1.5; }
  .pinned-note { border-radius: .65rem; background: rgba(55, 95, 75, .07); padding: .7rem .8rem; }

  .break-prompt-backdrop {
    position: fixed;
    z-index: 50;
    inset: 0;
    display: grid;
    place-items: center;
    background: rgba(22, 28, 24, .28);
    padding: 1rem;
  }

  .break-prompt {
    width: min(100%, 28rem);
    border: 1px solid rgba(100, 95, 80, .16);
    border-radius: .9rem;
    background: var(--paper);
    box-shadow: 0 24px 70px rgba(30, 35, 31, .22);
    padding: 1.35rem;
    text-align: left;
  }

  .break-prompt .eyebrow,
  .break-prompt h2,
  .break-prompt p { margin: 0; }
  .break-prompt h2 { margin-top: .2rem; font-size: 1.45rem; }
  .break-prompt p:not(.eyebrow) { margin-top: .5rem; color: var(--muted); line-height: 1.45; }
  .break-prompt-actions { display: flex; justify-content: flex-end; gap: .65rem; margin-top: 1.15rem; }

  @media (max-width: 640px) {
    .focus-header { align-items: flex-start; }
    .focus-header-actions { flex-wrap: wrap; justify-content: flex-end; }
    .focus-content { padding-top: 1rem; }
    .focus-task-heading,
    .session-tasks__heading { align-items: flex-start; flex-direction: column; }
    .blocked-filter { width: 100%; }
    .break-prompt-actions { flex-wrap: wrap; }
  }
</style>
