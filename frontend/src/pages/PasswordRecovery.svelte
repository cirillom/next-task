<script lang="ts">
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
  let error = '';
  let notice = '';

  async function submit() {
    error = notice = '';
    if (reset && password !== confirmation) {
      error = 'New passwords do not match.';
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
      error = reason instanceof Error ? reason.message : 'Could not reset password';
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
    <h1>{reset ? 'Choose a new password' : 'Forgot your password?'}</h1>
    {#if complete}
      <p class="notice" role="status">{notice}</p>
    {:else if reset && (!token || invalidLink)}
      <p class="error" role="alert">{error || 'This reset link is invalid. Request a new link.'}</p>
      <p><a href="#/forgot-password">Request a new reset link</a></p>
    {:else}
      <p class="muted">
        {reset
          ? 'Use at least 10 characters. All devices will be signed out after the reset.'
          : 'Enter the verified email for your account to request a reset link.'}
      </p>
      <form on:submit|preventDefault={submit}>
        {#if reset}
          <PasswordField id="reset-password" label="New password" bind:value={password} minlength={10} maxlength={1024} autocomplete="new-password" required />
          <PasswordField id="reset-confirmation" label="Confirm new password" bind:value={confirmation} minlength={10} maxlength={1024} autocomplete="new-password" required />
        {:else}
          <label>Email address<TextField type="email" bind:value={email} maxlength={320} autocomplete="email" required /></label>
        {/if}
        {#if error}<p class="error" role="alert">{error}</p>{/if}
        {#if notice}<p class="notice" role="status">{notice}</p>{/if}
        <AppButton type="submit" variant="primary" disabled={busy}>
          {busy ? (reset ? 'Saving…' : 'Sending…') : (reset ? 'Reset password' : 'Send reset link')}
        </AppButton>
      </form>
    {/if}
    <p class="back-link"><a href="/#/" on:click|preventDefault={() => reloadApp()}>Back to sign in</a></p>
  </section>
</main>

<style>
  .back-link { margin: 1.25rem 0 0; font-size: .85rem; }
</style>
