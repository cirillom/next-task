<script lang="ts">
  import { api } from '../lib/api/client';
  import ChatGPTSettings from '../lib/components/ChatGPTSettings.svelte';
  import GeminiSettings from '../lib/components/GeminiSettings.svelte';
  import PomodoroSettings from '../lib/components/PomodoroSettings.svelte';
  import type { User } from '../lib/api/types';

  export let user: User;
  let currentPassword = '';
  let newPassword = '';
  let confirmation = '';
  let error = '';
  let notice = '';

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
  <PomodoroSettings />
  <ChatGPTSettings />
  <GeminiSettings />
  <section class="panel"><h2>Change password</h2><form on:submit|preventDefault={changePassword}><label>Current password<input type="password" bind:value={currentPassword} autocomplete="current-password" required /></label><label>New password<input type="password" bind:value={newPassword} minlength="10" autocomplete="new-password" required /></label><label>Confirm new password<input type="password" bind:value={confirmation} minlength="10" autocomplete="new-password" required /></label>{#if error}<p class="error">{error}</p>{/if}{#if notice}<p class="notice">{notice}</p>{/if}<button class="primary">Change password</button></form></section>
  <section class="panel"><h2>About</h2><p>Next Task calculates scores when you view your queue. Finished and blocked state remain independent from workflow status.</p><p class="muted">Offline mode caches this application shell only. Task data always comes from your server.</p></section>
</div>