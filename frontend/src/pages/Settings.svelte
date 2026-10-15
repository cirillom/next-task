<script lang="ts">
  import { api } from '../lib/api/client';
  import GeminiSettings from '../lib/components/GeminiSettings.svelte';
  import PomodoroSettings from '../lib/components/PomodoroSettings.svelte';
  import type { User } from '../lib/api/types';
  import packageInfo from '../../package.json';
  import AppButton from '../lib/components/AppButton.svelte';
  import TextField from '../lib/components/TextField.svelte';
  import TextArea from '../lib/components/TextArea.svelte';
  import { onMount } from 'svelte';

  export let user: User;
  let currentPassword = '';
  let newPassword = '';
  let confirmation = '';
  let error = '';
  let notice = '';
  let formula = '';
  let workflowError = '';
  let workflowNotice = '';

  async function loadWorkflow() {
    try {
      formula = (await api.scoringSettings()).scoring_formula;
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
  <section class="panel"><h2>Scoring</h2><form on:submit|preventDefault={saveFormula}><label>Scoring formula<TextArea className="code-input" bind:value={formula} rows="4" /></label><p class="help">Variables: priority, ageDays, idleDays, dueOffsetDays, hasDueDate, tagValue. Supports arithmetic, comparisons, exp(), and Python-style conditional expressions.</p><AppButton type="submit" variant="primary">Save scoring formula</AppButton></form>{#if workflowError}<p class="error" role="alert">{workflowError}</p>{/if}{#if workflowNotice}<p class="notice">{workflowNotice}</p>{/if}</section>
  <PomodoroSettings />
  <GeminiSettings />
  <section class="panel"><h2>Change password</h2><form on:submit|preventDefault={changePassword}><label>Current password<TextField type="password" bind:value={currentPassword} autocomplete="current-password" required /></label><label>New password<TextField type="password" bind:value={newPassword} minlength="10" autocomplete="new-password" required /></label><label>Confirm new password<TextField type="password" bind:value={confirmation} minlength="10" autocomplete="new-password" required /></label>{#if error}<p class="error">{error}</p>{/if}{#if notice}<p class="notice">{notice}</p>{/if}<AppButton type="submit" variant="primary">Change password</AppButton></form></section>
  <section class="panel"><h2>About</h2><p>Next Task calculates scores when you view your queue. Finished and blocked state are independent from tags.</p><p class="muted">Offline mode caches this application shell only. Task data always comes from your server.</p><p class="muted">Next Task v{packageInfo.version}</p></section>
</div>
