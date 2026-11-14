<script lang="ts">
  import { t, text, message, errorMessage, type Message } from '../lib/i18n';
  import { ApiError, api } from '../lib/api/client';
  import AppButton from '../lib/components/AppButton.svelte';
  import PasswordField from '../lib/components/PasswordField.svelte';
  import TextField from '../lib/components/TextField.svelte';
  import { reloadApp } from '../lib/navigation';

  export let reset: boolean;
  export let token: string | null;

  let email = '';
  let password = '';
  let confirmation = '';
  let busy = false;
  let complete = false;
  let invalidLink = false;
  let error: Message = '';
  let notice: Message = '';

  async function submit() {
    error = notice = '';
    if (reset && password !== confirmation) {
      error = message('ui.passwordRecovery.newPasswordsDoNotMatch');
      return;
    }
    busy = true;
    try {
      const result = reset
        ? await api.resetPassword(token!, password)
        : await api.requestPasswordReset(email);
      notice = result.message;
      if (reset) {
        password = confirmation = '';
        complete = true;
        history.replaceState(null, '', '#/');
      }
    } catch (reason) {
      error = errorMessage(reason, 'ui.passwordRecovery.couldNotResetPassword');
      invalidLink = reset && reason instanceof ApiError && reason.status === 400;
    } finally {
      busy = false;
    }
  }
</script>

<svelte:head><meta name="referrer" content="no-referrer" /></svelte:head>

<main class="login-page">
  <section class="login-card">
    <div class="brand-mark">✓</div>
    <h1>{reset ? $t('ui.passwordRecovery.chooseANewPassword') : $t('ui.passwordRecovery.forgotYourPassword')}</h1>
    {#if complete}
      <p class="notice" role="status">{$text(notice)}</p>
    {:else if reset && (!token || invalidLink)}
      <p class="error" role="alert">{$text(error) || $t('ui.passwordRecovery.thisResetLinkIsInvalidRequestANew')}</p>
      <p><a href="#/forgot-password">{$t('ui.passwordRecovery.requestANewResetLink')}</a></p>
    {:else}
      <p class="muted">
        {reset
          ? $t('ui.passwordRecovery.useAtLeast10CharactersAllDevicesWill')
          : $t('ui.passwordRecovery.enterTheVerifiedEmailForYourAccountTo')}
      </p>
      <form on:submit|preventDefault={submit}>
        {#if reset}
          <PasswordField id="reset-password" label={$t('ui.passwordRecovery.newPassword')} bind:value={password} minlength={10} maxlength={1024} autocomplete="new-password" required />
          <PasswordField id="reset-confirmation" label={$t('ui.passwordRecovery.confirmNewPassword')} bind:value={confirmation} minlength={10} maxlength={1024} autocomplete="new-password" required />
        {:else}
          <label>{$t('ui.accountSettings.emailAddress')}<TextField type="email" bind:value={email} maxlength={320} autocomplete="email" required /></label>
        {/if}
        {#if error}<p class="error" role="alert">{$text(error)}</p>{/if}
        {#if notice}<p class="notice" role="status">{$text(notice)}</p>{/if}
        <AppButton type="submit" variant="primary" disabled={busy}>
          {busy ? (reset ? $t('ui.geminiSettings.saving') : $t('ui.accountSettings.sending')) : (reset ? $t('ui.passwordRecovery.resetPassword') : $t('ui.passwordRecovery.sendResetLink'))}
        </AppButton>
      </form>
    {/if}
    <p class="back-link"><a href="/#/" on:click|preventDefault={() => reloadApp()}>{$t('ui.acceptInvitation.backToSignIn')}</a></p>
  </section>
</main>

<style>
  .back-link { margin: 1.25rem 0 0; font-size: .85rem; }
</style>
