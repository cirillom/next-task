<script lang="ts">
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
  let error = '';
  let notice = '';

  async function submit() {
    error = '';
    if (password !== confirmation) {
      error = 'Passwords do not match.';
      return;
    }
    busy = true;
    try {
      notice = (await api.acceptInvitation(token!, name, password)).message;
      password = confirmation = '';
      complete = true;
      history.replaceState(null, '', '#/');
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not create account';
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
      error = reason instanceof Error ? reason.message : 'Could not sign out';
      busy = false;
    }
  }
</script>

<svelte:head><meta name="referrer" content="no-referrer" /></svelte:head>

<main class="login-page">
  <section class="login-card">
    <div class="brand-mark">✓</div>
    <h1>{complete ? 'Your account is ready' : 'Welcome to Next Task'}</h1>
    {#if complete}
      <p class="notice" role="status">{notice}</p>
    {:else if !token || invalidLink}
      <p class="error" role="alert">{error || 'This invitation is invalid. Ask for a new invitation.'}</p>
    {:else if signedIn}
      <p class="muted">Sign out before creating your invited account.</p>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <AppButton variant="primary" disabled={busy} on:click={signOut}>Sign out to continue</AppButton>
    {:else}
      <p class="muted">Choose your name and password. Your account will use the email address that received this invitation.</p>
      <form on:submit|preventDefault={submit}>
        <label>Name<TextField bind:value={name} maxlength={160} autocomplete="name" required /></label>
        <PasswordField id="invite-password" label="Password" bind:value={password} minlength={10} maxlength={1024} autocomplete="new-password" required />
        <PasswordField id="invite-confirmation" label="Confirm password" bind:value={confirmation} minlength={10} maxlength={1024} autocomplete="new-password" required />
        {#if error}<p class="error" role="alert">{error}</p>{/if}
        <AppButton type="submit" variant="primary" disabled={busy}>{busy ? 'Creating account…' : 'Create account'}</AppButton>
      </form>
    {/if}
    <p><a href="/#/" on:click|preventDefault={() => reloadApp()}>Back to sign in</a></p>
  </section>
</main>
