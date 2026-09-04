<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { api } from '../api/client';
  import { geminiApi, type TextToTaskDraft } from '../api/gemini';
  import type { Task, TaskInput, Workspace } from '../api/types';
  import TaskForm from './TaskForm.svelte';

  export let workspace: Workspace;
  const dispatch = createEventDispatcher<{ close: void; saved: Task }>();

  let stage: 'prompt' | 'review' = 'prompt';
  let requestText = '';
  let draft: TextToTaskDraft | null = null;
  let busy = false;
  let error = '';

  async function generate() {
    busy = true;
    error = '';
    try {
      draft = await geminiApi.taskDraft(workspace.id, requestText);
      stage = 'review';
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not create a task draft';
    } finally {
      busy = false;
    }
  }

  async function save(input: TaskInput) {
    busy = true;
    error = '';
    try {
      const saved = await api.createTask({ ...input, workspace_id: workspace.id });
      dispatch('saved', saved);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not save task';
    } finally {
      busy = false;
    }
  }

  function backToPrompt() {
    stage = 'prompt';
    error = '';
  }
</script>

<div class="modal-backdrop" role="presentation" on:click|self={() => dispatch('close')}>
  <div class="task-editor text-task-modal" role="dialog" aria-modal="true" aria-labelledby="text-task-title">
    <header class="editor-header">
      <div>
        <p class="eyebrow">{stage === 'prompt' ? 'Gemini Flash' : 'Review before creating'}</p>
        <h1 id="text-task-title">{stage === 'prompt' ? 'Text to task' : 'New task'}</h1>
      </div>
      <button class="icon-button" aria-label="Close" on:click={() => dispatch('close')}>×</button>
    </header>

    {#if stage === 'prompt'}
      <form class="prompt-form" on:submit|preventDefault={generate}>
        <p class="muted">Describe one task for <strong>{workspace.name}</strong>. Include dates, urgency, assignees, or useful context naturally.</p>
        <label>
          What needs to be done?
          <textarea bind:value={requestText} rows="9" maxlength="12000" required placeholder="Example: Ask Marina to review the release notes by Friday. This is urgent and belongs to the website launch."></textarea>
        </label>
        {#if error}<p class="error" role="alert">{error}</p>{/if}
        <footer class="modal-actions">
          <button type="button" on:click={() => dispatch('close')}>Cancel</button>
          <button class="primary" disabled={busy || !requestText.trim()}>{busy ? 'Drafting…' : 'Create draft'}</button>
        </footer>
      </form>
    {:else if draft}
      <p class="notice">Gemini suggested the initial values using <code>{draft.model}</code>. Review them before creating the task.</p>
      <TaskForm
        {workspace}
        initialTitle={draft.title}
        initialDescription={draft.description || ''}
        initialStatusId={draft.status_id}
        initialPriority={draft.priority}
        initialDueDate={draft.due_date || ''}
        initialAssigneeIds={draft.assignee_ids}
        initialTagIds={draft.existing_tag_ids}
        initialNewTags={draft.new_tag_names.join(', ')}
        {busy}
        {error}
        submitLabel="Create task"
        busyLabel="Creating…"
        cancelLabel="Back"
        on:cancel={backToPrompt}
        on:submit={(event) => save(event.detail)}
      />
    {/if}
  </div>
</div>

<style>
  .prompt-form { display: grid; gap: 1rem; }
  .prompt-form textarea { line-height: 1.5; }
  .modal-actions { position: sticky; bottom: -1.4rem; display: flex; justify-content: flex-end; gap: .7rem; border-top: 1px solid var(--line); background: var(--paper); margin: .4rem -1.4rem -1.4rem; padding: 1rem 1.4rem; }
  .modal-actions > button:not(.primary) { background: #fff; border: 1px solid #cbc8be; border-radius: .5rem; padding: .48rem .7rem; color: var(--ink); }
  code { overflow-wrap: anywhere; }
  @media (max-width: 760px) {
    .modal-actions { bottom: -1rem; margin: .4rem -1rem -1rem; padding: .8rem 1rem max(.8rem, env(safe-area-inset-bottom)); }
  }
</style>
