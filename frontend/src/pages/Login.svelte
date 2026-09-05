<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { api } from '../lib/api/client';
  import type { User } from '../lib/api/types';

  const dispatch = createEventDispatcher<{ authenticated: User }>();
  let mode: 'login' | 'signup' = 'login';
  let identifier = '';
  let password = '';
  let error = '';
  let busy = false;

  async function submit() {
    busy = true;
    error = '';
    try {
      const user = mode === 'signup'
        ? await api.signup(identifier, password)
        : await api.login(identifier, password);
      dispatch('authenticated', user);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : mode === 'signup' ? 'Could not create account' : 'Could not sign in';
    } finally {
      busy = false;
    }
  }

  function switchMode() {
    mode = mode === 'login' ? 'signup' : 'login';
    password = '';
    error = '';
  }
</script>

<main class="login-page">
  <section class="login-card">
    <div class="brand-mark">✓</div>
    <p class="eyebrow">Self-hosted task ranking</p>
    <h1>Next Task</h1>
    <p class="muted">
      {mode === 'signup'
        ? 'Create an account and start deciding what deserves your attention next.'
        : 'Sign in to decide what deserves your attention next.'}
    </p>
    <form on:submit|preventDefault={submit}>
      <label>
        Username or email
        <input bind:value={identifier} autocomplete="username" required />
      </label>
      <label>
        Password
        <input
          type="password"
          bind:value={password}
          autocomplete={mode === 'signup' ? 'new-password' : 'current-password'}
          minlength={mode === 'signup' ? 10 : undefined}
          required
        />
      </label>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <button class="primary" disabled={busy}>
        {#if mode === 'signup'}
          {busy ? 'Creating account…' : 'Create account'}
        {:else}
          {busy ? 'Signing in…' : 'Sign in'}
        {/if}
      </button>
    </form>
    <button type="button" class="auth-switch" disabled={busy} on:click={switchMode}>
      {mode === 'signup' ? 'Already have an account? Sign in' : 'Create account'}
    </button>
  </section>
</main>

<style>
  .auth-switch {
    width: 100%;
    margin-top: .8rem;
    border: 0;
    background: transparent;
    color: var(--forest-2);
    padding: .35rem;
    font-size: .82rem;
    font-weight: 700;
    text-decoration: underline;
    text-underline-offset: .15rem;
  }
</style>
