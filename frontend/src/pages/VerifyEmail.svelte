<script lang="ts">
  import { t, text, errorMessage, type Message } from '../lib/i18n';
  import { api } from '../lib/api/client';
  import AppButton from '../lib/components/AppButton.svelte';
  import { reloadApp } from '../lib/navigation';

  export let token: string | null;
  export let signedIn: boolean;

  let busy = false;
  let verified = false;
  let error: Message = '';

  async function verify() {
    if (!token) return;
    busy = true;
    error = '';
    try {
      await api.verifyEmail(token);
      verified = true;
      history.replaceState(null, '', signedIn ? '#/settings' : '#/');
    } catch (reason) {
      error = errorMessage(reason, 'ui.verifyEmail.couldNotVerifyThisEmail');
    } finally {
      busy = false;
    }
  }
</script>

<main class="login-page">
  <section class="login-card">
    <div class="brand-mark">✓</div>
    <h1>{$t('ui.verifyEmail.verifyYourEmail')}</h1>
    {#if verified}
      <p>{$t('ui.verifyEmail.yourEmailIsVerifiedYouCanUseIt')}</p>
      <a href={signedIn ? '/#/settings' : '/#/'} on:click|preventDefault={() => reloadApp(signedIn ? '/#/settings' : '/#/')}>{$t('ui.verifyEmail.continueToNextTask')}</a>
    {:else if !token}
      <p class="error" role="alert">{$t('ui.verifyEmail.thisVerificationLinkIsInvalid')}</p>
    {:else}
      <p>{$t('ui.verifyEmail.confirmThisAddressForYourNextTaskAccount')}</p>
      {#if error}<p class="error" role="alert">{$text(error)}</p>{/if}
      <AppButton variant="primary" disabled={busy} on:click={verify}>
        {busy ? $t('ui.verifyEmail.verifying') : $t('ui.accountSettings.verifyEmail')}
      </AppButton>
    {/if}
  </section>
</main>
