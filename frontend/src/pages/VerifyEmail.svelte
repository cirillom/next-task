<script lang="ts">
  import { api } from '../lib/api/client';
  import AppButton from '../lib/components/AppButton.svelte';

  export let token: string | null;
  export let signedIn: boolean;

  let busy = false;
  let verified = false;
  let error = '';

  async function verify() {
    if (!token) return;
    busy = true;
    error = '';
    try {
      await api.verifyContactEmail(token);
      verified = true;
      history.replaceState(null, '', '#/verify-email-complete');
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not verify this email';
    } finally {
      busy = false;
    }
  }
</script>

<main class="login-page">
  <section class="login-card">
    <div class="brand-mark">✓</div>
    <h1>Verify contact email</h1>
    {#if verified}
      <p>Your contact email is verified.</p>
      <a href={signedIn ? '#/settings' : '#/'}>Continue to Next Task</a>
    {:else if !token}
      <p class="error" role="alert">This verification link is invalid.</p>
    {:else}
      <p>Confirm this address as the contact email for your Next Task account.</p>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <AppButton variant="primary" disabled={busy} on:click={verify}>
        {busy ? 'Verifying…' : 'Verify email'}
      </AppButton>
    {/if}
  </section>
</main>
