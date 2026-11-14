<script lang="ts">
  import { t, text, errorMessage, type Message } from '../i18n';
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
  let error: Message = '';
  let busy = false;
  $: emailChanged = email.trim().toLowerCase() !== user.email.toLowerCase();
  $: emailVerified = status?.verified ?? false;

  onMount(async () => {
    try {
      status = await api.emailStatus();
      email = status.pending_email ?? user.email;
    } catch (reason) {
      error = errorMessage(reason, 'ui.accountSettings.couldNotLoadEmailStatus');
    }
  });

  async function sendVerification() {
    error = '';
    busy = true;
    try {
      status = await api.requestEmail(email, password);
      password = '';
    } catch (reason) {
      error = errorMessage(reason, 'ui.accountSettings.couldNotSendTheVerificationEmail');
    } finally {
      busy = false;
    }
  }
</script>

<section class="panel account-panel">
  <div class="account-heading">
    <div><p class="eyebrow">{$t('ui.accountSettings.yourAccount')}</p><h2>{$t('ui.accountSettings.profileAndEmail')}</h2></div>
    {#if status}
      <span class:verified={emailVerified} class="email-status">
        {emailVerified ? $t('ui.accountSettings.emailVerified') : $t('ui.accountSettings.emailNotVerified')}
      </span>
    {/if}
  </div>
  <div class="profile-name"><span>{$t('ui.accountSettings.name')}</span><strong>{user.display_name}</strong></div>
  {#if status?.pending_email}
    <div class="pending-email" role="status">
      <strong>{$t('ui.accountSettings.checkYourInbox')}</strong>
      <span>{$t('ui.accountSettings.verificationPending', {email: status.pending_email, changed: status.pending_email !== user.email ? "yes" : "no"})}</span>
    </div>
  {/if}
  <form novalidate on:submit|preventDefault={sendVerification}>
    <label>{$t('ui.accountSettings.emailAddress')}<TextField type="email" inputmode="email" bind:value={email} autocomplete="email" required /></label>
    <p class="email-help">
      {#if emailChanged}
        {$t('ui.accountSettings.weLlSendALinkToThisAddress')}
      {:else if emailVerified}
        {$t('ui.accountSettings.thisIsYourVerifiedSignInEmailEnter')}
      {:else}
        {$t('ui.accountSettings.verifyThisAddressToUseItForFuture')}
      {/if}
    </p>
    <PasswordField id="email-current-password" label={$t('ui.accountSettings.currentPassword')} bind:value={password} autocomplete="current-password" required />
    {#if error}<p class="error" role="alert">{$text(error)}</p>{/if}
    <AppButton type="submit" variant="primary" disabled={busy || (!emailChanged && emailVerified)}>{busy ? $t('ui.accountSettings.sending') : emailChanged ? $t('ui.accountSettings.sendChangeLink') : $t('ui.accountSettings.verifyEmail')}</AppButton>
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
