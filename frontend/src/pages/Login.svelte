<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  import { api } from '../lib/api/client';
  import type { User } from '../lib/api/types';

  const dispatch = createEventDispatcher<{ authenticated: User }>();
  let email = '';
  let password = '';
  let error = '';
  let busy = false;

  async function submit() {
    busy = true;
    error = '';
    try {
      dispatch('authenticated', await api.login(email, password));
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not sign in';
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
    <p class="muted">Sign in to decide what deserves your attention next.</p>
    <form on:submit|preventDefault={submit}>
      <label>Email<input type="email" bind:value={email} autocomplete="email" required /></label>
      <label>Password<input type="password" bind:value={password} autocomplete="current-password" required /></label>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <button class="primary" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
    </form>
  </section>
</main>
