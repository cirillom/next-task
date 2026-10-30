<script lang="ts">
  import { api } from '../lib/api/client';
  import GeminiSettings from '../lib/components/GeminiSettings.svelte';
  import PomodoroSettings from '../lib/components/PomodoroSettings.svelte';
  import type { ContactEmailStatus, User } from '../lib/api/types';
  import packageInfo from '../../package.json';
  import AppButton from '../lib/components/AppButton.svelte';
  import PasswordField from '../lib/components/PasswordField.svelte';
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
  let contactStatus: ContactEmailStatus | null = null;
  let contactEmail = '';
  let contactPassword = '';
  let contactError = '';
  let contactNotice = '';
  let contactBusy = false;

  async function loadContactEmail() {
    try {
      contactStatus = await api.contactEmail();
      contactEmail = contactStatus.pending_email ?? contactStatus.verified_email ?? '';
    } catch (reason) {
      contactError = reason instanceof Error ? reason.message : 'Could not load contact email';
    }
  }

  async function requestContactEmail() {
    contactError = contactNotice = '';
    contactBusy = true;
    try {
      contactStatus = await api.requestContactEmail(contactEmail, contactPassword);
      contactPassword = '';
      contactNotice = contactStatus.pending_email
        ? 'Verification email sent. Open the link within 24 hours.'
        : 'Your verified contact email is unchanged.';
    } catch (reason) {
      contactError = reason instanceof Error ? reason.message : 'Could not send verification email';
    } finally {
      contactBusy = false;
    }
  }

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

  onMount(() => { void loadWorkflow(); void loadContactEmail(); });

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
  <section class="panel">
    <h2>Contact email</h2>
    <p class="help">Your login identifier stays the same. Only a verified contact email can be used for account recovery later.</p>
    {#if contactStatus}
      <p>Verified: <strong>{contactStatus.verified_email ?? 'None'}</strong></p>
      {#if contactStatus.pending_email}
        <p>Waiting for verification: <strong>{contactStatus.pending_email}</strong></p>
      {/if}
    {/if}
    <form on:submit|preventDefault={requestContactEmail}>
      <label>Contact email<TextField type="email" bind:value={contactEmail} autocomplete="email" required /></label>
      <PasswordField id="contact-current-password" label="Current password" bind:value={contactPassword} autocomplete="current-password" required />
      {#if contactError}<p class="error" role="alert">{contactError}</p>{/if}
      {#if contactNotice}<p class="notice" role="status">{contactNotice}</p>{/if}
      <AppButton type="submit" variant="primary" disabled={contactBusy}>{contactBusy ? 'Sending…' : 'Send verification email'}</AppButton>
    </form>
  </section>
  <section class="panel"><h2>Scoring</h2><form on:submit|preventDefault={saveFormula}><label>Scoring formula<TextArea className="code-input" bind:value={formula} rows="4" /></label><p class="help">Variables: priority, ageDays, idleDays, dueOffsetDays, hasDueDate, tagValue. Supports arithmetic, comparisons, exp(), and Python-style conditional expressions.</p><AppButton type="submit" variant="primary">Save scoring formula</AppButton></form>{#if workflowError}<p class="error" role="alert">{workflowError}</p>{/if}{#if workflowNotice}<p class="notice">{workflowNotice}</p>{/if}</section>
  <PomodoroSettings />
  <GeminiSettings />
  <section class="panel">
    <h2>Change password</h2>
    <form on:submit|preventDefault={changePassword}>
      <PasswordField id="current-password" label="Current password" bind:value={currentPassword} autocomplete="current-password" required />
      <PasswordField id="new-password" label="New password" bind:value={newPassword} minlength={10} autocomplete="new-password" required />
      <PasswordField id="confirm-new-password" label="Confirm new password" bind:value={confirmation} minlength={10} autocomplete="new-password" required />
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      {#if notice}<p class="notice">{notice}</p>{/if}
      <AppButton type="submit" variant="primary">Change password</AppButton>
    </form>
  </section>
  <section class="panel"><h2>About</h2><p>Next Task calculates scores when you view your queue. Finished and blocked state are independent from tags.</p><p class="muted">Offline mode caches this application shell only. Task data always comes from your server.</p><p class="muted">Next Task v{packageInfo.version}</p></section>
</div>
