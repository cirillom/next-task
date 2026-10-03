<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { api } from '../api/client';
  import { geminiApi, type TextToTaskDraft } from '../api/gemini';
  import type { Task, TaskInput, Workspace } from '../api/types';
  import TaskForm from './TaskForm.svelte';
  import AppButton from './AppButton.svelte';
  import TextArea from './TextArea.svelte';

  export let workspace: Workspace;
  export let destinationChoices: Workspace[] = [workspace];
  const dispatch = createEventDispatcher<{ close: void; saved: Task }>();

  type Stage = 'capture' | 'review';
  type ReviewSource = 'expand' | 'gemini';

  let stage: Stage = 'capture';
  let reviewSource: ReviewSource = 'expand';
  let captureText = '';
  let proposal: TextToTaskDraft | null = null;
  let busy = false;
  let switchingWorkspace = false;
  let error = '';
  let form: TaskForm;
  let destinationId = destinationChoices.some((item) => item.id === workspace.id) ? workspace.id : destinationChoices[0]?.id ?? workspace.id;
  $: destination = destinationChoices.find((item) => item.id === destinationId) || destinationChoices[0] || workspace;

  async function changeWorkspace(event: Event) {
    const select = event.currentTarget as HTMLSelectElement;
    const target = destinationChoices.find((item) => item.id === Number(select.value));
    if (!target) return;
    if (stage === 'review') {
      if (!form) {
        select.value = String(destinationId);
        return;
      }
      switchingWorkspace = true;
      const changed = await form.switchWorkspace(target);
      switchingWorkspace = false;
      if (!changed) {
        select.value = String(destinationId);
        return;
      }
    }
    destinationId = target.id;
  }

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
      const saved = await api.createDraft({
        workspace_id: destination.id,
        title: parsed.title,
        description: parsed.description
      });
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
      proposal = await geminiApi.taskDraft(destination.id, captureText);
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
      const saved = await api.createTask({ ...input, workspace_id: destination.id });
      dispatch('saved', saved);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not create task';
    } finally {
      busy = false;
    }
  }

  async function saveDraft(input: TaskInput) {
    busy = true;
    error = '';
    try {
      const { priority: _priority, ...draftInput } = input;
      const saved = await api.createDraft({ ...draftInput, workspace_id: destination.id });
      dispatch('saved', saved);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not create draft';
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
      <div class="header-workspace">
        {#if destinationChoices.length > 1}
          <label>Workspace
            <select value={destinationId} disabled={busy || switchingWorkspace} on:change={changeWorkspace}>
              {#each destinationChoices as item (item.id)}<option value={item.id}>{item.name}</option>{/each}
            </select>
          </label>
        {:else}
          <span>Workspace</span><strong>{destination.name}</strong>
        {/if}
      </div>
      <button class="icon-button" aria-label="Close" title="Close" on:click={() => dispatch('close')}>×</button>
    </header>

    {#if stage === 'capture'}
      <div class="capture-body">
        <label class="capture-field">
          <span>What do you need to do?</span>
          <TextArea
            bind:value={captureText}
            rows="7"
            maxlength="12000"
            autofocus
            placeholder="Write a task, thought, or a few lines of context…"
          />
        </label>
        <p class="capture-hint">The first non-empty line becomes the title. Any lines after it become the description.</p>
        {#if error}<p class="error" role="alert">{error}</p>{/if}
        <footer class="capture-actions">
          <AppButton disabled={busy || !captureText.trim()} on:click={createDraft}>
            <span aria-hidden="true">✎</span> {busy ? 'Saving…' : 'Draft task'}
          </AppButton>
          <AppButton disabled={busy || !captureText.trim()} on:click={generate}>
            <span aria-hidden="true">✨</span> {busy ? 'Drafting…' : 'Text to task'}
          </AppButton>
          <AppButton variant="primary" disabled={busy || !captureText.trim()} on:click={expand}>
            <span aria-hidden="true">↗</span> Expand
          </AppButton>
        </footer>
      </div>
    {:else if proposal}
      {#if reviewSource === 'gemini'}
        <p class="notice">Gemini filled the task using <code>{proposal.model}</code>. Review anything you want before creating it.</p>
      {/if}
      <TaskForm
        bind:this={form}
        workspace={destination}
        initialTitle={proposal.title}
        initialDescription={proposal.description || ''}
        initialPriority={proposal.priority}
        initialDueDate={proposal.due_date || ''}
        initialAssigneeIds={proposal.assignee_ids}
        initialTagIds={proposal.existing_tag_ids}
        initialNewTags={proposal.new_tag_names.join(', ')}
        {busy}
        {error}
        submitLabel="Create task"
        busyLabel="Creating…"
        draftSubmitLabel="Save draft"
        cancelLabel="Back"
        on:cancel={backToCapture}
        on:draft={(event) => saveDraft(event.detail)}
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
    align-items: center;
    margin: -1.1rem -1.1rem .9rem;
    padding: .9rem 1.1rem .75rem;
  }

  .header-workspace { display: flex; align-items: center; gap: .5rem; margin-left: auto; font-size: .8rem; }
  .header-workspace label { display: flex; align-items: center; gap: .5rem; font-weight: 700; }
  .header-workspace strong { color: var(--forest-2); }
  .header-workspace select { max-width: 13rem; }

  .capture-body { display: grid; gap: .75rem; }
  .capture-field { display: grid; gap: .4rem; font-weight: 750; }
  .capture-field :global(.app-text-area) { min-height: 11rem; line-height: 1.55; }
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

  code { overflow-wrap: anywhere; }

  @media (max-width: 640px) {
    .quick-capture-modal { padding: .8rem; }
    .editor-header { top: -.8rem; margin: -.8rem -.8rem .75rem; padding: .75rem .8rem; }
    .header-workspace { min-width: 0; }
    .header-workspace select { max-width: 8rem; }
    .capture-actions { margin: .2rem -.8rem -.8rem; padding: .75rem .8rem max(.75rem, env(safe-area-inset-bottom)); }
    .capture-actions :global(.app-button) { flex: 1 1 auto; }
  }
</style>
