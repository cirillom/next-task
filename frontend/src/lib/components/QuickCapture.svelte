<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { api } from '../api/client';
  import { geminiApi, type TextToTaskDraft } from '../api/gemini';
  import type { Task, TaskInput, Workspace } from '../api/types';
  import TaskForm from './TaskForm.svelte';

  export let workspace: Workspace;
  const dispatch = createEventDispatcher<{ close: void; saved: Task }>();

  type Stage = 'capture' | 'review';
  type ReviewSource = 'expand' | 'gemini';

  let stage: Stage = 'capture';
  let reviewSource: ReviewSource = 'expand';
  let captureText = '';
  let proposal: TextToTaskDraft | null = null;
  let busy = false;
  let error = '';

  function parsedCapture(): { title: string; description: string | null } | null {
    const lines = captureText.split('\n');
    const first = lines.findIndex((line) => line.trim().length > 0);
    if (first < 0) return null;
    const title = lines[first].trim();
    const description = lines.slice(first + 1).join('\n').trim();
    return { title, description: description || null };
  }

  function manualProposal(): TextToTaskDraft | null {
    const parsed = parsedCapture();
    if (!parsed) return null;
    return {
      title: parsed.title,
      description: parsed.description,
      status_id: 0,
      priority: 1,
      due_date: null,
      assignee_ids: [],
      existing_tag_ids: [],
      new_tag_names: [],
      model: ''
    };
  }

  async function createDraft() {
    const parsed = parsedCapture();
    if (!parsed) return;
    busy = true;
    error = '';
    try {
      const saved = await api.createDraft(workspace.id, parsed.title, parsed.description);
      dispatch('saved', saved);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not create draft';
    } finally {
      busy = false;
    }
  }

  async function generate() {
    if (!captureText.trim()) return;
    busy = true;
    error = '';
    try {
      proposal = await geminiApi.taskDraft(workspace.id, captureText);
      reviewSource = 'gemini';
      stage = 'review';
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not turn this text into a task';
    } finally {
      busy = false;
    }
  }

  function expand() {
    proposal = manualProposal();
    if (!proposal) return;
    reviewSource = 'expand';
    error = '';
    stage = 'review';
  }

  async function save(input: TaskInput) {
    busy = true;
    error = '';
    try {
      const saved = await api.createTask({ ...input, workspace_id: workspace.id });
      dispatch('saved', saved);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not create task';
    } finally {
      busy = false;
    }
  }

  function backToCapture() {
    stage = 'capture';
    error = '';
  }
</script>

<div class="modal-backdrop" role="presentation" on:click|self={() => dispatch('close')}>
  <div class:expanded={stage === 'review'} class="task-editor quick-capture-modal" role="dialog" aria-modal="true" aria-labelledby="quick-capture-title">
    <header class="editor-header">
      <div>
        <p class="eyebrow">{stage === 'capture' ? 'Quick capture' : reviewSource === 'gemini' ? 'Review Gemini suggestion' : 'Task details'}</p>
        <h1 id="quick-capture-title">New task</h1>
      </div>
      <button class="icon-button" aria-label="Close" title="Close" on:click={() => dispatch('close')}>×</button>
    </header>

    {#if stage === 'capture'}
      <div class="capture-body">
        <label class="capture-field">
          <span>What do you need to do?</span>
          <textarea
            bind:value={captureText}
            rows="7"
            maxlength="12000"
            autofocus
            placeholder="Write a task, thought, or a few lines of context…"
          ></textarea>
        </label>
        <p class="capture-hint">The first non-empty line becomes the title. Any lines after it become the description.</p>
        {#if error}<p class="error" role="alert">{error}</p>{/if}
        <footer class="capture-actions">
          <button type="button" disabled={busy || !captureText.trim()} on:click={createDraft}>
            <span aria-hidden="true">✎</span> {busy ? 'Saving…' : 'Draft task'}
          </button>
          <button type="button" disabled={busy || !captureText.trim()} on:click={generate}>
            <span aria-hidden="true">✨</span> {busy ? 'Drafting…' : 'Text to task'}
          </button>
          <button type="button" class="primary" disabled={busy || !captureText.trim()} on:click={expand}>
            <span aria-hidden="true">↗</span> Expand
          </button>
        </footer>
      </div>
    {:else if proposal}
      {#if reviewSource === 'gemini'}
        <p class="notice">Gemini filled the task using <code>{proposal.model}</code>. Review anything you want before creating it.</p>
      {/if}
      <TaskForm
        {workspace}
        initialTitle={proposal.title}
        initialDescription={proposal.description || ''}
        initialStatusId={proposal.status_id}
        initialPriority={proposal.priority}
        initialDueDate={proposal.due_date || ''}
        initialAssigneeIds={proposal.assignee_ids}
        initialTagIds={proposal.existing_tag_ids}
        initialNewTags={proposal.new_tag_names.join(', ')}
        {busy}
        {error}
        submitLabel="Create task"
        busyLabel="Creating…"
        cancelLabel="Back"
        on:cancel={backToCapture}
        on:submit={(event) => save(event.detail)}
      />
    {/if}
  </div>
</div>

<style>
  .quick-capture-modal {
    width: min(100%, 38rem);
    padding: 1.1rem;
  }

  .quick-capture-modal.expanded { width: min(100%, 60rem); }

  .editor-header {
    top: -1.1rem;
    margin: -1.1rem -1.1rem .9rem;
    padding: .9rem 1.1rem .75rem;
  }

  .capture-body { display: grid; gap: .75rem; }
  .capture-field { display: grid; gap: .4rem; font-weight: 750; }
  .capture-field textarea { min-height: 11rem; resize: vertical; line-height: 1.55; font: inherit; }
  .capture-hint { margin: -.2rem 0 0; color: var(--muted); font-size: .78rem; }

  .capture-actions {
    display: flex;
    justify-content: flex-end;
    flex-wrap: wrap;
    gap: .55rem;
    border-top: 1px solid var(--line);
    margin: .25rem -1.1rem -1.1rem;
    padding: .85rem 1.1rem 1rem;
    background: var(--paper);
  }

  .capture-actions button {
    display: inline-flex;
    align-items: center;
    gap: .35rem;
    border: 1px solid #cbc8be;
    border-radius: .5rem;
    background: #fff;
    padding: .5rem .72rem;
    color: var(--ink);
    font-weight: 700;
  }

  .capture-actions button.primary { border-color: var(--forest); background: var(--forest); color: #fff; }
  code { overflow-wrap: anywhere; }

  @media (max-width: 640px) {
    .quick-capture-modal { padding: .8rem; }
    .editor-header { top: -.8rem; margin: -.8rem -.8rem .75rem; padding: .75rem .8rem; }
    .capture-actions { margin: .2rem -.8rem -.8rem; padding: .75rem .8rem max(.75rem, env(safe-area-inset-bottom)); }
    .capture-actions button { flex: 1 1 auto; justify-content: center; }
  }
</style>
