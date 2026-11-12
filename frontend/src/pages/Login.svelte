<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { ApiError, api } from '../lib/api/client';
  import type { User } from '../lib/api/types';
  import AppButton from '../lib/components/AppButton.svelte';
  import PasswordField from '../lib/components/PasswordField.svelte';
  import TextField from '../lib/components/TextField.svelte';

  const dispatch = createEventDispatcher<{ authenticated: User }>();
  let email = '';
  let password = '';
  let error = '';
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
        ? 'Too many sign-in attempts. Please wait and try again.'
        : reason instanceof Error ? reason.message : 'Could not sign in';
      showLockoutHint = reason instanceof ApiError && reason.status === 401;
    } finally {
      busy = false;
    }
  }
</script>

<main class="login-page">
  <section class="login-card">
    <div class="brand-mark">✓</div>
    <p class="eyebrow">Self-hosted task ranking</p>
    <h1>Next Task</h1>
    <p class="muted">
      Sign in to decide what deserves your attention next.
    </p>
    <form on:submit|preventDefault={submit}>
      <label>
        Email
        <TextField type="text" inputmode="email" bind:value={email} autocomplete="username" required />
      </label>
      <PasswordField
        id="account-password"
        label="Password"
        bind:value={password}
        autocomplete="current-password"
        required
      />
      <a class="forgot-password" href="#/forgot-password">Forgot password?</a>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      {#if showLockoutHint}
        <p class="muted">After five unsuccessful attempts, sign-in may pause for 15 minutes. If your password is correct, wait before trying again.</p>
      {/if}
      <AppButton type="submit" variant="primary" disabled={busy}>
        {busy ? 'Signing in…' : 'Sign in'}
      </AppButton>
    </form>
    <p class="muted">Accounts are available by invitation.</p>
  </section>
</main>

<style>
  .forgot-password { justify-self: end; font-size: .82rem; }
</style>
