<script lang="ts">
  import { t, text, rich, message, errorMessage, type Message } from '../i18n';
  import { onMount } from 'svelte';
  import { geminiApi, type GeminiModel, type GeminiSettings } from '../api/gemini';
  import AppButton from './AppButton.svelte';
  import TextField from './TextField.svelte';

  let settings: GeminiSettings | null = null;
  let apiKey = '';
  let models: GeminiModel[] = [];
  let selectedModel = '';
  let modelsLoading = false;
  let modelError: Message = '';
  let loading = true;
  let busy = false;
  let error: Message = '';
  let notice: Message = '';

  onMount(async () => {
    try {
      settings = await geminiApi.settings();
      if (settings.configured) await loadModels();
    } catch (reason) {
      error = errorMessage(reason, 'ui.geminiSettings.couldNotLoadGeminiSettings');
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
      modelError = errorMessage(reason, 'ui.geminiSettings.couldNotLoadGoogleModels');
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
      notice = message('ui.geminiSettings.geminiApiKeySavedSecurely');
      await loadModels();
    } catch (reason) {
      error = errorMessage(reason, 'ui.geminiSettings.couldNotSaveGeminiApiKey');
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
      notice = message('ui.geminiSettings.geminiModelSaved');
    } catch (reason) {
      modelError = errorMessage(reason, 'ui.geminiSettings.couldNotSaveGeminiModel');
    } finally {
      busy = false;
    }
  }

  async function remove() {
    if (!window.confirm($t('ui.geminiSettings.removeYourGeminiApiKeyTextToTask'))) return;
    busy = true;
    error = '';
    notice = '';
    try {
      settings = await geminiApi.deleteKey();
      models = [];
      selectedModel = '';
      modelError = '';
      notice = message('ui.geminiSettings.geminiApiKeyRemoved');
    } catch (reason) {
      error = errorMessage(reason, 'ui.geminiSettings.couldNotRemoveGeminiApiKey');
    } finally {
      busy = false;
    }
  }
</script>

<section class="panel">
  <div class="integration-heading">
    <div>
      <p class="eyebrow">{$t('ui.geminiSettings.aiIntegration')}</p>
      <h2>{$t('ui.geminiSettings.geminiTextToTask')}</h2>
    </div>
    {#if settings?.configured}<span class="configured">{$t('ui.geminiSettings.configured')}</span>{/if}
  </div>
  <p class="muted">
    {$t('ui.geminiSettings.addYourPersonalGeminiApiKeyToTurn')}
  </p>
  {#if loading}
    <p class="muted">{$t('ui.geminiSettings.loadingIntegrationSettings')}</p>
  {:else}
    <form on:submit|preventDefault={save}>
      <label>
        {$t('ui.geminiSettings.geminiApiKey')}
        <TextField
          type="password"
          bind:value={apiKey}
          minlength="20"
          maxlength="512"
          autocomplete="off"
          placeholder={settings?.configured ? settings.masked_key || $t('ui.geminiSettings.configured') : $t('ui.geminiSettings.pasteYourApiKey')}
          required
        />
      </label>
      <p class="help">
        {@html $rich('ui.geminiSettings.keyHelp')}
      </p>
      {#if error}<p class="error" role="alert">{$text(error)}</p>{/if}
      {#if notice}<p class="notice">{$text(notice)}</p>{/if}
      <div class="integration-actions">
        {#if settings?.configured}
          <AppButton variant="danger" disabled={busy} on:click={remove}>{$t('ui.geminiSettings.removeKey')}</AppButton>
        {/if}
        <span></span>
        <AppButton type="submit" variant="primary" disabled={busy || apiKey.trim().length < 20}>
          {busy ? $t('ui.geminiSettings.saving') : settings?.configured ? $t('ui.geminiSettings.replaceKey') : $t('ui.geminiSettings.saveKey')}
        </AppButton>
      </div>
    </form>
    {#if settings?.configured}
      <div class="model-settings">
        <label for="gemini-model">{$t('ui.geminiSettings.modelForTextToTask')}</label>
        <div class="model-actions">
          <select id="gemini-model" bind:value={selectedModel} disabled={busy || modelsLoading || models.length === 0}>
            {#if selectedModel && !models.some((model) => model.id === selectedModel)}
              <option value={selectedModel}>{$t('ui.geminiSettings.currentDefault', { value1: selectedModel })}</option>
            {/if}
            {#each models as model}
              <option value={model.id}>{model.name} ({model.id})</option>
            {/each}
          </select>
          <AppButton disabled={busy || modelsLoading} on:click={loadModels}>{$t('ui.geminiSettings.refresh')}</AppButton>
          <AppButton variant="primary" disabled={busy || modelsLoading || !models.some((model) => model.id === selectedModel) || selectedModel === settings.model} on:click={saveModel}>{$t('ui.geminiSettings.saveModel')}</AppButton>
        </div>
        <p class="help">{modelsLoading ? $t('ui.geminiSettings.loadingModelsFromGoogle') : $t('ui.geminiSettings.modelHelp', {model: settings.model})}</p>
        {#if modelError}<p class="error" role="alert">{$text(modelError)}</p>{/if}
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
