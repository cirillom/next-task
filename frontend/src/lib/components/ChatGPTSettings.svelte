<script lang="ts">
  import { onMount } from 'svelte';
  import { mcpApi, type McpSettings } from '../api/mcp';

  let settings: McpSettings | null = null;
  let error = '';
  let notice = '';
  let revoking = false;

  async function load() {
    error = '';
    try {
      settings = await mcpApi.settings();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load ChatGPT settings';
    }
  }

  async function copyUrl() {
    if (!settings) return;
    try {
      await navigator.clipboard.writeText(settings.connector_url);
      notice = 'Connector URL copied.';
      error = '';
    } catch {
      error = 'Could not copy automatically. Select and copy the URL below.';
    }
  }

  async function revokeAll() {
    if (!window.confirm('Disconnect every ChatGPT connection from your Next Task account?')) return;
    revoking = true;
    error = '';
    notice = '';
    try {
      settings = await mcpApi.revokeAll();
      notice = 'All ChatGPT connections were revoked.';
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not revoke ChatGPT connections';
    } finally {
      revoking = false;
    }
  }

  onMount(load);
</script>

<section class="panel">
  <p class="eyebrow">No API key required</p>
  <h2>ChatGPT task connector</h2>
  <p>
    Connect ChatGPT directly to Next Task. ChatGPT interprets your request and can read,
    create, update, finish, reopen, block, or unblock tasks after you approve changes.
  </p>
  <label>
    MCP connector URL
    <span class="connector-row">
      <input class="code-input" value={settings?.connector_url || 'Loading…'} readonly />
      <button type="button" on:click={copyUrl} disabled={!settings}>Copy</button>
    </span>
  </label>
  <p class="help">
    In ChatGPT, enable <strong>Developer mode</strong> under <strong>Settings → Security and
    login</strong>. Then open <strong>Settings → Plugins</strong>, add a custom connector, paste
    this URL, and sign in with your Next Task account.
  </p>
  <p class="muted">
    Active connections: <strong>{settings?.active_connections ?? '—'}</strong>
  </p>
  {#if error}<p class="error">{error}</p>{/if}
  {#if notice}<p class="notice">{notice}</p>{/if}
  {#if settings?.active_connections}
    <button class="danger" type="button" on:click={revokeAll} disabled={revoking}>
      {revoking ? 'Disconnecting…' : 'Disconnect all ChatGPT connections'}
    </button>
  {/if}
</section>
