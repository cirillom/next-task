<script lang="ts">
  import { api } from '../api/client';
  import type { User } from '../api/types';
  import { t, text, locale, languages, setLanguage, message, type Language, type Message } from '../i18n';

  export let user: User | null = null;
  let busy = false;
  let error: Message = '';

  async function change(event: Event) {
    const language = (event.target as HTMLSelectElement).value as Language;
    const previous = $locale;
    busy = true;
    error = '';
    try {
      if (user) {
        const saved = await api.updateLanguage(language);
        user.language = saved.language;
      }
      setLanguage(language);
    } catch {
      (event.target as HTMLSelectElement).value = previous;
      error = message('language.saveError');
    } finally { busy = false; }
  }
</script>

<label class="language-selector">
  <span>{$t('language.label')}</span>
  <select value={$locale} disabled={busy} on:change={change}>
    {#each Object.entries(languages) as [value, label]}<option {value}>{label}</option>{/each}
  </select>
</label>
{#if error}<p class="error" role="alert">{$text(error)}</p>{/if}

<style>
  .language-selector { display: inline-flex; align-items: center; gap: .5rem; font-size: .85rem; }
  select { width: auto; min-width: 11rem; }
</style>
