<script lang="ts">
  import { onMount } from 'svelte';
  import { geminiApi, type GeminiModel, type GeminiSettings } from '../api/gemini';
  import AppButton from './AppButton.svelte';
  import TextField from './TextField.svelte';

  let settings: GeminiSettings | null = null;
  let apiKey = '';
  let models: GeminiModel[] = [];
  let selectedModel = '';
  let modelsLoading = false;
  let modelError = '';
  let loading = true;
  let busy = false;
  let error = '';
  let notice = '';

  onMount(async () => {
    try {
      settings = await geminiApi.settings();
      if (settings.configured) await loadModels();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load Gemini settings';
    } finally {
      loading = false;
    }
  });

  async function loadModels() {
    modelsLoading = true;
    modelError = '';
    try {
      models = await geminiApi.models();
      selectedModel = settings?.model || '';
    } catch (reason) {
      models = [];
      modelError = reason instanceof Error ? reason.message : 'Could not load Google models';
    } finally {
      modelsLoading = false;
    }
  }

  async function save() {
    busy = true;
    error = '';
    notice = '';
    try {
      settings = await geminiApi.saveKey(apiKey);
      apiKey = '';
      notice = 'Gemini API key saved securely.';
      await loadModels();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not save Gemini API key';
    } finally {
      busy = false;
    }
  }

  async function saveModel() {
    busy = true;
    modelError = '';
    notice = '';
    try {
      settings = await geminiApi.saveModel(selectedModel);
      notice = 'Gemini model saved.';
    } catch (reason) {
      modelError = reason instanceof Error ? reason.message : 'Could not save Gemini model';
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
      models = [];
      selectedModel = '';
      modelError = '';
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
        <TextField
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
        Keys are available from
        <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer">Google AI Studio</a>.
      </p>
      {#if error}<p class="error" role="alert">{error}</p>{/if}
      {#if notice}<p class="notice">{notice}</p>{/if}
      <div class="integration-actions">
        {#if settings?.configured}
          <AppButton variant="danger" disabled={busy} on:click={remove}>Remove key</AppButton>
        {/if}
        <span></span>
        <AppButton type="submit" variant="primary" disabled={busy || apiKey.trim().length < 20}>
          {busy ? 'Saving…' : settings?.configured ? 'Replace key' : 'Save key'}
        </AppButton>
      </div>
    </form>
    {#if settings?.configured}
      <div class="model-settings">
        <label for="gemini-model">Model for text to task</label>
        <div class="model-actions">
          <select id="gemini-model" bind:value={selectedModel} disabled={busy || modelsLoading || models.length === 0}>
            {#if selectedModel && !models.some((model) => model.id === selectedModel)}
              <option value={selectedModel}>{selectedModel} (current default)</option>
            {/if}
            {#each models as model}
              <option value={model.id}>{model.name} ({model.id})</option>
            {/each}
          </select>
          <AppButton disabled={busy || modelsLoading} on:click={loadModels}>Refresh</AppButton>
          <AppButton variant="primary" disabled={busy || modelsLoading || !models.some((model) => model.id === selectedModel) || selectedModel === settings.model} on:click={saveModel}>Save model</AppButton>
        </div>
        <p class="help">{modelsLoading ? 'Loading models from Google…' : 'Available text models for your API key. Current model: ' + settings.model}</p>
        {#if modelError}<p class="error" role="alert">{modelError}</p>{/if}
      </div>
    {/if}
  {/if}
</section>

<style>
  .integration-heading, .integration-actions { display: flex; align-items: center; gap: .8rem; }
  .integration-heading { justify-content: space-between; }
  .integration-heading h2 { margin-bottom: .35rem; }
  .configured { border-radius: 99rem; background: #e2f0e8; color: #21563d; padding: .3rem .6rem; font-size: .75rem; font-weight: 750; }
  .integration-actions span { flex: 1; }
  .model-settings { margin-top: 1.25rem; display: grid; gap: .6rem; }
  .model-actions { display: flex; gap: .5rem; flex-wrap: wrap; align-items: center; }
  .model-actions select { flex: 1 1 16rem; }
</style>
