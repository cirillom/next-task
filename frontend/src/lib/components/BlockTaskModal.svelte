<script lang="ts">
  import { createEventDispatcher, onMount, tick } from 'svelte';
  import { api } from '../api/client';
  import type { Block, TaskSummary } from '../api/types';
  import { formatDateTime, localDateTime } from '../format';
  import DateTimeInput from './DateTimeInput.svelte';
  import AppButton from './AppButton.svelte';
  import TextArea from './TextArea.svelte';
  import TaskSearchResults from './TaskSearchResults.svelte';
  import BlockLabel from './BlockLabel.svelte';

  type AutoUnblockChoice = 'none' | 'tomorrow' | 'three-days' | 'week' | 'custom';

  export let taskTitle = '';
  export let taskId = 0;
  export let history: Block[] = [];
  export let busy = false;

  const dispatch = createEventDispatcher<{
    close: void;
    block: { reason?: string; blocking_task_id?: number; unblocked_at?: string | null };
    reblock: { unblocked_at: string | null };
    deleteBlock: number;
    unblock: number;
    createTask: string;
    openTask: number;
  }>();
  let reason = '';
  let tasks: TaskSummary[] = [];
  let blocker: TaskSummary | null = null;
  let mentionQuery: string | null = null;
  let mentionStart = 0;
  let mentionCursor = 0;
  let results: TaskSearchResults;
  let autoUnblockAt = '';
  let autoUnblockChoice: AutoUnblockChoice = 'none';
  let autoUnblockChoiceSelected = false;
  let reblockMode = false;
  let autoUnblockInput: DateTimeInput;

  function offsetLocalDateTime(days: number): string {
    const target = new Date();
    target.setDate(target.getDate() + days);
    target.setSeconds(0, 0);
    return localDateTime(target);
  }

  let minimumAutoUnblock = localDateTime();

  onMount(async () => {
    tasks = await api.tasks({ finished: false });
  });

  function isActive(block: Block): boolean {
    return !block.unblocked_at || new Date(block.unblocked_at).getTime() > Date.now();
  }

  function newestFirst(a: Block, b: Block): number {
    return Date.parse(b.blocked_at) - Date.parse(a.blocked_at) || b.id - a.id;
  }

  $: orderedHistory = [...history].sort((a, b) =>
    Number(isActive(b)) - Number(isActive(a)) || newestFirst(a, b)
  );
  $: latestManualId = history.filter((block) => block.reason).sort(newestFirst)[0]?.id;

  function updateMention(event: Event) {
    const input = event.target as HTMLTextAreaElement;
    reason = input.value;
    mentionCursor = input.selectionStart;
    const before = reason.slice(0, mentionCursor);
    mentionStart = before.lastIndexOf('#');
    mentionQuery = mentionStart >= 0 && !before.slice(mentionStart).includes('\n')
      ? before.slice(mentionStart + 1) : null;
  }

  function chooseBlocker(task: TaskSummary) {
    blocker = task;
    reason = reason.slice(0, mentionStart) + reason.slice(mentionCursor);
    mentionQuery = null;
  }

  function reasonKeydown(event: KeyboardEvent) {
    if (mentionQuery === null) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      mentionQuery = null;
    } else if (event.key === 'Enter') {
      event.preventDefault();
      results?.selectFirst();
    }
  }

  function close() {
    if (!busy) dispatch('close');
  }

  async function chooseAutoUnblock(choice: AutoUnblockChoice) {
    autoUnblockChoice = choice;
    autoUnblockChoiceSelected = true;
    minimumAutoUnblock = localDateTime();
    if (choice === 'none') autoUnblockAt = '';
    if (choice === 'tomorrow') autoUnblockAt = offsetLocalDateTime(1);
    if (choice === 'three-days') autoUnblockAt = offsetLocalDateTime(3);
    if (choice === 'week') autoUnblockAt = offsetLocalDateTime(7);
    if (choice === 'custom') {
      if (!autoUnblockAt) autoUnblockAt = offsetLocalDateTime(1);
      await tick();
      autoUnblockInput?.focus();
    }
  }

  function submit() {
    const trimmed = reason.trim();
    if ((!trimmed && !blocker) || busy) return;
    const unblockedAt = autoUnblockAt ? new Date(autoUnblockAt).toISOString() : null;
    if (reblockMode) {
      dispatch('reblock', { unblocked_at: unblockedAt });
      return;
    }
    dispatch('block', blocker ? { blocking_task_id: blocker.id } : { reason: trimmed, unblocked_at: unblockedAt });
  }

  async function prepareReblock(block: Block) {
    if (busy) return;
    if (autoUnblockChoiceSelected) {
      const unblockedAt = autoUnblockAt ? new Date(autoUnblockAt).toISOString() : null;
      dispatch('reblock', { unblocked_at: unblockedAt });
      return;
    }
    reason = block.reason || '';
    autoUnblockAt = '';
    autoUnblockChoice = 'none';
    reblockMode = true;
    minimumAutoUnblock = localDateTime();
    await tick();
  }

  function deleteBlock(blockId: number) {
    if (!busy) dispatch('deleteBlock', blockId);
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') close();
  }
