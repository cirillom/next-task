<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Block } from '../api/types';
  import { formatDateTime } from '../format';

  export let taskTitle = '';
  export let history: Block[] = [];
  export let busy = false;

  const dispatch = createEventDispatcher<{
    close: void;
    block: { reason: string; unblocked_at: string | null };
    reblock: void;
    deleteBlock: number;
  }>();
  let reason = '';
  let autoUnblockAt = '';

  function datetimeLocalNow(): string {
    const now = new Date();
    const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
    return local.toISOString().slice(0, 16);
  }

  let minimumAutoUnblock = datetimeLocalNow();

  function isActive(block: Block): boolean {
    return !block.unblocked_at || new Date(block.unblocked_at).getTime() > Date.now();
  }

  function close() {
    if (!busy) dispatch('close');
  }

  function submit() {
    const trimmed = reason.trim();
    if (!trimmed || busy) return;
    const unblockedAt = autoUnblockAt ? new Date(autoUnblockAt).toISOString() : null;
    dispatch('block', { reason: trimmed, unblocked_at: unblockedAt });
  }

  function reblock() {
    if (!busy) dispatch('reblock');
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
        <h1 id="block-modal-title">Block task</h1>
        <p class="task-title">{taskTitle}</p>
      </div>
      <button type="button" class="icon-button" aria-label="Close" disabled={busy} on:click={close}>×</button>
    </header>

    <form on:submit|preventDefault={submit}>
      <label>
        Blocking reason
        <textarea
          bind:value={reason}
          rows="4"
          placeholder="What is preventing this task from moving forward?"
          disabled={busy}
          required
        ></textarea>
      </label>
      <p class="help">This reason stays in the task's blocking history after the task is unblocked.</p>

      <label class="auto-unblock-field">
        <span>Auto-unblock at <span class="optional">(optional)</span></span>
        <input
          type="datetime-local"
          lang="pt-BR"
          bind:value={autoUnblockAt}
          min={minimumAutoUnblock}
          disabled={busy}
          on:focus={() => (minimumAutoUnblock = datetimeLocalNow())}
        />
      </label>

      <section class="history-section" aria-labelledby="blocking-history-title">
        <div class="history-heading">
          <h2 id="blocking-history-title">Blocking history</h2>
          <span>{history.length} {history.length === 1 ? 'entry' : 'entries'}</span>
        </div>

        {#if history.length}
          <ol class="block-history">
            {#each history as block, index}
              <li class:active={isActive(block)}>
                <div class="block-history__top">
                  <strong>{block.reason}</strong>
                  <div class="history-actions">
                    {#if index === 0 && !isActive(block)}
                      <button type="button" class="reblock-button" disabled={busy} on:click={reblock}>
                        {busy ? 'Reblocking…' : 'Reblock with this reason'}
                      </button>
                    {/if}
                    {#if !isActive(block)}
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

      <footer class="block-modal__actions">
        <button type="button" disabled={busy} on:click={close}>Cancel</button>
        <button class="primary" disabled={busy || !reason.trim()}>{busy ? 'Blocking…' : 'Block task'}</button>
      </footer>
    </form>
  </section>
</div>

<style>
  .block-modal {
    width: min(100%, 42rem);
    max-height: calc(100vh - 2rem);
    overflow: auto;
    border-radius: 1rem;
    background: var(--paper);
    box-shadow: 0 30px 90px rgba(0, 0, 0, .3);
  }

  .block-modal__header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    border-bottom: 1px solid var(--line);
    padding: 1.35rem 1.4rem 1.1rem;
  }

  .block-modal__header h1 {
    margin: 0;
    font-size: 2rem;
  }

  .task-title {
    margin: .45rem 0 0;
    color: var(--muted);
    font-weight: 650;
  }

  form {
    display: grid;
    gap: 0;
    padding: 1.25rem 1.4rem 0;
  }

  textarea {
    min-height: 7rem;
    line-height: 1.5;
  }

  .help {
    margin: .45rem 0 0;
  }

  .auto-unblock-field {
    display: flex;
    align-items: center;
    gap: .75rem;
    margin-top: .85rem;
    color: var(--muted);
    font-size: .82rem;
    font-weight: 650;
  }

  .auto-unblock-field > span {
    flex: 0 0 auto;
  }

  .auto-unblock-field input {
    min-width: 0;
    flex: 1 1 auto;
    height: 2.35rem;
    padding: .45rem .65rem;
    font-size: .82rem;
  }

  .optional {
    color: var(--muted);
    font-weight: 500;
  }

  .history-section {
    margin-top: 1rem;
    border-top: 1px solid var(--line);
    padding-top: 1.1rem;
  }

  .history-heading {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
  }

  .history-heading h2 {
    margin: 0;
  }

  .history-heading span {
    color: var(--muted);
    font-size: .78rem;
  }

  .block-history {
    display: grid;
    gap: .65rem;
    margin: .8rem 0 0;
    padding: 0;
    list-style: none;
  }

  .block-history li {
    display: grid;
    gap: .22rem;
    border-left: 3px solid #c9c4b8;
    border-radius: .5rem;
    background: #f5f2ea;
    padding: .7rem .8rem;
  }

  .block-history li.active {
    border-left-color: #bb623f;
    background: #f8e6dc;
  }

  .block-history__top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: .75rem;
  }

  .block-history__top strong {
    min-width: 0;
    overflow-wrap: anywhere;
  }

  .block-history span {
    color: var(--muted);
    font-size: .78rem;
  }

  .history-actions {
    display: flex;
    flex: 0 0 auto;
    align-items: center;
    gap: .35rem;
  }

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
  .trash-button:focus-visible {
    background: #fff;
    color: #9a4f3f;
  }

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
    justify-content: flex-end;
    gap: .7rem;
    border-top: 1px solid var(--line);
    margin: 1.25rem -1.4rem 0;
    padding: 1rem 1.4rem;
  }

  .block-modal__actions > button:not(.primary) {
    border: 1px solid #cbc8be;
    border-radius: .5rem;
    background: #fff;
    color: var(--ink);
    padding: .65rem .9rem;
  }

  @media (max-width: 600px) {
    .auto-unblock-field {
      gap: .5rem;
      font-size: .76rem;
    }

    .auto-unblock-field input {
      font-size: .76rem;
    }

    .block-history__top {
      gap: .5rem;
    }

    .reblock-button {
      white-space: nowrap;
    }
  }
</style>