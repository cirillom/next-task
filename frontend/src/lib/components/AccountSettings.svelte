<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '../api/client';
  import type { EmailStatus, User } from '../api/types';
  import AppButton from './AppButton.svelte';
  import PasswordField from './PasswordField.svelte';
  import TextField from './TextField.svelte';

  export let user: User;
  let status: EmailStatus | null = null;
  let email = user.email;
  let password = '';
  let error = '';
  let busy = false;
  $: emailChanged = email.trim().toLowerCase() !== user.email.toLowerCase();
  $: emailVerified = status?.verified ?? false;

  onMount(async () => {
    try {
      status = await api.emailStatus();
      email = status.pending_email ?? user.email;
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load email status';
    }
  });

  async function sendVerification() {
    error = '';
    busy = true;
    try {
      status = await api.requestEmail(email, password);
      password = '';
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not send the verification email';
    } finally {
      busy = false;
    }
  }
</script>

<section class="panel account-panel">
  <div class="account-heading">
    <div><p class="eyebrow">Your account</p><h2>Profile and email</h2></div>
    {#if status}
      <span class:verified={emailVerified} class="email-status">
        {emailVerified ? 'Email verified' : 'Email not verified'}
      </span>
    {/if}
  </div>
  <div class="profile-name"><span>Name</span><strong>{user.display_name}</strong></div>
  {#if status?.pending_email}
    <div class="pending-email" role="status">
      <strong>Check your inbox</strong>
      <span>A verification link was sent to {status.pending_email}. It expires in 24 hours.{status.pending_email !== user.email ? ' Your current email stays active until you confirm the new one.' : ''}</span>
    </div>
  {/if}
  <form novalidate on:submit|preventDefault={sendVerification}>
    <label>Email address<TextField type="email" inputmode="email" bind:value={email} autocomplete="email" required /></label>
    <p class="email-help">
      {#if emailChanged}
        We’ll send a link to this address. It becomes your sign-in email after verification.
      {:else if emailVerified}
        This is your verified sign-in email. Enter a new address above to change it.
      {:else}
        Verify this address to use it for future account recovery.
      {/if}
    </p>
    <PasswordField id="email-current-password" label="Current password" bind:value={password} autocomplete="current-password" required />
    {#if error}<p class="error" role="alert">{error}</p>{/if}
    <AppButton type="submit" variant="primary" disabled={busy || (!emailChanged && emailVerified)}>{busy ? 'Sending…' : emailChanged ? 'Send change link' : 'Verify email'}</AppButton>
  </form>
</section>

<style>
  .account-panel { padding: clamp(1.25rem, 3vw, 1.8rem); }
  .account-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; margin-bottom: 1.1rem; }
  .account-heading .eyebrow { margin-bottom: .35rem; }
  .account-heading h2 { margin-bottom: 0; font-size: 1.35rem; }
  .email-status { flex: none; border-radius: 99px; padding: .35rem .7rem; background: #f4e8d1; color: #765419; font-size: .75rem; font-weight: 700; }
  .email-status.verified { background: #e2f0e8; color: #21563d; }
  .profile-name { display: flex; gap: 1rem; padding: .85rem 0 1.1rem; margin-bottom: 1.2rem; border-bottom: 1px solid var(--line); }
  .profile-name span { min-width: 8rem; color: var(--muted); }
  .pending-email { display: grid; gap: .25rem; padding: .85rem 1rem; margin-bottom: 1.25rem; border: 1px solid #e6d3ab; border-radius: .65rem; background: #fbf5e8; font-size: .84rem; line-height: 1.5; }
  .email-help { margin: -.55rem 0 0; color: var(--muted); font-size: .8rem; line-height: 1.5; }
  .account-panel form { gap: .9rem; }
  .account-panel form :global(.app-button) { justify-self: start; }
  @media (max-width: 520px) {
    .account-heading { flex-direction: column; }
    .profile-name { display: grid; gap: .25rem; }
  }
</style>
