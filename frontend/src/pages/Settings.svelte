<script lang="ts">
  import { api } from '../lib/api/client';
  import GeminiSettings from '../lib/components/GeminiSettings.svelte';
  import PomodoroSettings from '../lib/components/PomodoroSettings.svelte';
  import type { Status, User } from '../lib/api/types';
  import packageInfo from '../../package.json';
  import AppButton from '../lib/components/AppButton.svelte';
  import TextField from '../lib/components/TextField.svelte';
  import TextArea from '../lib/components/TextArea.svelte';
  import NumberField from '../lib/components/NumberField.svelte';
  import { onMount } from 'svelte';

  export let user: User;
  let currentPassword = '';
  let newPassword = '';
  let confirmation = '';
  let error = '';
  let notice = '';
  let formula = '';
  let statuses: Status[] = [];
  let statusName = '';
  let statusValue = 0;
  let workflowError = '';
  let workflowNotice = '';

  async function loadWorkflow() {
    try {
      const [settings, loadedStatuses] = await Promise.all([api.scoringSettings(), api.statuses()]);
      formula = settings.scoring_formula;
      statuses = loadedStatuses;
    } catch (reason) {
      workflowError = reason instanceof Error ? reason.message : 'Could not load workflow settings';
    }
  }

  async function saveFormula() {
    workflowError = workflowNotice = '';
    try {
      await api.updateScoringSettings(formula);
      workflowNotice = 'Scoring formula saved.';
    } catch (reason) {
      workflowError = reason instanceof Error ? reason.message : 'Could not save scoring formula';
    }
  }

  async function addStatus() {
    workflowError = workflowNotice = '';
    try {
      await api.createStatus(statusName, statusValue);
      statusName = '';
      statusValue = 0;
      await loadWorkflow();
    } catch (reason) {
      workflowError = reason instanceof Error ? reason.message : 'Could not create status';
    }
  }

  async function saveStatus(item: Status) {
    workflowError = workflowNotice = '';
    try {
      await api.updateStatus(item.id, { name: item.name, score_value: item.score_value });
      workflowNotice = 'Status saved.';
    } catch (reason) {
      workflowError = reason instanceof Error ? reason.message : 'Could not save status';
      await loadWorkflow();
    }
  }

  async function removeStatus(item: Status) {
    if (!window.confirm(`Delete status “${item.name}”?`)) return;
    workflowError = workflowNotice = '';
    try {
      await api.deleteStatus(item.id);
      await loadWorkflow();
    } catch (reason) {
      workflowError = reason instanceof Error ? reason.message : 'Could not delete status';
    }
  }

  onMount(loadWorkflow);

  async function changePassword() {
    error = '';
    notice = '';
    if (newPassword !== confirmation) {
      error = 'New passwords do not match.';
      return;
    }
    try {
      await api.changePassword(currentPassword, newPassword);
      currentPassword = newPassword = confirmation = '';
      notice = 'Password changed. Other sessions were signed out.';
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not change password';
    }
  }
</script>

<div class="page-heading"><div><p class="eyebrow">Your account</p><h1>Settings</h1></div></div>
<div class="settings-stack narrow">
  <section class="panel"><h2>Profile</h2><dl><div><dt>Name</dt><dd>{user.display_name}</dd></div><div><dt>Username / email</dt><dd>{user.email}</dd></div></dl></section>
  <section class="panel"><h2>Scoring</h2><form on:submit|preventDefault={saveFormula}><label>Scoring formula<TextArea className="code-input" bind:value={formula} rows="4" /></label><p class="help">Variables: priority, ageDays, idleDays, dueOffsetDays, hasDueDate, statusValue. Supports arithmetic, comparisons, exp(), and Python-style conditional expressions.</p><AppButton type="submit" variant="primary">Save scoring formula</AppButton></form></section>
  <section class="panel"><h2>Statuses</h2><div class="editable-list">{#each statuses as item}<div class="editable-row"><TextField bind:value={item.name} aria-label="Status name" /><NumberField step="any" bind:value={item.score_value} aria-label="Score value" /><AppButton on:click={() => saveStatus(item)}>Save</AppButton><AppButton variant="danger" on:click={() => removeStatus(item)}>Delete</AppButton></div>{/each}</div><form class="inline-control" on:submit|preventDefault={addStatus}><TextField bind:value={statusName} placeholder="New status" required /><NumberField step="any" bind:value={statusValue} aria-label="Score value" /><AppButton type="submit">Add status</AppButton></form>{#if workflowError}<p class="error" role="alert">{workflowError}</p>{/if}{#if workflowNotice}<p class="notice">{workflowNotice}</p>{/if}</section>
  <PomodoroSettings />
  <GeminiSettings />
  <section class="panel"><h2>Change password</h2><form on:submit|preventDefault={changePassword}><label>Current password<TextField type="password" bind:value={currentPassword} autocomplete="current-password" required /></label><label>New password<TextField type="password" bind:value={newPassword} minlength="10" autocomplete="new-password" required /></label><label>Confirm new password<TextField type="password" bind:value={confirmation} minlength="10" autocomplete="new-password" required /></label>{#if error}<p class="error">{error}</p>{/if}{#if notice}<p class="notice">{notice}</p>{/if}<AppButton type="submit" variant="primary">Change password</AppButton></form></section>
  <section class="panel"><h2>About</h2><p>Next Task calculates scores when you view your queue. Finished and blocked state remain independent from workflow status.</p><p class="muted">Offline mode caches this application shell only. Task data always comes from your server.</p><p class="muted">Next Task v{packageInfo.version}</p></section>
</div>
