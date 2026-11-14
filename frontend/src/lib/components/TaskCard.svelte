<script lang="ts">
  import TaskAction from './TaskAction.svelte';
  import { t, localized, numeric, errorMessage, type Message } from '../i18n';
  import { createEventDispatcher } from 'svelte';
  import { api } from '../api/client';
  import type { Task } from '../api/types';
  import RankingBoost from './RankingBoost.svelte';
  import { daysSince, formatDate, formatDateTime, localDate } from '../format';
  import BlockTaskModal from './BlockTaskModal.svelte';
  import BlockSummary from './BlockSummary.svelte';
  import DateTimeInput from './DateTimeInput.svelte';
  import TagBadge from './TagBadge.svelte';
  import Markdown from './Markdown.svelte';
  import TaskCompletionDialog from './TaskCompletionDialog.svelte';
  import TaskHierarchy from './TaskHierarchy.svelte';
  import TaskAbandonment from './TaskAbandonment.svelte';

  export let task: Task;
  export let readOnly = false;

  const dispatch = createEventDispatcher<{ changed: Task; open: number; error: Message; createBlocker: { taskId: number; title: string } }>();
  let busy = false;
  let descriptionExpanded = false;
  let blockModalOpen = false;
  let completionOpen = false;
  let dueDateDraft = task.due_date || '';

  $: if (!busy && dueDateDraft !== (task.due_date || '')) {
    dueDateDraft = task.due_date || '';
  }

  function idleAnchor(): string {
    return task.last_worked_at || task.created_at;
  }

  function idleLabel(): string {
    const days = daysSince(idleAnchor());
    return $t('ui.nextTaskCard.idle', { count: days, date: formatDate(idleAnchor()) });
  }

  async function act(action: () => Promise<Task>) {
    busy = true;
    try {
      dispatch('changed', await action());
    } catch (error) {
      dispatch('error', errorMessage(error, 'ui.nextTaskCard.actionFailed'));
    } finally {
      busy = false;
    }
  }

  async function runBlockingAction(action: () => Promise<Task>, fallbackMessage: string) {
    busy = true;
    try {
      dispatch('changed', await action());
      blockModalOpen = false;
    } catch (error) {
      dispatch('error', errorMessage(error, fallbackMessage));
    } finally {
      busy = false;
    }
  }

  function block(request: { reason?: string; blocking_task_id?: number; unblocked_at?: string | null }) {
    void runBlockingAction(
      () => api.blockTask(task.id, request),
      'ui.nextTaskCard.couldNotBlockTask'
    );
  }

  function reblock(request: { unblocked_at: string | null }) {
    void runBlockingAction(
      () => api.reblockTask(task.id, request.unblocked_at),
      'ui.nextTaskCard.couldNotReblockTask'
    );
  }

  async function deleteBlock(blockId: number) {
    busy = true;
    try {
      dispatch('changed', await api.deleteBlock(task.id, blockId));
    } catch (error) {
      dispatch('error', errorMessage(error, 'ui.nextTaskCard.couldNotDeleteBlockingReason'));
    } finally {
      busy = false;
    }
  }

  function markWorkedNow() {
    void act(() => api.updateTask(task.id, { last_worked_at: new Date().toISOString() }));
  }

  async function updateDueDate(value: string) {
    busy = true;
    try {
      const updated = await api.updateTask(task.id, { due_date: value || null });
      dueDateDraft = updated.due_date || '';
      dispatch('changed', updated);
    } catch (error) {
      dueDateDraft = task.due_date || '';
      dispatch('error', errorMessage(error, 'ui.taskCard.couldNotUpdateDueDate'));
    } finally {
      busy = false;
    }
  }

  function toggleFinished() {
    if (task.finished_at) {
      void act(() => api.reopenTask(task.id));
      return;
    }
    if (task.unfinished_descendant_count > 0) {
      completionOpen = true;
      return;
    }
    void act(() => api.finishTask(task.id));
  }

  async function confirmFinish() {
    busy = true;
    try {
      const updated = await api.finishTask(task.id);
      completionOpen = false;
      dispatch('changed', updated);
    } catch (error) {
      dispatch('error', errorMessage(error, 'ui.nextTaskCard.couldNotFinishTask'));
    } finally {
      busy = false;
    }
  }
</script>

