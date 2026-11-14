<script lang="ts">
  import { t, text, errorMessage, type Message } from '../lib/i18n';
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import type { Task } from '../lib/api/types';
  import { formatDateTime } from '../lib/format';
  import Markdown from '../lib/components/Markdown.svelte';
  import AppButton from '../lib/components/AppButton.svelte';

  const dispatch = createEventDispatcher<{ openTask: number }>();

  let drafts: Task[] = [];
  let loading = true;
  let error: Message = '';

  async function load() {
    loading = true;
    error = '';
    try {
      drafts = await api.drafts();
    } catch (reason) {
      error = errorMessage(reason, 'ui.drafts.couldNotLoadDrafts');
    } finally {
      loading = false;
    }
  }

  onMount(load);
</script>

<div class="page-heading">
  <div>
    <p class="eyebrow">{$t('ui.drafts.needsYourInput')}</p>
    <h1>{$t('ui.app.drafts')}</h1>
    <p class="draft-intro">{$t('ui.drafts.prepareTasksHereWithoutMakingThemActiveUntil')}</p>
  </div>
</div>

{#if error}<p class="error" role="alert">{$text(error)}</p>{/if}
{#if loading}
  <p class="empty">{$t('ui.drafts.loadingDrafts')}</p>
{:else if !drafts.length}
  <section class="empty draft-empty">
    <strong>{$t('ui.drafts.noDraftsWaiting')}</strong>
    <span>{$t('ui.drafts.useNewTaskAndChooseDraftTaskWhen')}</span>
  </section>
{:else}
  <div class="draft-list">
    {#each drafts as draft (draft.id)}
      <article class="draft-card">
        <div class="draft-copy">
          <div class="draft-title-row">
            <h2>{draft.title}</h2>
            <span class="task-id">#{draft.id}</span>
          </div>
          {#if draft.description}
            <div class="draft-description"><Markdown source={draft.description} /></div>
          {/if}
          <div class="draft-meta">{$t('ui.drafts.captured', { value1: formatDateTime(draft.created_at) })}</div>
        </div>

          <AppButton variant="primary" className="edit-draft-button" on:click={() => dispatch('openTask', draft.id)}>
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l10.5-10.5a2.8 2.8 0 0 0-4-4L4 16v4Z" /><path d="m13.5 6.5 4 4" /></svg>
            {$t('ui.drafts.editDraft')}
          </AppButton>
      </article>
    {/each}
  </div>
{/if}

<style>
  .page-heading { align-items: flex-start; }
  .draft-intro { max-width: 42rem; margin: .25rem 0 0; color: var(--muted); }
  .draft-empty { display: grid; gap: .25rem; }
  .draft-list { display: grid; gap: .7rem; }

  .draft-card {
    display: flex;
    align-items: center;
    gap: 1rem;
    border: 1px solid var(--line);
    border-radius: .75rem;
    background: var(--paper);
    padding: .85rem 1rem;
  }

  .draft-copy { min-width: 0; flex: 1; }
  .draft-title-row { display: flex; align-items: baseline; gap: .5rem; }
  .draft-title-row h2 { margin: 0; font-size: 1rem; }
  .task-id { color: var(--muted); font-size: .72rem; font-variant-numeric: tabular-nums; }
  .draft-description { max-height: 4.5rem; overflow: hidden; margin-top: .35rem; color: #4c524e; font-size: .86rem; }
  .draft-description :global(.markdown > :first-child) { margin-top: 0; }
  .draft-description :global(.markdown > :last-child) { margin-bottom: 0; }
  .draft-meta { margin-top: .45rem; color: var(--muted); font-size: .72rem; }

  :global(.edit-draft-button) {
    display: inline-flex;
    flex: 0 0 auto;
    align-items: center;
    gap: .35rem;
    white-space: nowrap;
  }

  :global(.edit-draft-button svg) {
    width: 1rem;
    height: 1rem;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.9;
  }

  @media (max-width: 640px) {
    .draft-card { align-items: stretch; flex-direction: column; }
    :global(.edit-draft-button) { justify-content: center; }
  }
</style>
