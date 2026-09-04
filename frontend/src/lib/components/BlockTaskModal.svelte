<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import type { Block } from '../api/types';

  export let taskTitle = '';
  export let history: Block[] = [];
  export let busy = false;

  const dispatch = createEventDispatcher<{ close: void; block: string }>();
  let reason = '';
  $: lastBlock = history[0] ?? null;

  function close() {
    if (!busy) dispatch('close');
  }

  function submit() {
    const trimmed = reason.trim();
    if (trimmed && !busy) dispatch('block', trimmed);
  }

  function reblockLastReason() {
    if (lastBlock && !busy) dispatch('block', lastBlock.reason);
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === 'Escape') close();
  }

  function formatDate(value: string): string {
    return new Date(value).toLocaleString();
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
      {#if lastBlock}
        <section class="previous-blocker" aria-labelledby="previous-blocker-title">
          <div>
            <span class="field-label" id="previous-blocker-title">Previous blocker</span>
            <strong>{lastBlock.reason}</strong>
            <span class="previous-blocker__time">
              Last blocked {formatDate(lastBlock.blocked_at)}
              {#if lastBlock.unblocked_at} · unblocked {formatDate(lastBlock.unblocked_at)}{/if}
            </span>
          </div>
          <button type="button" class="reblock-button" disabled={busy} on:click={reblockLastReason}>
            {busy ? 'Blocking…' : 'Reblock with this reason'}
          </button>
        </section>
      {/if}

      <label class="reason-field">
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

      <section class="history-section" aria-labelledby="blocking-history-title">
        <div class="history-heading">
          <h2 id="blocking-history-title">Blocking history</h2>
          <span>{history.length} {history.length === 1 ? 'entry' : 'entries'}</span>
        </div>

        {#if history.length}
          <ol class="block-history">
            {#each history as block}
              <li class:active={!block.unblocked_at}>
                <strong>{block.reason}</strong>
                <span>Blocked {formatDate(block.blocked_at)}</span>
                <span>{block.unblocked_at ? `Unblocked ${formatDate(block.unblocked_at)}` : 'Currently active'}</span>
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

  .previous-blocker {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: 1.1rem;
    border: 1px solid #d9c9a7;
    border-radius: .7rem;
    background: #faf3e3;
    padding: .85rem .9rem;
  }

  .previous-blocker > div {
    min-width: 0;
    display: grid;
    gap: .22rem;
  }

  .previous-blocker strong {
    overflow-wrap: anywhere;
  }

  .previous-blocker__time {
    color: var(--muted);
    font-size: .76rem;
  }

  .reblock-button {
    flex: 0 0 auto;
    border: 1px solid #b69657;
    border-radius: .55rem;
    background: #fffaf0;
    color: var(--ink);
    padding: .6rem .75rem;
    font-weight: 700;
  }

  .reason-field {
    border-top: 1px solid var(--line);
    padding-top: 1.05rem;
  }

  textarea {
    min-height: 7rem;
    line-height: 1.5;
  }

  .help {
    margin: .45rem 0 0;
  }

  .history-section {
    margin-top: 1.25rem;
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

  .block-history span {
    color: var(--muted);
    font-size: .78rem;
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
    .previous-blocker {
      align-items: stretch;
      flex-direction: column;
    }

    .reblock-button {
      width: 100%;
    }
  }
</style>
