<script lang="ts">
  import { t, text, message, errorMessage, type Message } from '../lib/i18n';
  import { createEventDispatcher } from 'svelte';
  import { ApiError, api } from '../lib/api/client';
  import type { User } from '../lib/api/types';
  import AppButton from '../lib/components/AppButton.svelte';
  import PasswordField from '../lib/components/PasswordField.svelte';
  import TextField from '../lib/components/TextField.svelte';

  const dispatch = createEventDispatcher<{ authenticated: User }>();
  let email = '';
  let password = '';
  let error: Message = '';
  let showLockoutHint = false;
  let busy = false;

  async function submit() {
    busy = true;
    error = '';
    showLockoutHint = false;
    try {
      const user = await api.login(email, password);
      dispatch('authenticated', user);
    } catch (reason) {
      error = reason instanceof ApiError && reason.status === 429
        ? message('ui.login.tooManySignInAttemptsPleaseWaitAnd')
        : errorMessage(reason, 'ui.login.couldNotSignIn');
      showLockoutHint = reason instanceof ApiError && reason.status === 401;
    } finally {
      busy = false;
    }
  }
</script>

<main class="login-page">
  <section class="login-card">
    <div class="brand-mark">✓</div>
    <p class="eyebrow">{$t('ui.login.selfHostedTaskRanking')}</p>
    <h1>{$t('ui.app.nextTask')}</h1>
    <p class="muted">
      {$t('ui.login.signInToDecideWhatDeservesYourAttention')}
    </p>
    <form on:submit|preventDefault={submit}>
      <label>
        {$t('ui.login.email')}
        <TextField type="text" inputmode="email" bind:value={email} autocomplete="username" required />
      </label>
      <PasswordField
        id="account-password"
        label={$t('ui.acceptInvitation.password')}
        bind:value={password}
        autocomplete="current-password"
        required
      />
      <a class="forgot-password" href="#/forgot-password">{$t('ui.login.forgotPassword')}</a>
      {#if error}<p class="error" role="alert">{$text(error)}</p>{/if}
      {#if showLockoutHint}
        <p class="muted">{$t('ui.login.afterFiveUnsuccessfulAttemptsSignInMayPause')}</p>
      {/if}
      <AppButton type="submit" variant="primary" disabled={busy}>
        {busy ? $t('ui.login.signingIn') : $t('ui.login.signIn')}
      </AppButton>
    </form>
    <p class="muted">{$t('ui.login.accountsAreAvailableByInvitation')}</p>
  </section>
</main>

<style>
  .forgot-password { justify-self: end; font-size: .82rem; }
</style>
