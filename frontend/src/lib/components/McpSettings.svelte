<script lang="ts">
  import { onMount } from 'svelte';
  import { request } from '../api/client';
  import { t } from '../i18n';
  import AppButton from './AppButton.svelte';

  type Connection = { id: number; client_name: string; scope: string };
  let settings: { endpoint: string; connections: Connection[] } | null = null;
  let loading = true;
  let error = false;
  let copied = false;
  async function load() {
    try { settings = await request('/api/settings/mcp'); error = false; }
    catch { error = true; }
    finally { loading = false; }
  }
  async function disconnect(id: number) {
    try { await request(`/api/settings/mcp/connections/${id}`, { method: 'DELETE' }); await load(); }
    catch { error = true; }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(settings!.endpoint); copied = true; }
    catch { error = true; }
  }
  onMount(load);
</script>

<section class="panel">
  <h2>{$t('ui.mcp.settingsTitle')}</h2>
  {#if loading}<p>{$t('ui.mcp.loading')}</p>
  {:else if error}<p role="alert" class="error">{$t('ui.mcp.settingsError')}</p>
  {:else if settings}
    <p>{$t('ui.mcp.settingsHelp')}</p>
    <p>{$t('ui.mcp.clientHelp')}</p>
    <label>{$t('ui.mcp.endpoint')} <input readonly value={settings.endpoint} on:focus={(event) => event.currentTarget.select()} /></label>
    <AppButton on:click={copy}>{$t('ui.mcp.copy')}</AppButton>
    {#if copied}<span role="status">{$t('ui.mcp.copied')}</span>{/if}
    <h3>{$t('ui.mcp.connections')}</h3>
    {#if settings.connections.length === 0}<p>{$t('ui.mcp.empty')}</p>{/if}
    {#each settings.connections as connection (connection.id)}
      <p>{connection.client_name} ({connection.scope}) <AppButton on:click={() => disconnect(connection.id)}>{$t('ui.mcp.disconnect')}</AppButton></p>
    {/each}
  {/if}
</section>
