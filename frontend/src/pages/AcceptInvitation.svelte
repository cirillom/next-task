<script lang="ts">
  import { t, text, message, errorMessage, type Message } from '../lib/i18n';
  import { ApiError, api } from '../lib/api/client';
  import AppButton from '../lib/components/AppButton.svelte';
  import PasswordField from '../lib/components/PasswordField.svelte';
  import TextField from '../lib/components/TextField.svelte';
  import { reloadApp } from '../lib/navigation';

  export let token: string | null;
  export let signedIn: boolean;

  let name = '';
  let password = '';
  let confirmation = '';
  let busy = false;
  let complete = false;
  let invalidLink = false;
  let error: Message = '';
  let notice: Message = '';

  async function submit() {
    error = '';
    if (password !== confirmation) {
      error = message('ui.acceptInvitation.passwordsDoNotMatch');
      return;
    }
    busy = true;
    try {
      notice = (await api.acceptInvitation(token!, name, password)).message;
      password = confirmation = '';
      complete = true;
      history.replaceState(null, '', '#/');
    } catch (reason) {
      error = errorMessage(reason, 'ui.acceptInvitation.couldNotCreateAccount');
      invalidLink = reason instanceof ApiError && reason.status === 400;
    } finally {
      busy = false;
    }
  }

  async function signOut() {
    busy = true;
    try {
      await api.logout();
      reloadApp(location.href);
    } catch (reason) {
      error = errorMessage(reason, 'ui.acceptInvitation.couldNotSignOut');
      busy = false;
    }
  }
</script>

<svelte:head><meta name="referrer" content="no-referrer" /></svelte:head>

<main class="login-page">
  <section class="login-card">
    <div class="brand-mark">✓</div>
    <h1>{complete ? $t('ui.acceptInvitation.yourAccountIsReady') : $t('ui.acceptInvitation.welcomeToNextTask')}</h1>
    {#if complete}
      <p class="notice" role="status">{$text(notice)}</p>
    {:else if !token || invalidLink}
      <p class="error" role="alert">{$text(error) || $t('ui.acceptInvitation.thisInvitationIsInvalidAskForANew')}</p>
    {:else if signedIn}
      <p class="muted">{$t('ui.acceptInvitation.signOutBeforeCreatingYourInvitedAccount')}</p>
      {#if error}<p class="error" role="alert">{$text(error)}</p>{/if}
      <AppButton variant="primary" disabled={busy} on:click={signOut}>{$t('ui.acceptInvitation.signOutToContinue')}</AppButton>
    {:else}
      <p class="muted">{$t('ui.acceptInvitation.chooseYourNameAndPasswordYourAccountWill')}</p>
      <form on:submit|preventDefault={submit}>
        <label>{$t('ui.accountSettings.name')}<TextField bind:value={name} maxlength={160} autocomplete="name" required /></label>
        <PasswordField id="invite-password" label={$t('ui.acceptInvitation.password')} bind:value={password} minlength={10} maxlength={1024} autocomplete="new-password" required />
        <PasswordField id="invite-confirmation" label={$t('ui.acceptInvitation.confirmPassword')} bind:value={confirmation} minlength={10} maxlength={1024} autocomplete="new-password" required />
        {#if error}<p class="error" role="alert">{$text(error)}</p>{/if}
        <AppButton type="submit" variant="primary" disabled={busy}>{busy ? $t('ui.acceptInvitation.creatingAccount') : $t('ui.acceptInvitation.createAccount')}</AppButton>
      </form>
    {/if}
    <p><a href="/#/" on:click|preventDefault={() => reloadApp()}>{$t('ui.acceptInvitation.backToSignIn')}</a></p>
  </section>
</main>
