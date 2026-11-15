<script lang="ts">
  import { createEventDispatcher, onDestroy } from 'svelte';
  import type { Task } from '../api/types';
  import { errorMessage, t, text, type Message } from '../i18n';
  import { cardDescriptionSaves } from '../cardDescriptionSaves';
  import Markdown from './Markdown.svelte';
  import AppButton from './AppButton.svelte';

  export let task: Task;
  export let disabled = false;
  const dispatch = createEventDispatcher<{ changed: Task; error: Message; open: number }>();
  let revision = 0;
  let state: ReturnType<typeof cardDescriptionSaves.get>;
  const unsubscribe = cardDescriptionSaves.subscribe(() => revision++);
  onDestroy(unsubscribe);
  $: if (revision >= 0) state = cardDescriptionSaves.get(task.id);
  $: displayed = state?.latest || task;
  $: failure = state?.error ? errorMessage(state.error, 'ui.nextTaskCard.actionFailed') : '';
  $: cardDescriptionSaves.acknowledge(task);

  async function save(value: string, base: string | null, id: number) {
    if (disabled) return;
    const updated = await cardDescriptionSaves.save({id, base, value});
    if (task.id !== id) return;
    if (updated) dispatch('changed', updated);
    else if (cardDescriptionSaves.get(id)?.error) dispatch('error', errorMessage(cardDescriptionSaves.get(id)?.error, 'ui.nextTaskCard.actionFailed'));
  }
</script>

<Markdown source={displayed.description || ''} editable={!disabled} disabled={disabled || !!state?.busy || !!state?.pending} on:input={(event) => void save(event.detail, displayed.description, displayed.id)} />
{#if failure && state?.pending}
  <div class="save-error" role="alert">
    <span>{$text(failure)}</span>
    <details><summary>{$t('ui.markdownEditor.attemptedChange')}</summary><pre>{state.pending.value}</pre></details>
    {#if state.conflict}
      <AppButton on:click={() => dispatch('open', task.id)}>{$t('ui.markdownEditor.reviewTask')}</AppButton>
    {:else}
      <AppButton on:click={() => state?.pending && void save(state.pending.value, state.pending.base, state.pending.id)}>{$t('ui.focus.retrySave')}</AppButton>
    {/if}
    <AppButton on:click={() => {cardDescriptionSaves.discard(task.id); if (state?.latest) dispatch('changed', state.latest);}}>{$t('ui.markdownEditor.discardAttempt')}</AppButton>
  </div>
{/if}

<style>
  .save-error { display: grid; gap: .35rem; color: var(--danger); }
  .save-error pre { max-height: 10rem; overflow: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
