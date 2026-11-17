<script lang="ts">
  import { onMount } from 'svelte';
  import { request } from '../lib/api/client';
  import { t } from '../lib/i18n';
  import AppButton from '../lib/components/AppButton.svelte';

  export let requestId: string | null;
  let details: { account: string; client_name: string; redirect_uri: string; scope: string } | null = null;
  let error = false;
  let busy = false;
  onMount(async () => {
    try { details = await request(`/api/mcp/authorizations/${encodeURIComponent(requestId ?? '')}`); }
    catch { error = true; }
  });
  async function decide(allow: boolean) {
    busy = true;
    try {
      const response = await request<{ redirect_uri: string }>(`/api/mcp/authorizations/${encodeURIComponent(requestId ?? '')}`, {
        method: 'POST', body: JSON.stringify({ allow })
      });
      window.location.assign(response.redirect_uri);
    } catch { error = true; busy = false; }
  }
</script>

<main class="narrow panel">
  <h1>{$t('ui.mcp.consentTitle')}</h1>
  {#if error}<p class="error" role="alert">{$t('ui.mcp.consentError')}</p>
  {:else if !details}<p>{$t('ui.mcp.loading')}</p>
  {:else}
    <p>{$t('ui.mcp.account')}: <strong>{details.account}</strong></p>
    <p>{$t('ui.mcp.client')}: <strong>{details.client_name}</strong></p>
    <p>{$t('ui.mcp.redirect')}: {new URL(details.redirect_uri).host}</p>
    <p>{$t('ui.mcp.unverified')}</p>
    <p>{$t('ui.mcp.permission')}</p>
    <AppButton variant="primary" disabled={busy} on:click={() => decide(true)}>{$t('ui.mcp.allow')}</AppButton>
    <AppButton disabled={busy} on:click={() => decide(false)}>{$t('ui.mcp.deny')}</AppButton>
  {/if}
</main>