<article class:blocked={task.current_block} class:finished={task.finished_at} class="task-card">
  <div class="task-card__top">
    <button class="title-button" on:click={() => dispatch('open', task.id)}>
      <span>{task.title}</span>
      <span class="task-id">#{task.id}</span>
    </button>
    <div class="task-card__header-actions">
      {#if !readOnly}
        <button
          type="button"
          class="edit-button"
          aria-label={$t('ui.nextTaskCard.editTask')}
          title={$t('ui.nextTaskCard.editTask')}
          disabled={busy}
          on:click={() => dispatch('open', task.id)}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h9" /><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
        </button>
      {/if}
      <span class="score" title={$t('ui.nextTaskCard.calculatedScore')}>{$numeric(task.score, { minimumFractionDigits: 1, maximumFractionDigits: 1 })}</span>
      <RankingBoost {task} on:open={(event) => dispatch('open', event.detail)} />
    </div>
  </div>

  <TaskHierarchy {task} on:open={(event) => dispatch('open', event.detail)} />

  {#if task.description}
    <div class:expanded={descriptionExpanded} class="task-description"><Markdown source={task.description} /></div>
    <button type="button" class="description-toggle" aria-expanded={descriptionExpanded} on:click={() => (descriptionExpanded = !descriptionExpanded)}>
      {descriptionExpanded ? $t('ui.nextTaskCard.collapseDescription') : $t('ui.nextTaskCard.expandDescription')}
    </button>
  {/if}

  <div class="meta-row">
    {#if readOnly}<span class="priority" title={$t('ui.taskCard.priority')}>{task.priority}</span>{/if}
    <span class="date-meta" title={formatDateTime(task.created_at)}>{$t('ui.nextTaskCard.created', { value1: formatDate(task.created_at) })}</span>
    {#if task.finished_at}<span class="date-meta" title={formatDateTime(task.finished_at)}>{$t('ui.taskCard.finished', { value1: formatDateTime(task.finished_at) })}</span>{/if}
    <span class="date-meta" title={formatDateTime(idleAnchor())}>{$localized(idleLabel())}</span>
  </div>

  {#if task.direct_tags.length}
    <div class="tag-row">{#each task.direct_tags as tag}<TagBadge {tag} />{/each}</div>
  {/if}

  {#if task.active_blocks.length}<BlockSummary blocks={task.active_blocks} compact on:openTask={(event) => dispatch('open', event.detail)} />{/if}

  {#if !readOnly || task.abandoned_by_task_id}
    <div class="task-actions">
      {#if !readOnly && !task.abandoned_by_task_id}
        <TaskAction icon={task.finished_at ? 'reopen' : 'finish'} label={task.finished_at ? $t('ui.taskCard.reopen') : $t('ui.nextTaskCard.finish')} className="finish-action" disabled={busy} title={task.finished_at ? $t('ui.taskCard.reopenTask') : $t('ui.taskCard.finishTask')} ariaLabel={task.finished_at ? $t('ui.taskCard.reopenTask') : $t('ui.taskCard.finishTask')} on:click={toggleFinished} />

        <TaskAction icon="worked" label={$t('ui.nextTaskCard.workedNow')} className="quick-action worked-action" disabled={busy} title={$t('ui.taskCard.setLastWorkedOnToNow')} on:click={markWorkedNow} />

        <TaskAction icon="block" label={task.current_block ? $t('ui.taskCard.manageBlocks') : $t('ui.nextTaskCard.block')} className="quick-action block-action" disabled={busy} active={!!task.current_block} on:click={() => (blockModalOpen = true)} />

        <div class="due-date-action" class:overdue={!!dueDateDraft && !task.finished_at && dueDateDraft < localDate()}>
          <DateTimeInput
            bind:value={dueDateDraft}
            pickerOnly
            pickerText={dueDateDraft ? $t('ui.nextTaskCard.due', { value1: formatDate(dueDateDraft) }) : $t('ui.taskCard.dueDate')}
            pickerLabel={dueDateDraft ? $t('ui.taskCard.changeDueDateFrom', { value1: formatDate(dueDateDraft) }) : $t('ui.taskCard.setDueDate')}
            disabled={busy}
            on:change={(event) => void updateDueDate(event.detail)}
          />
        </div>

        <div class="priority-stepper" aria-label={$t('ui.taskCard.priority')}>
          <button type="button" aria-label={$t('ui.taskCard.decreasePriority')} title={$t('ui.taskCard.decreasePriority')} disabled={busy || task.priority <= 1} on:click={() => act(() => api.updateTask(task.id, { priority: task.priority - 1 }))}>−</button>
          <span title={$t('ui.taskCard.priority')}>{task.priority}</span>
          <button type="button" aria-label={$t('ui.taskCard.increasePriority')} title={$t('ui.taskCard.increasePriority')} disabled={busy} on:click={() => act(() => api.updateTask(task.id, { priority: task.priority + 1 }))}>+</button>
        </div>
      {/if}
      <TaskAbandonment {task} {readOnly} disabled={busy} on:abandon={() => void act(() => api.abandonTask(task.id))} on:restore={() => void act(() => api.restoreTask(task.id))} on:open={(event) => dispatch('open', event.detail)} />
    </div>
  {/if}
</article>

{#if blockModalOpen}
  <BlockTaskModal taskTitle={task.title} taskId={task.id} history={task.blocking_history} {busy} on:close={() => (blockModalOpen = false)} on:block={(event) => block(event.detail)} on:unblock={(event) => void runBlockingAction(() => api.unblockOne(task.id, event.detail), 'ui.blockTaskModal.couldNotUnblockTask')} on:createTask={(event) => { blockModalOpen = false; dispatch('createBlocker', { taskId: task.id, title: event.detail }); }} on:openTask={(event) => dispatch('open', event.detail)} on:reblock={(event) => reblock(event.detail)} on:deleteBlock={(event) => deleteBlock(event.detail)} />
{/if}

{#if completionOpen}
  <TaskCompletionDialog taskId={task.id} taskTitle={task.title} {busy} on:close={() => (completionOpen = false)} on:confirm={() => void confirmFinish()} />
{/if}

<style>
  .title-button { display: flex; align-items: baseline; gap: .45rem; }
  .task-id { flex: 0 0 auto; color: var(--muted); font-size: .72rem; font-weight: 700; opacity: .72; }
  .date-meta { color: var(--muted); font-variant-numeric: tabular-nums; }
  .meta-row > span + span::before { content: '·'; margin-right: .65rem; color: #b8b3a8; font-weight: 700; }
  .task-card__header-actions { display: flex; align-items: center; gap: .35rem; }

  .edit-button { display: grid; width: 1.75rem; height: 1.75rem; place-items: center; border: 0; border-radius: .4rem; background: transparent; color: var(--muted); opacity: .35; padding: .3rem; transition: opacity .15s ease, background .15s ease; }
  .edit-button svg { width: 1rem; height: 1rem; fill: none; stroke: currentColor; stroke-linecap: round; stroke-linejoin: round; stroke-width: 1.8; }
  .edit-button svg { width: 100%; height: 100%; }
  .task-card:hover .edit-button, .edit-button:focus-visible { opacity: .85; }
  .edit-button:hover:not(:disabled) { background: rgba(0, 0, 0, .04); }

  .task-actions { --task-action-height: 2rem; --task-action-padding: .62rem; }

  .due-date-action { color: var(--forest-2); }
  .due-date-action.overdue { color: #9b422d; }
  .due-date-action :global(.picker-trigger) { color: inherit; }

  .priority-stepper { display: inline-grid; height: 2rem; grid-template-columns: 1.65rem auto 1.65rem; align-items: stretch; overflow: hidden; border: 1px solid #cfcbc0; border-radius: .5rem; background: #fbfaf6; }
  .priority-stepper button { min-width: 0; border: 0; border-radius: 0; background: transparent; padding: 0; font-size: .95rem; line-height: 1; }
  .priority-stepper button:hover:not(:disabled) { background: rgba(0, 0, 0, .045); }
  .priority-stepper span { display: grid; min-width: 1.65rem; place-items: center; border-right: 1px solid #dedad0; border-left: 1px solid #dedad0; padding: 0 .2rem; color: var(--forest); font-size: .76rem; font-weight: 800; font-variant-numeric: tabular-nums; }

  .task-description { width: 100%; height: 7rem; margin-top: .6rem; overflow-y: auto; padding: .65rem .75rem; border: 1px solid var(--line); border-radius: .55rem; background: #faf8f2; }
  .task-description.expanded { height: auto; overflow-y: visible; }
  .description-toggle { margin-top: .35rem; border: 0; background: transparent; color: var(--forest-2); padding: .15rem 0; font-size: .8rem; font-weight: 700; text-decoration: underline; text-underline-offset: .15rem; }

  @media (max-width: 600px) {
    .edit-button { opacity: .6; }

  }
</style>
