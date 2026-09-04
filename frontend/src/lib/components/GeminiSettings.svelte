<script lang="ts">
  import { onMount } from 'svelte';
  import { geminiApi, type GeminiSettings } from '../api/gemini';

  let settings: GeminiSettings | null = null;
  let apiKey = '';
  let loading = true;
  let busy = false;
  let error = '';
  let notice = '';

  onMount(async () => {
    try {
      settings = await geminiApi.settings();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load Gemini settings';
    } finally {
      loading = false;
    }
  });

  async function save() {
    busy = true;
    error = '';
    notice = '';
    try {
      settings = await geminiApi.saveKey(apiKey);
      apiKey = '';
      notice = 'Gemini API key saved securely.';
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not save Gemini API key';
    } finally {
      busy = false;
    }
  }

  async function remove() {
    if (!window.confirm('Remove your Gemini API key? Text to task will stop working.')) return;
    busy = true;
    error = '';
    notice = '';
    try {
      settings = await geminiApi.deleteKey();
      notice = 'Gemini API key removed.';
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not remove Gemini API key';
    } finally {
      busy = false;
    }
  }
</script>

<section class="panel">
  <div class="integration-heading">
    <div>
      <p class="eyebrow">AI integration</p>
      <h2>Gemini text to task</h2>
    </div>
    {#if settings?.configured}<span class="configured">Configured</span>{/if}
  </div>
  <p class="muted">
    Add your personal Gemini API key to turn natural-language notes into editable task drafts.
    The key is encrypted on this server and is never shown again.
  </p>
  {#if loading}
    <p class="muted">Loading integration settings…</p>
  {:else}
    <form on:submit|preventDefault={save}>
      <label>
        Gemini API key
        <input
          type="password"
          bind:value={apiKey}
          minlength="20"
          maxlength="512"
          autocomplete="off"
          placeholder={settings?.configured ? settings.masked_key || 'Configured' : 'Paste your API key'}
          required
        />
      </label>
      <p class="help">
        Model: <code>{settings?.model || 'Gemini Flash'}</code>. Keys are available from
        <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer">Google AI Studio</a>.
      </p>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      {#if notice}<p class="notice">{notice}</p>{/if}
      <div class="integration-actions">
        {#if settings?.configured}
          <button type="button" class="danger-subtle" disabled={busy} on:click={remove}>Remove key</button>
        {/if}
        <span></span>
        <button class="primary" disabled={busy || apiKey.trim().length < 20}>
          {busy ? 'Saving…' : settings?.configured ? 'Replace key' : 'Save key'}
        </button>
      </div>
    </form>
  {/if}
</section>

<style>
  .integration-heading, .integration-actions { display: flex; align-items: center; gap: .8rem; }
  .integration-heading { justify-content: space-between; }
  .integration-heading h2 { margin-bottom: .35rem; }
  .configured { border-radius: 99rem; background: #e2f0e8; color: #21563d; padding: .3rem .6rem; font-size: .75rem; font-weight: 750; }
  .integration-actions span { flex: 1; }
  code { overflow-wrap: anywhere; }
</style>