</script>

<svelte:window on:keydown={handleKeydown} />

<div class="modal-backdrop" role="presentation" on:click|self={close}>
  <section class="block-modal" role="dialog" aria-modal="true" aria-labelledby="block-modal-title">
    <header class="block-modal__header">
      <div>
        <p class="eyebrow">Task blocking</p>
        <h1 id="block-modal-title">{reblockMode ? 'Reblock task' : 'Block task'}</h1>
        <p class="task-title">{taskTitle}</p>
      </div>
      <button type="button" class="icon-button" aria-label="Close" disabled={busy} on:click={close}>×</button>
    </header>

    <form on:submit|preventDefault={submit}>
      <div class="block-modal__body">
      {#if blocker}
        <div class="selected-blocker"><strong>{blocker.title} #{blocker.id}</strong><AppButton disabled={busy} on:click={() => (blocker = null)}>Remove</AppButton></div>
      {:else}
        <div class="reason-field">
          <label for="blocking-reason">Blocking reason</label>
          <TextArea
            id="blocking-reason"
            bind:value={reason}
            rows="4"
            placeholder="What is preventing this task from moving forward? Type # to find a task."
            disabled={busy}
            readonly={reblockMode}
            required
            on:input={updateMention}
            on:blur={() => (mentionQuery = null)}
            on:keydown={reasonKeydown}
          />
          {#if mentionQuery !== null && !reblockMode}
            <TaskSearchResults
              bind:this={results}
              {tasks}
              query={mentionQuery}
              excludeIds={[taskId, ...history.filter(isActive).map((block) => block.blocking_task_id || 0)]}
              on:select={(event) => chooseBlocker(event.detail)}
              on:create={(event) => dispatch('createTask', event.detail)}
            />
          {/if}
        </div>
        <p class="help">This reason stays in the task's blocking history after the task is unblocked.</p>

      <section class="auto-unblock-section" aria-label="Auto-unblock">
        <div class="auto-unblock-heading">
          <strong>Auto-unblock</strong>
          <span>Optional</span>
        </div>
        <div class="preset-row">
          <button type="button" class:active={autoUnblockChoice === 'tomorrow'} disabled={busy} on:click={() => chooseAutoUnblock('tomorrow')}>Tomorrow</button>
          <button type="button" class:active={autoUnblockChoice === 'three-days'} disabled={busy} on:click={() => chooseAutoUnblock('three-days')}>In 3 days</button>
          <button type="button" class:active={autoUnblockChoice === 'week'} disabled={busy} on:click={() => chooseAutoUnblock('week')}>Next week</button>
          <button type="button" class:active={autoUnblockChoice === 'custom'} disabled={busy} on:click={() => chooseAutoUnblock('custom')}>Pick date</button>
          <button type="button" class:active={autoUnblockChoice === 'none'} disabled={busy} on:click={() => chooseAutoUnblock('none')}>No auto-unblock</button>
        </div>

        {#if autoUnblockChoice === 'custom'}
          <label class="auto-unblock-field">
            <span>Auto-unblock at</span>
            <DateTimeInput
              bind:this={autoUnblockInput}
              includeTime
              bind:value={autoUnblockAt}
              min={minimumAutoUnblock}
              disabled={busy}
              on:focus={() => (minimumAutoUnblock = localDateTime())}
            />
          </label>
        {:else if autoUnblockAt}
          <p class="selected-auto-unblock">Auto-unblocks {formatDateTime(new Date(autoUnblockAt).toISOString())}</p>
        {/if}
      </section>

      <section class="history-section" aria-labelledby="blocking-history-title">
        <div class="history-heading">
          <h2 id="blocking-history-title">Blocking history</h2>
          <span>{history.length} {history.length === 1 ? 'entry' : 'entries'}</span>
        </div>

        {#if history.length}
          <ol class="block-history">
            {#each orderedHistory as block (block.id)}
              <li class:active={isActive(block)}>
                <div class="block-history__top">
                  <strong><BlockLabel {block} on:openTask={(event) => dispatch('openTask', event.detail)} /></strong>
                  <div class="history-actions">
                    {#if block.id === latestManualId && !isActive(block)}
                      <button
                        type="button"
                        class="reblock-button"
                        disabled={busy}
                        on:click={() => prepareReblock(block)}
                      >
                        Reblock with this reason
                      </button>
                    {/if}
                    {#if isActive(block)}
                      <AppButton disabled={busy} on:click={() => dispatch('unblock', block.id)}>Unblock</AppButton>
                    {:else}
                      <button
                        type="button"
                        class="trash-button"
                        aria-label="Delete blocking reason"
                        title="Delete blocking reason"
                        disabled={busy}
                        on:click={() => deleteBlock(block.id)}
                      >
                        <svg viewBox="0 0 24 24" aria-hidden="true">
                          <path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v5m4-5v5" />
                        </svg>
                      </button>
                    {/if}
                  </div>
                </div>
                <span>Blocked {formatDateTime(block.blocked_at)}</span>
                <span>
                  {#if !block.unblocked_at}
                    Currently active
                  {:else if isActive(block)}
                    Auto-unblocks {formatDateTime(block.unblocked_at)}
                  {:else}
                    Unblocked {formatDateTime(block.unblocked_at)}
                  {/if}
                </span>
              </li>
            {/each}
          </ol>
        {:else}
          <p class="history-empty">This task has not been blocked before.</p>
        {/if}
      </section>
      {/if}
      </div>

      <footer class="block-modal__actions">
        <AppButton disabled={busy} on:click={close}>Cancel</AppButton>
        <AppButton type="submit" variant="primary" disabled={busy || (!reason.trim() && !blocker)}>
          {#if busy}
            {reblockMode ? 'Reblocking…' : 'Blocking…'}
          {:else}
            {reblockMode ? 'Reblock task' : 'Block task'}
          {/if}
        </AppButton>
      </footer>
    </form>
  </section>
</div>

<style>
  .block-modal {
    width: min(100%, 42rem);
    max-height: calc(100vh - 2rem);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    border-radius: 1rem;
    background: var(--paper);
    box-shadow: 0 30px 90px rgba(0, 0, 0, .3);
  }

  .block-modal__header {
    display: flex;
    flex: 0 0 auto;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    border-bottom: 1px solid var(--line);
    padding: 1.35rem 1.4rem 1.1rem;
  }

  .block-modal__header h1 { margin: 0; font-size: 2rem; }
  .task-title { margin: .45rem 0 0; color: var(--muted); font-weight: 650; }

  form { display: flex; min-height: 0; flex-direction: column; }
  .block-modal__body { min-height: 0; overflow-y: auto; padding: 1.25rem 1.4rem 0; }
  form :global(.app-text-area) { min-height: 7rem; line-height: 1.5; }
  form :global(.app-text-area[readonly]) { background: #f5f2ea; color: var(--muted); }
  .selected-blocker { display: flex; align-items: center; justify-content: space-between; gap: .5rem; border: 1px solid var(--line); border-radius: .55rem; padding: .5rem .65rem; }
  .reason-field { position: relative; display: grid; gap: .35rem; }
  .help { margin: .45rem 0 0; }

  .auto-unblock-section {
    display: grid;
    gap: .55rem;
    margin-top: 1rem;
    border-top: 1px solid var(--line);
    padding-top: .9rem;
  }

  .auto-unblock-heading {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
  }

  .auto-unblock-heading span { color: var(--muted); font-size: .72rem; }

  .preset-row { display: flex; flex-wrap: wrap; gap: .4rem; }

  .preset-row button {
    border: 1px solid #cbc8be;
    border-radius: 999px;
    background: #fff;
    color: var(--muted);
    padding: .42rem .65rem;
    font-size: .75rem;
    font-weight: 700;
  }

  .preset-row button:hover:not(:disabled),
  .preset-row button.active {
    border-color: #9daa9f;
    background: #eef2ef;
    color: var(--forest-2);
  }

  .auto-unblock-field {
    display: flex;
    align-items: center;
    gap: .75rem;
    color: var(--muted);
    font-size: .82rem;
    font-weight: 650;
  }

  .auto-unblock-field > span { flex: 0 0 auto; }

  .auto-unblock-field :global(input) {
    min-width: 0;
    flex: 1 1 auto;
    height: 2.35rem;
    padding: .45rem .65rem;
    font-size: .82rem;
  }

  .selected-auto-unblock { margin: 0; color: var(--forest-2); font-size: .78rem; font-weight: 700; }

  .history-section { margin-top: 1rem; border-top: 1px solid var(--line); padding-top: 1.1rem; }
  .history-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 1rem; }
  .history-heading h2 { margin: 0; }
  .history-heading span { color: var(--muted); font-size: .78rem; }
  .block-history { display: grid; gap: .65rem; margin: .8rem 0 0; padding: 0; list-style: none; }

  .block-history li {
    display: grid;
    gap: .22rem;
    border-left: 3px solid #c9c4b8;
    border-radius: .5rem;
    background: #f5f2ea;
    padding: .7rem .8rem;
  }

  .block-history li.active { border-left-color: #bb623f; background: #f8e6dc; }
  .block-history__top { display: flex; align-items: flex-start; justify-content: space-between; gap: .75rem; }
  .block-history__top strong { min-width: 0; overflow-wrap: anywhere; }
  .block-history span { color: var(--muted); font-size: .78rem; }
  .history-actions { display: flex; flex: 0 0 auto; align-items: center; gap: .35rem; }

  .reblock-button {
    border: 1px solid #bdb7aa;
    border-radius: .45rem;
    background: #fff;
    color: var(--forest-2);
    padding: .4rem .55rem;
    font-size: .76rem;
    font-weight: 700;
  }

  .trash-button {
    display: grid;
    width: 2rem;
    height: 2rem;
    place-items: center;
    border: 0;
    border-radius: .4rem;
    background: transparent;
    color: var(--muted);
    padding: 0;
  }

  .trash-button:hover:not(:disabled),
  .trash-button:focus-visible { background: #fff; color: #9a4f3f; }

  .trash-button svg {
    width: 1rem;
    height: 1rem;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.8;
  }

  .history-empty {
    margin: .8rem 0 0;
    border: 1px dashed var(--line);
    border-radius: .6rem;
    color: var(--muted);
    padding: .85rem;
    text-align: center;
  }

  .block-modal__actions {
    display: flex;
    flex: 0 0 auto;
    justify-content: flex-end;
    gap: .7rem;
    border-top: 1px solid var(--line);
    background: var(--paper);
    padding: 1rem 1.4rem;
  }

  @media (max-width: 600px) {
    .preset-row button { flex: 1 1 auto; }
    .auto-unblock-field { align-items: stretch; flex-direction: column; gap: .35rem; font-size: .76rem; }
    .auto-unblock-field :global(input) { font-size: .76rem; }
    .block-history__top { gap: .5rem; }
    .reblock-button { white-space: nowrap; }
  }
</style>
