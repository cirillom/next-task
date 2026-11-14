<script lang="ts">
  import { t, text, rich, localized, message, errorMessage, type Message } from '../lib/i18n';
  import { createEventDispatcher, onDestroy, onMount } from 'svelte';
  import { api, ApiError } from '../lib/api/client';
  import AppButton from '../lib/components/AppButton.svelte';
  import type {
    NextScope,
    PomodoroPhase,
    PomodoroSession,
    PomodoroSettings,
    Tag,
    Task
  } from '../lib/api/types';
  import MarkdownEditor from '../lib/components/MarkdownEditor.svelte';
  import TagBadge from '../lib/components/TagBadge.svelte';
  import TagScopeFilters from '../lib/components/TagScopeFilters.svelte';
  import TaskCard from '../lib/components/TaskCard.svelte';
  import TaskQueue from '../lib/components/TaskQueue.svelte';
  import ScoringWarning from '../lib/components/ScoringWarning.svelte';
  import { cleanTagScope, emptyTagScope, sameTagScope } from '../lib/tagScope';

  type BlockedFilter = '' | 'false' | 'true';
  type TaskResolution = 'finished' | 'blocked';
  type DescriptionSaveState = 'idle' | 'saving' | 'saved' | 'error';

  export let taskVersion = 0;
  export let sessionScope: NextScope = { include_tag_ids: [], exclude_tag_ids: [], tag_match: 'all' };

  const dispatch = createEventDispatcher<{ openTask: number; end: void; createBlocker: { taskId: number; title: string } }>();
  const baseDocumentTitle = typeof document === 'undefined' ? $t('ui.app.nextTask') : document.title;

  let settings: PomodoroSettings | null = null;
  let session: PomodoroSession | null = null;
  let tags: Tag[] = [];
  let currentTask: Task | null = null;
  let sessionTasks: Task[] = [];
  let taskListBlocked: BlockedFilter = '';
  let queueOpen = false;
  let phase: PomodoroPhase = 'focus';
  let running = false;
  let ringing = false;
  let remainingSeconds = 0;
  let deadline = 0;
  let serverClockOffset = 0;
  let shortBreaksTaken = 0;
  let loading = true;
  let selecting = false;
  let findingScopedTask = false;
  let listLoading = false;
  let unblockingTaskId: number | null = null;
  let breakPrompt: TaskResolution | null = null;
  let audioContext: AudioContext | null = null;
  let error: Message = '';
  let timer: number;
  let pollTimer: number;
  let syncInFlight = false;
  let initializedSession = false;
  let lastAlarmAt = 0;
  let seenTaskVersion = taskVersion;
  let editingScope = false;
  let scopeSaving = false;
  let scopeConflict = false;
  let scopeDraft: NextScope = emptyTagScope();
  let scopeBase: NextScope = emptyTagScope();
  let pinnedOutsideScope = false;
  let scopeCheckRequest = 0;
  let listRequest = 0;

  $: activeScope = session?.scope ?? sessionScope;
  $: tagById = new Map(tags.map((tag) => [tag.id, tag]));

  let descriptionDraft = '';
  let descriptionSaveState: DescriptionSaveState = 'idle';
  let descriptionSaveTimer: number;
  let descriptionSaveInFlight = false;
  let pendingDescriptionSave: { taskId: number; value: string } | null = null;

  function durationSeconds(targetPhase: PomodoroPhase = phase): number {
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
    if (phase === 'focus') return $t('ui.focus.focusPhase');
    if (phase === 'long-break') return $t('ui.focus.longBreak');
    return $t('ui.focus.shortBreak');
  }

  function startLabel(): string {
    if (phase === 'focus') return $t('ui.focus.startFocus');
    if (phase === 'long-break') return $t('ui.focus.startLongBreak');
    return $t('ui.focus.startShortBreak');
  }

  function tabStateLabel(): string {
    if (ringing) return $t('ui.pomodoroSettings.alarm');
    if (phase === 'focus') return running ? $t('ui.pomodoroLauncher.focus') : $t('ui.focus.focusReady');
    if (phase === 'long-break') return running ? $t('ui.pomodoroLauncher.longBreak') : $t('ui.focus.longBreakReady');
    return running ? $t('ui.focus.break') : $t('ui.focus.breakReady');
  }

  function nextBreakLabel(): string {
    if (!settings) return $t('ui.focus.startBreak');
    return shortBreaksTaken >= settings.short_breaks_before_long ? $t('ui.focus.startLongBreak') : $t('ui.focus.startShortBreak');
  }

  function ensureAudioContext(): AudioContext | null {
    if (typeof AudioContext === 'undefined') return null;
    if (!audioContext) audioContext = new AudioContext();
    if (audioContext.state === 'suspended') void audioContext.resume();
    return audioContext;
  }

  function playNotificationSound(completedPhase: PomodoroPhase) {
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

  function playAlarmSound(completedPhase: PomodoroPhase) {
    const context = ensureAudioContext();
    if (!context) return;

    const base = completedPhase === 'focus' ? 740 : 620;
    const now = context.currentTime;
    [0, .16, .32].forEach((offset, index) => {
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      const start = now + offset;
      oscillator.type = index % 2 === 0 ? 'square' : 'sine';
      oscillator.frequency.setValueAtTime(base + (index % 2) * 180, start);
      gain.gain.setValueAtTime(.0001, start);
      gain.gain.exponentialRampToValueAtTime(.2, start + .015);
      gain.gain.exponentialRampToValueAtTime(.0001, start + .13);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.start(start);
      oscillator.stop(start + .14);
    });
  }

  async function applySession(next: PomodoroSession, announceCompletion = true) {
    const previousSession = session;
    const scopeChanged = !!previousSession && !sameTagScope(previousSession.scope, next.scope);
    const taskChanged = next.task_id !== currentTask?.id;
    session = next;
    phase = next.phase;
    running = next.state === 'running';
    ringing = next.state === 'ringing';
    shortBreaksTaken = next.short_breaks_taken;
    serverClockOffset = Date.parse(next.server_now) - Date.now();
    deadline = next.ends_at ? Date.parse(next.ends_at) : 0;
    remainingSeconds = running && deadline
      ? Math.max(0, Math.ceil((deadline - (Date.now() + serverClockOffset)) / 1000))
      : ringing ? 0 : durationSeconds(next.phase);

    if (next.task_id !== currentTask?.id) {
      if (next.task_id === null) {
        currentTask = null;
        resetDescriptionEditor(null);
      } else {
        try {
          currentTask = await api.task(next.task_id);
          resetDescriptionEditor(currentTask);
        } catch {
          currentTask = null;
          resetDescriptionEditor(null);
        }
      }
    }

    if (scopeChanged) {
      if (editingScope && !sameTagScope(scopeBase, next.scope)) scopeConflict = true;
      await refreshScopeView();
    } else if (taskChanged) {
      await refreshPinnedScope();
    }

    if (
      announceCompletion &&
      initializedSession &&
      previousSession?.state === 'running' &&
      previousSession.ends_at !== null &&
      Date.parse(previousSession.ends_at) <= Date.parse(next.server_now) &&
      next.state === 'ready' &&
      previousSession.phase !== next.phase
    ) {
      playNotificationSound(previousSession.phase);
    }
    initializedSession = true;
  }

  async function syncSession() {
    if (syncInFlight) return;
    syncInFlight = true;
    try {
      const latest = await api.pomodoroSession();
      if (!latest) {
        dispatch('end');
        return;
      }
      const lostPinnedTask = !!currentTask && latest.task_id === null;
      await applySession(latest);
      if (lostPinnedTask && !selecting) {
        await selectNextTask();
        await loadSessionTasks();
      }
    } catch (reason) {
      error = errorMessage(reason, 'ui.focus.couldNotSynchronizeThePomodoroSession');
    } finally {
      syncInFlight = false;
    }
  }

  function scopeParams(scope: NextScope) {
    return {
      include_tag_id: scope.include_tag_ids,
      exclude_tag_id: scope.exclude_tag_ids,
      tag_match: scope.tag_match
    };
  }

  async function refreshPinnedScope() {
    const pinnedId = currentTask?.id;
    const request = ++scopeCheckRequest;
    if (!pinnedId) {
      pinnedOutsideScope = false;
      return;
    }
    try {
      const matching = await api.tasks({ finished: false, ...scopeParams(session?.scope ?? sessionScope) });
      if (request === scopeCheckRequest && currentTask?.id === pinnedId) {
        pinnedOutsideScope = !matching.some((task) => task.id === pinnedId);
      }
    } catch (reason) {
      if (request === scopeCheckRequest) error = errorMessage(reason, 'ui.focus.couldNotCheckThePinnedTaskScope');
    }
  }

  async function refreshScopeView() {
    try {
      tags = await api.tags();
    } catch (reason) {
      error = errorMessage(reason, 'ui.focus.couldNotLoadSessionTags');
    }
    await Promise.all([loadSessionTasks(), refreshPinnedScope()]);
  }

  function openScopeEditor() {
    if (!session) return;
    scopeBase = cleanTagScope(session.scope);
    scopeDraft = cleanTagScope(session.scope);
    scopeConflict = false;
    editingScope = true;
  }

  function closeScopeEditor() {
    editingScope = false;
    scopeConflict = false;
  }

  async function saveScope() {
    if (!session || scopeSaving || scopeConflict) return;
    if (sameTagScope(scopeDraft, scopeBase)) {
      closeScopeEditor();
      return;
    }
    scopeSaving = true;
    error = '';
    try {
      const updated = await api.updatePomodoroSessionScope(scopeDraft, scopeBase);
      editingScope = false;
      await applySession(updated, false);
    } catch (reason) {
      if (reason instanceof ApiError && reason.status === 409) {
        scopeConflict = true;
        try {
          const latest = await api.pomodoroSession();
          if (latest) await applySession(latest, false);
        } catch (syncReason) {
          error = errorMessage(syncReason, 'ui.focus.couldNotLoadTheLatestSessionScope');
        }
      } else {
        error = errorMessage(reason, 'ui.focus.couldNotSaveSessionScope');
      }
    } finally {
      scopeSaving = false;
    }
  }

  function resetDescriptionEditor(task: Task | null) {
    window.clearTimeout(descriptionSaveTimer);
    pendingDescriptionSave = null;
    descriptionDraft = task?.description || '';
    descriptionSaveState = 'idle';
  }

  function rankedTasksForScope(scope: NextScope) {
    return api.tasks({
      finished: false,
      blocked: false,
      actionable: true,
      ...scopeParams(scope)
    });
  }

  async function selectNextTask() {
    selecting = true;
    error = '';
    try {
      const ranked = await rankedTasksForScope(session?.scope ?? sessionScope);
      currentTask = ranked[0] ?? null;
      scopeCheckRequest++;
      pinnedOutsideScope = false;
      resetDescriptionEditor(currentTask);
      if (session) session = await api.updatePomodoroSessionTask(currentTask?.id ?? null);
    } catch (reason) {
      error = errorMessage(reason, 'ui.focus.couldNotSelectTheNextTask');
    } finally {
      selecting = false;
    }
  }

  async function findCorrectlyScopedTask() {
    if (!session || findingScopedTask) return;
    findingScopedTask = true;
    error = '';
    const scope = cleanTagScope(session.scope);
    try {
      const ranked = await rankedTasksForScope(scope);
      if (!sameTagScope(scope, session?.scope ?? sessionScope)) {
        error = message('ui.focus.theSessionScopeChangedFindACorrectlyScoped');
      } else if (!ranked.length) {
        error = message('ui.focus.noActionableTaskMatchesThisSessionScopeEdit');
      } else {
        if (await focusTask(ranked[0])) void loadSessionTasks();
      }
    } catch (reason) {
      error = errorMessage(reason, 'ui.focus.couldNotFindACorrectlyScopedTask');
    } finally {
      findingScopedTask = false;
    }
  }

  async function focusTask(task: Task): Promise<boolean> {
    if (task.finished_at || task.current_block || task.abandoned_by_task_id) return false;
    try {
      const updatedSession = await api.updatePomodoroSessionTask(task.id);
      session = updatedSession;
      currentTask = task;
      scopeCheckRequest++;
      pinnedOutsideScope = false;
      resetDescriptionEditor(task);
      error = '';
      return true;
    } catch (reason) {
      error = errorMessage(reason, 'ui.focus.couldNotChangeThePomodoroTask');
      return false;
    }
  }

  async function loadSessionTasks() {
    const request = ++listRequest;
    listLoading = true;
    try {
      const ranked = await api.tasks({
        finished: false,
        blocked: taskListBlocked,
        actionable: true,
        ...scopeParams(session?.scope ?? sessionScope)
      });
      if (request === listRequest) sessionTasks = ranked;
    } catch (reason) {
      if (request === listRequest) error = errorMessage(reason, 'ui.focus.couldNotLoadSessionTasks');
    } finally {
      if (request === listRequest) listLoading = false;
    }
  }

  async function unblockListedTask(task: Task) {
    if (!task.current_block || unblockingTaskId !== null) return;
    if (task.active_blocks.length > 1) {
      dispatch('openTask', task.id);
      return;
    }
    unblockingTaskId = task.id;
    error = '';
    try {
      await api.unblockOne(task.id, task.active_blocks[0].id);
      await loadSessionTasks();
    } catch (reason) {
      error = errorMessage(reason, 'ui.focus.couldNotUnblockTask');
    } finally {
      unblockingTaskId = null;
    }
  }

  function scheduleDescriptionSave(value: string) {
    if (!currentTask) return;
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
      error = errorMessage(reason, 'ui.focus.couldNotSaveDescription');
    } finally {
      descriptionSaveInFlight = false;
      if (pendingDescriptionSave) void drainDescriptionSave();
    }
  }

  async function startCurrentPeriod() {
    if (!settings || running || ringing) return;
    ensureAudioContext();
    if (phase === 'focus' && !currentTask) await selectNextTask();

    if (phase === 'focus' && currentTask) {
      try {
        const updated = await api.updateTask(currentTask.id, { last_worked_at: new Date().toISOString() });
        currentTask = updated;
        sessionTasks = sessionTasks.map((task) => task.id === updated.id ? updated : task);
        void loadSessionTasks();
      } catch (reason) {
        error = errorMessage(reason, 'ui.focus.couldNotRecordTaskWork');
        return;
      }
    }

    try {
      await applySession(await api.startPomodoroPeriod(), false);
    } catch (reason) {
      error = errorMessage(reason, 'ui.focus.couldNotStartThePomodoroPeriod');
    }
  }

  async function cutPeriodShort() {
    if (!running) return;
    try {
      await applySession(await api.skipPomodoroPeriod(), false);
      breakPrompt = null;
      if (phase === 'focus' && !currentTask) await selectNextTask();
    } catch (reason) {
      error = errorMessage(reason, 'ui.focus.couldNotEndThePomodoroPeriod');
    }
  }

  function tick() {
    if (ringing && session) {
      if (Date.now() - lastAlarmAt >= 1100) {
        lastAlarmAt = Date.now();
        playAlarmSound(session.phase);
      }
      return;
    }
    if (!running || !deadline) return;
    remainingSeconds = Math.max(
      0,
      Math.ceil((deadline - (Date.now() + serverClockOffset)) / 1000)
    );
    if (remainingSeconds === 0) void syncSession();
  }

  async function startBreakAfterTask() {
    breakPrompt = null;
    try {
      await applySession(await api.skipPomodoroPeriod(), false);
      await startCurrentPeriod();
    } catch (reason) {
      error = errorMessage(reason, 'ui.focus.couldNotStartTheBreak');
    }
  }

  async function dismissAlarm() {
    try {
      await applySession(await api.dismissPomodoroAlarm(), false);
      lastAlarmAt = 0;
      if (phase === 'focus' && !currentTask) await selectNextTask();
    } catch (reason) {
      error = errorMessage(reason, 'ui.focus.couldNotDismissTheAlarm');
    }
  }

  async function endSession() {
    try {
      await api.endPomodoroSession();
      dispatch('end');
    } catch (reason) {
      error = errorMessage(reason, 'ui.focus.couldNotEndThePomodoroSession');
    }
  }

  function keepFocusingAfterTask() {
    breakPrompt = null;
  }

  async function handleTaskChanged(updated: Task) {
    if (!currentTask || updated.id !== currentTask.id || !settings) return;

    if (updated.abandoned_by_task_id) {
      currentTask = null;
      resetDescriptionEditor(null);
      await selectNextTask();
      return;
    }

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
    if (descriptionSaveState === 'idle' || descriptionSaveState === 'saved') {
      descriptionDraft = updated.description || '';
    }
  }

  async function handlePinnedTaskChanged(updated: Task) {
    await handleTaskChanged(updated);
    await loadSessionTasks();
    await refreshPinnedScope();
  }

  async function reconcileExternalTaskChange() {
    if (!currentTask) {
      await selectNextTask();
      await loadSessionTasks();
      return;
    }

    try {
      const refreshed = await api.task(currentTask.id);
      if (refreshed.finished_at || refreshed.current_block || refreshed.abandoned_by_task_id) {
        await handleTaskChanged(refreshed);
      } else {
        currentTask = refreshed;
        if (descriptionSaveState === 'idle' || descriptionSaveState === 'saved') {
          descriptionDraft = refreshed.description || '';
        }
      }
    } catch {
      currentTask = null;
      resetDescriptionEditor(null);
      await selectNextTask();
    }
    await loadSessionTasks();
    await refreshPinnedScope();
  }

  $: if (taskVersion !== seenTaskVersion) {
    seenTaskVersion = taskVersion;
    void reconcileExternalTaskChange();
  }

  $: if (typeof document !== 'undefined') {
    document.title = $t('ui.focus.nextTask', { value1: formatTime(remainingSeconds), value2: tabStateLabel() });
  }

  onMount(() => {
    timer = window.setInterval(tick, 250);
    pollTimer = window.setInterval(() => void syncSession(), 1500);
    void (async () => {
      try {
        const [loadedSettings, existingSession, loadedTags] = await Promise.all([
          api.pomodoroSettings(),
          api.pomodoroSession(),
          api.tags()
        ]);
        settings = loadedSettings;
        tags = loadedTags;
        const activeSession = existingSession ?? await api.createPomodoroSession({
          tag_id: null,
          scope: sessionScope
        });
        await applySession(activeSession, false);
        if (phase === 'focus' && !currentTask) await selectNextTask();
        await loadSessionTasks();
        await refreshPinnedScope();
      } catch (reason) {
        error = errorMessage(reason, 'ui.focus.couldNotStartFocusMode');
      } finally {
        loading = false;
      }
    })();

    return () => {
      window.clearInterval(timer);
      window.clearInterval(pollTimer);
      document.title = baseDocumentTitle;
      if (audioContext) void audioContext.close();
    };
  });

  onDestroy(() => {
    window.clearTimeout(descriptionSaveTimer);
    if (currentTask) {
      pendingDescriptionSave = { taskId: currentTask.id, value: descriptionDraft };
      void drainDescriptionSave();
    }
  });
