<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { ApiError, api } from '../api/client';
  import { geminiApi, type TextToTaskDraft } from '../api/gemini';
  import type { Member, Status, Tag, Task, Workspace } from '../api/types';

  export let workspace: Workspace;
  const dispatch = createEventDispatcher<{ close: void; saved: Task }>();

  let stage: 'prompt' | 'review' = 'prompt';
  let requestText = '';
  let statuses: Status[] = [];
  let tags: Tag[] = [];
  let members: Member[] = [];
  let title = '';
  let description = '';
  let statusId = 0;
  let priority = 1;
  let dueDate = '';
  let assigneeIds: number[] = [];
  let tagIds: number[] = [];
  let newTags = '';
  let model = '';
  let loading = true;
  let busy = false;
  let error = '';

  onMount(async () => {
    try {
      [statuses, tags, members] = await Promise.all([
        api.statuses(workspace.id),
        api.tags(workspace.id),
        api.members(workspace.id)
      ]);
      statusId = statuses[0]?.id || 0;
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load workspace options';
    } finally {
      loading = false;
    }
  });

  function applyDraft(draft: TextToTaskDraft) {
    title = draft.title;
    description = draft.description || '';
    statusId = statuses.some((item) => item.id === draft.status_id)
      ? draft.status_id
      : statuses[0]?.id || 0;
    priority = draft.priority;
    dueDate = draft.due_date || '';
    assigneeIds = draft.assignee_ids;
    tagIds = draft.existing_tag_ids;
    newTags = draft.new_tag_names.join(', ');
    model = draft.model;
    stage = 'review';
  }

  async function generate() {
    busy = true;
    error = '';
    try {
      applyDraft(await geminiApi.taskDraft(workspace.id, requestText));
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not create a task draft';
    } finally {
      busy = false;
    }
  }

  function normalizedNewTags(): string[] {
    const values = newTags
      .split(/[\n,]+/)
      .map((value) => value.trim().replace(/^#/, '').trim().toLowerCase())
      .filter(Boolean);
    return [...new Set(values)];
  }

  async function resolveTagIds(): Promise<number[]> {
    const resolved = new Set(tagIds);
    for (const name of normalizedNewTags()) {
      const existing = tags.find((tag) => tag.name.toLowerCase() === name);
      if (existing) {
        resolved.add(existing.id);
        continue;
      }
      try {
        const created = await api.createTag(workspace.id, { name });
        tags = [...tags, created];
        resolved.add(created.id);
      } catch (reason) {
        if (!(reason instanceof ApiError) || reason.status !== 409) throw reason;
        tags = await api.tags(workspace.id);
        const concurrent = tags.find((tag) => tag.name.toLowerCase() === name);
        if (!concurrent) throw reason;
        resolved.add(concurrent.id);
      }
    }
    return [...resolved];
  }

  async function save() {
    busy = true;
    error = '';
    try {
      const saved = await api.createTask({
        workspace_id: workspace.id,
        title,
        description: description || null,
        status_id: statusId,
        priority,
        due_date: dueDate || null,
        last_worked_at: null,
        parent_task_id: null,
        assignee_ids: assigneeIds,
        tag_ids: await resolveTagIds()
      });
      dispatch('saved', saved);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not save task';
    } finally {
      busy = false;
    }
  }
</script>

<div class="modal-backdrop" role="presentation" on:click|self={() => dispatch('close')}>
  <div class="text-task-modal" role="dialog" aria-modal="true" aria-labelledby="text-task-title">
    <header class="editor-header">
      <div>
        <p class="eyebrow">{stage === 'prompt' ? 'Gemini Flash' : 'Review before creating'}</p>
        <h1 id="text-task-title">{stage === 'prompt' ? 'Text to task' : 'Edit task draft'}</h1>
      </div>
      <button class="icon-button" aria-label="Close" on:click={() => dispatch('close')}>×</button>
    </header>

    {#if loading}
      <p class="empty">Loading {workspace.name}…</p>
    {:else if stage === 'prompt'}
      <form on:submit|preventDefault={generate}>
        <p class="muted">Describe one task for <strong>{workspace.name}</strong>. Include dates, urgency, assignees, or useful context naturally.</p>
        <label>
          What needs to be done?
          <textarea bind:value={requestText} rows="9" maxlength="12000" required placeholder="Example: Ask Marina to review the release notes by Friday. This is urgent and belongs to the website launch."></textarea>
        </label>
        {#if error}<p class="error" role="alert">{error}</p>{/if}
        <footer class="modal-actions">
          <button type="button" on:click={() => dispatch('close')}>Cancel</button>
          <button class="primary" disabled={busy || !requestText.trim() || !statusId}>{busy ? 'Drafting…' : 'Create draft'}</button>
        </footer>
      </form>
    {:else}
      <form on:submit|preventDefault={save}>
        <p class="notice">Gemini suggested this draft using <code>{model}</code>. Review every field before creating it.</p>
        <div class="form-grid">
          <label class="wide">Title<input bind:value={title} maxlength="500" required /></label>
          <label>Status<select bind:value={statusId}>{#each statuses as item}<option value={item.id}>{item.name}</option>{/each}</select></label>
          <label>Priority<input type="number" bind:value={priority} min="1" max="5" required /></label>
          <label>Due date<input type="date" bind:value={dueDate} /></label>
          <label class="wide">Description (Markdown)<textarea bind:value={description} rows="8" placeholder="Details, links, lists, or acceptance criteria…"></textarea></label>
        </div>
        <fieldset><legend>Assignees</legend><div class="choice-grid">{#each members as member}<label><input type="checkbox" value={member.user_id} bind:group={assigneeIds} /> {member.display_name}</label>{/each}</div></fieldset>
        <fieldset><legend>Existing direct tags</legend><div class="choice-grid">{#each tags as tag}<label><input type="checkbox" value={tag.id} bind:group={tagIds} /> #{tag.name}</label>{/each}</div></fieldset>
        <label>Suggested new tags<input bind:value={newTags} placeholder="ai, planning, errands" /><span class="help">Comma-separated. Edit or remove any suggestion; new tags are created with the task.</span></label>
        {#if error}<p class="error" role="alert">{error}</p>{/if}
        <footer class="modal-actions">
          <button type="button" disabled={busy} on:click={() => { stage = 'prompt'; error = ''; }}>Back</button>
          <button class="primary" disabled={busy || !title.trim() || !statusId}>{busy ? 'Creating…' : 'Create task'}</button>
        </footer>
      </form>
    {/if}
  </div>
</div>

<style>
  .text-task-modal { width: min(100%, 54rem); max-height: calc(100vh - 2rem); overflow: auto; border-radius: 1rem; background: var(--paper); padding: 1.4rem; box-shadow: 0 30px 90px rgba(0, 0, 0, .3); }
  .text-task-modal form { display: grid; gap: 1rem; }
  .text-task-modal textarea { line-height: 1.5; }
  .modal-actions { position: sticky; bottom: -1.4rem; display: flex; justify-content: flex-end; gap: .7rem; border-top: 1px solid var(--line); background: var(--paper); margin: .4rem -1.4rem -1.4rem; padding: 1rem 1.4rem; }
  .modal-actions > button:not(.primary) { background: #fff; border: 1px solid #cbc8be; border-radius: .5rem; padding: .48rem .7rem; color: var(--ink); }
  code { overflow-wrap: anywhere; }
  @media (max-width: 760px) {
    .text-task-modal { width: 100%; max-height: 100vh; border-radius: 0; padding: 1rem; }
    .modal-actions { bottom: -1rem; margin: .4rem -1rem -1rem; padding: .8rem 1rem max(.8rem, env(safe-area-inset-bottom)); }
  }
</style>
