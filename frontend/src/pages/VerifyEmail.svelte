<script lang="ts">
  import { api } from '../lib/api/client';
  import AppButton from '../lib/components/AppButton.svelte';
  import { reloadApp } from '../lib/navigation';

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
      await api.verifyEmail(token);
      verified = true;
      history.replaceState(null, '', signedIn ? '#/settings' : '#/');
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
    <h1>Verify your email</h1>
    {#if verified}
      <p>Your email is verified. You can use it to sign in.</p>
      <a href={signedIn ? '/#/settings' : '/#/'} on:click|preventDefault={() => reloadApp(signedIn ? '/#/settings' : '/#/')}>Continue to Next Task</a>
    {:else if !token}
      <p class="error" role="alert">This verification link is invalid.</p>
    {:else}
      <p>Confirm this address for your Next Task account. If you changed your email, use the new address to sign in afterward.</p>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      <AppButton variant="primary" disabled={busy} on:click={verify}>
        {busy ? 'Verifying…' : 'Verify email'}
      </AppButton>
    {/if}
  </section>
</main>