</script>

<div class:break-mode={phase !== 'focus'} class="focus-screen">
  <header class="focus-header">
    <div class="focus-brand"><span class="focus-dot"></span><strong>{$t('ui.app.nextTask')}</strong></div>
    <div class="focus-header-actions">
      {#if phase === 'focus'}
        <AppButton on:click={() => dispatch('openTask', 0)}>{$t('ui.focus.newTask')}</AppButton>
      {/if}
      <AppButton on:click={endSession}>{$t('ui.focus.endSession')}</AppButton>
    </div>
  </header>

  <main class="focus-content">
    <div class="phase-chip">{$localized(phaseLabel())}</div>
    <div class="timer" aria-live="polite">{$localized(formatTime(remainingSeconds))}</div>

    <div class="period-controls">
      {#if ringing}
        <span class="running-label alarm-label">{$t('ui.focus.alarmRinging')}</span>
        <AppButton variant="primary" className="period-button" on:click={dismissAlarm}>{$t('ui.focus.dismissAlarm')}</AppButton>
      {:else if running}
        <span class="running-label">{$t('ui.focus.running')}</span>
        <AppButton className="period-button" on:click={cutPeriodShort}>
          {phase === 'focus' ? $t('ui.focus.endFocusEarly') : $t('ui.focus.endBreakEarly')}
        </AppButton>
      {:else}
        <AppButton variant="primary" className="period-button" disabled={loading || selecting} on:click={startCurrentPeriod}>
          {$localized(startLabel())}
        </AppButton>
      {/if}
    </div>

    {#if settings}
      <div class="cycle-dots" aria-label={$t('ui.focus.shortBreaksBeforeTheNextLongBreak', { value1: shortBreaksTaken })}>
        {#each Array(settings.short_breaks_before_long) as _, index}
          <span class:done={index < shortBreaksTaken}></span>
        {/each}
        <span class="long-dot" title={$t('ui.pomodoroLauncher.longBreak')}></span>
      </div>
    {/if}

    <section class="session-scope" aria-label={$t('ui.focus.sessionScope')}>
      <div class="session-scope-heading">
        <strong>{$t('ui.focus.sessionScope')}</strong>
        <button type="button" disabled={!session || scopeSaving} on:click={openScopeEditor}>{$t('ui.focus.editScope')}</button>
      </div>
      <div class="scope-selection">
        <span>{$t('ui.focus.include')}</span>
        {#if activeScope.include_tag_ids.length}
          {#each activeScope.include_tag_ids as tagId (tagId)}
            {@const tag = tagById.get(tagId)}
            {#if tag}<TagBadge {tag}>{tag.display_name}</TagBadge>{:else}<small class="missing-tag">{$t('ui.focus.deletedTag', { value1: tagId })}</small>{/if}
          {/each}
        {:else}<span class="scope-empty">{$t('ui.focus.allTags')}</span>{/if}
      </div>
      <div class="scope-selection">
        <span>{$t('ui.focus.exclude')}</span>
        {#if activeScope.exclude_tag_ids.length}
          {#each activeScope.exclude_tag_ids as tagId (tagId)}
            {@const tag = tagById.get(tagId)}
            {#if tag}<TagBadge {tag}>{tag.display_name}</TagBadge>{:else}<small class="missing-tag">{$t('ui.focus.deletedTag', { value1: tagId })}</small>{/if}
          {/each}
        {:else}<span class="scope-empty">{$t('ui.focus.noneExcluded')}</span>{/if}
      </div>
      <p class="scope-match">{$t('ui.focus.matchIncludedTags')} <strong>{activeScope.tag_match === 'all' ? $t('ui.tagScopeFilters.all') : $t('ui.tagScopeFilters.any')}</strong></p>

      {#if editingScope}
        <div class="scope-editor">
          <TagScopeFilters {tags} scope={scopeDraft} matchName="session-tag-match" disabled={scopeSaving || scopeConflict} on:change={(event) => (scopeDraft = event.detail)} />
          {#if scopeConflict}<p class="error" role="alert">{$t('ui.focus.thisScopeChangedOnAnotherDeviceCloseAnd')}</p>{/if}
          <div class="scope-editor-actions">
            <AppButton disabled={scopeSaving} on:click={closeScopeEditor}>{$t('ui.blockTaskModal.cancel')}</AppButton>
            <AppButton variant="primary" disabled={scopeSaving || scopeConflict} on:click={saveScope}>{scopeSaving ? $t('ui.geminiSettings.saving') : $t('ui.focus.saveScope')}</AppButton>
          </div>
        </div>
      {/if}
    </section>

    {#if pinnedOutsideScope && currentTask}
      <p class="scope-warning" role="status">
        {@html $rich('ui.focus.outsideScope', {title: currentTask.title})}
        <button type="button" disabled={findingScopedTask} on:click={findCorrectlyScopedTask}>
          {findingScopedTask ? $t('ui.focus.findingCorrectlyScopedTask') : $t('ui.focus.findCorrectlyScopedTask')}
        </button>
      </p>
    {/if}

    {#if error}<p class="error" role="alert">{$text(error)}</p>{/if}
    <ScoringWarning message={sessionTasks[0]?.scoring_warning ?? currentTask?.scoring_warning ?? null} />

    {#if loading}
      <section class="focus-placeholder">{$t('ui.focus.preparingYourPomodoroSession')}</section>
    {:else if phase === 'focus'}
      <section class="focus-task-area">
        <div class="focus-task-heading">
          <div>
            <p class="eyebrow">{$t('ui.focus.yourTaskForThisSession')}</p>
            <h1>{currentTask ? $t('ui.focus.focusOnThis') : $t('ui.focus.nothingActionableRightNow')}</h1>
          </div>
          {#if currentTask}<span class="locked-task">{$t('ui.focus.currentPomodoroTask')}</span>{/if}
        </div>

        {#if selecting}
          <div class="focus-placeholder">{$t('ui.focus.rankingYourTasks')}</div>
        {:else if currentTask}
          <TaskCard
            task={currentTask}
            on:changed={(event) => handlePinnedTaskChanged(event.detail)}
            on:open={(event) => dispatch('openTask', event.detail)}
            on:createBlocker={(event) => dispatch('createBlocker', event.detail)}
            on:error={(event) => (error = event.detail)}
          />

          <section class="focus-description-editor" aria-label={$t('ui.focus.taskWorkingNotes')}>
            <div class="description-heading">
              <strong>{$t('ui.focus.workingNotes')}</strong>
              {#if descriptionSaveState !== 'idle'}
                <span class:error-state={descriptionSaveState === 'error'} class="save-state" aria-live="polite">
                  {descriptionSaveState === 'saving' ? $t('ui.geminiSettings.saving') : descriptionSaveState === 'saved' ? $t('ui.focus.saved') : $t('ui.focus.saveFailed')}
                </span>
              {/if}
            </div>
            <MarkdownEditor
              bind:value={descriptionDraft}

              label=""
              placeholder={$t('ui.focus.takeNotesUpdateChecklistsPasteLinksOrWrite')}
              on:input={(event) => scheduleDescriptionSave(event.detail)}
            />
          </section>

          <p class="session-rule">
            {$t('ui.focus.thisTaskStaysPinnedAcrossFocusAndBreak')}
          </p>
        {:else}
          <div class="empty-focus">
            <p>{$t('ui.focus.noUnfinishedUnblockedTasksAreAvailableInThis')}</p>
            <AppButton variant="primary" on:click={() => dispatch('openTask', 0)}>{$t('ui.focus.createATask')}</AppButton>
          </div>
        {/if}

      </section>
    {:else}
      <section class="break-card">
        <div class="break-icon" aria-hidden="true">☕</div>
        <h1>{running ? $t('ui.focus.takeYourBreak') : $t('ui.focus.breakReadyWhenYouAre')}</h1>
        <p>
          {#if running}
            {$t('ui.focus.stepAwayUntilTheTimerEndsOrEnd')}
          {:else}
            {$t('ui.focus.theBreakTimerWillNotStartUntilYou')}
          {/if}
        </p>
        {#if currentTask}
          <p class="pinned-note">{@html $rich('ui.focus.pinnedForNext', {title: currentTask.title})}</p>
        {:else}
          <p class="pinned-note">{$t('ui.focus.yourNextTaskWillBeRankedWithinThis')}</p>
        {/if}
      </section>
    {/if}

    {#if !loading}
      <div class="choose-task-row">
        <button type="button" class="choose-task-toggle" aria-expanded={queueOpen} on:click={() => (queueOpen = !queueOpen)}>
          <span>{queueOpen ? $t('ui.focus.hideTaskQueue') : $t('ui.focus.chooseAnotherTask')}</span>
          <span class="queue-count">{sessionTasks.length}</span>
          <span aria-hidden="true">{queueOpen ? '▴' : '▾'}</span>
        </button>
      </div>

      {#if queueOpen}
        <section class="session-tasks" aria-label={$t('ui.focus.tasksInThisPomodoroSessionScope')}>
          <div class="session-tasks__heading">
            <h2>{$t('ui.focus.queue')}</h2>
            <label class="blocked-filter">
              <span>{$t('ui.focus.blocked')}</span>
              <select bind:value={taskListBlocked} on:change={loadSessionTasks}>
                <option value="">{$t('ui.focus.either')}</option>
                <option value="false">{$t('ui.focus.notBlocked')}</option>
                <option value="true">{$t('ui.focus.blocked')}</option>
              </select>
            </label>
          </div>

          {#if listLoading}
            <p class="task-list-empty">{$t('ui.focus.loadingTasks')}</p>
          {:else if sessionTasks.length === 0}
            <p class="task-list-empty">{$t('ui.focus.noMatchingUnfinishedTasks')}</p>
          {:else}
            <TaskQueue
              tasks={sessionTasks}
              currentTaskId={currentTask?.id ?? null}
              allowFocus={true}
              allowUnblock={true}
              busyTaskId={unblockingTaskId}
              on:open={(event) => dispatch('openTask', event.detail)}
              on:focus={(event) => focusTask(event.detail)}
              on:unblock={(event) => unblockListedTask(event.detail)}
            />
          {/if}
        </section>
      {/if}
    {/if}
  </main>

  {#if breakPrompt}
    <div class="break-prompt-backdrop" role="presentation">
      <section class="break-prompt" role="dialog" aria-modal="true" aria-labelledby="break-prompt-title" aria-describedby="break-prompt-description">
        <p class="eyebrow">{breakPrompt === 'finished' ? $t('ui.focus.taskCompleted') : $t('ui.focus.taskBlocked')}</p>
        <h2 id="break-prompt-title">{$t('ui.focus.startABreak')}</h2>
        <p id="break-prompt-description">{$t('ui.focus.takeABreakNowOrKeepTheCurrent')}</p>
        <div class="break-prompt-actions">
          <AppButton on:click={keepFocusingAfterTask}>{$t('ui.focus.keepFocusing')}</AppButton>
          <AppButton variant="primary" on:click={startBreakAfterTask}>{$localized(nextBreakLabel())}</AppButton>
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
  :global(.period-button) { min-width: 9rem; }

  .running-label {
    border-radius: 999px;
    background: rgba(166, 80, 56, .1);
    color: #8e4b37;
    padding: .34rem .58rem;
    font-size: .72rem;
    font-weight: 800;
  }

  .break-mode .running-label { background: rgba(55, 95, 75, .1); color: var(--forest-2); }
  .break-mode .alarm-label,
  .alarm-label { background: #f6d7d1; color: #8d2f24; }

  .cycle-dots { display: flex; justify-content: center; gap: .4rem; margin: .85rem 0 .8rem; }
  .cycle-dots span { width: .48rem; height: .48rem; border-radius: 50%; background: #d4d0c5; }
  .cycle-dots span.done { background: #a65038; }
  .cycle-dots .long-dot { width: .7rem; border-radius: .2rem; background: #9daf9f; }

  .session-scope {
    display: grid;
    width: min(100%, 38rem);
    gap: .6rem;
    margin: 0 auto 2rem;
    border: 1px solid rgba(100, 95, 80, .14);
    border-radius: .8rem;
    background: rgba(255, 255, 255, .7);
    padding: .8rem;
    text-align: left;
  }
  .session-scope-heading { display: flex; align-items: center; justify-content: space-between; gap: .75rem; }
  .session-scope-heading strong { color: var(--forest-2); font-size: .82rem; }
  .session-scope-heading button, .scope-warning button { border: 0; background: transparent; color: var(--forest-2); padding: .2rem; font-size: .78rem; font-weight: 750; text-decoration: underline; }
  .session-scope-heading button:disabled, .scope-warning button:disabled { opacity: .5; cursor: wait; }
  .scope-selection { display: flex; flex-wrap: wrap; align-items: center; gap: .35rem; }
  .scope-selection > span:first-child { min-width: 3.8rem; color: var(--muted); font-size: .72rem; font-weight: 750; }
  .scope-empty, .missing-tag { color: var(--muted); font-size: .76rem; }
  .scope-match { margin: 0; color: var(--muted); font-size: .74rem; }
  .scope-match strong { color: var(--ink); }
  .scope-editor { display: grid; gap: .8rem; border-top: 1px solid var(--line); padding-top: .75rem; }
  .scope-editor-actions { display: flex; justify-content: flex-end; gap: .5rem; }
  .scope-warning { width: min(100%, 38rem); margin: -1rem auto 1.5rem; border: 1px solid #deb98a; border-radius: .65rem; background: #fff4e7; padding: .65rem .8rem; font-size: .78rem; line-height: 1.5; text-align: left; }
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

  .focus-task-area :global(.task-card .task-description),
  .focus-task-area :global(.task-card .description-toggle) { display: none; }

  .focus-description-editor {
    margin-top: .7rem;
    border: 1px solid rgba(100, 95, 80, .15);
    border-radius: .8rem;
    background: rgba(255, 255, 255, .68);
    padding: .75rem;
  }

  .description-heading {
    display: flex;
    min-height: 1.5rem;
    align-items: center;
    justify-content: space-between;
    gap: .75rem;
    margin-bottom: .4rem;
    color: var(--muted);
    font-size: .76rem;
  }

  .description-heading strong { color: var(--ink); font-size: .8rem; }
  .save-state { color: var(--forest-2); font-size: .72rem; font-weight: 750; }
  .save-state.error-state { color: var(--danger); }

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
