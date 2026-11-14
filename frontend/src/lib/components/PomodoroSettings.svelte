<script lang="ts">
  import { t, text, message, errorMessage, type Message } from '../i18n';
  import { onMount } from 'svelte';
  import { api } from '../api/client';
  import type { PomodoroSettings } from '../api/types';
  import AppButton from './AppButton.svelte';
  import NumberField from './NumberField.svelte';

  let settings: PomodoroSettings = {
    focus_minutes: 25,
    short_break_minutes: 5,
    long_break_minutes: 15,
    short_breaks_before_long: 3,
    alert_mode: 'notification'
  };
  let loading = true;
  let saving = false;
  let error: Message = '';
  let notice: Message = '';

  async function load() {
    try {
      settings = await api.pomodoroSettings();
    } catch (reason) {
      error = errorMessage(reason, 'ui.pomodoroLauncher.couldNotLoadPomodoroSettings');
    } finally {
      loading = false;
    }
  }

  async function save() {
    saving = true;
    error = '';
    notice = '';
    try {
      settings = await api.updatePomodoroSettings(settings);
      notice = message('ui.pomodoroSettings.pomodoroSettingsSaved');
    } catch (reason) {
      error = errorMessage(reason, 'ui.pomodoroSettings.couldNotSavePomodoroSettings');
    } finally {
      saving = false;
    }
  }

  onMount(load);
</script>

<section class="panel pomodoro-settings">
  <div class="section-heading">
    <div>
      <h2>{$t('ui.pomodoroLauncher.pomodoro')}</h2>
      <p class="muted">{$t('ui.pomodoroSettings.chooseTheRhythmUsedByFocusSessions')}</p>
    </div>
    <span class="tomato" aria-hidden="true">◉</span>
  </div>

  {#if loading}
    <p class="muted">{$t('ui.pomodoroSettings.loadingPomodoroSettings')}</p>
  {:else}
    <form on:submit|preventDefault={save}>
      <div class="pomodoro-grid">
        <label>
          {$t('ui.pomodoroSettings.focusTime')}
          <span class="number-field"><NumberField min="1" max="180" bind:value={settings.focus_minutes} required /><small>{$t('ui.pomodoroSettings.min')}</small></span>
        </label>
        <label>
          {$t('ui.pomodoroLauncher.shortBreak')}
          <span class="number-field"><NumberField min="1" max="60" bind:value={settings.short_break_minutes} required /><small>{$t('ui.pomodoroSettings.min')}</small></span>
        </label>
        <label>
          {$t('ui.pomodoroLauncher.longBreak')}
          <span class="number-field"><NumberField min="1" max="180" bind:value={settings.long_break_minutes} required /><small>{$t('ui.pomodoroSettings.min')}</small></span>
        </label>
        <label>
          {$t('ui.pomodoroSettings.shortBreaksBeforeLong')}
          <span class="number-field"><NumberField min="1" max="12" bind:value={settings.short_breaks_before_long} required /><small>{$t('ui.pomodoroSettings.breaks')}</small></span>
        </label>
      </div>
      <fieldset class="alert-mode">
        <legend>{$t('ui.pomodoroSettings.whenAPeriodEnds')}</legend>
        <label>
          <input type="radio" bind:group={settings.alert_mode} value="notification" />
          <span><strong>{$t('ui.pomodoroSettings.notification')}</strong><small>{$t('ui.pomodoroSettings.playOneShortChimeAndPrepareTheNext')}</small></span>
        </label>
        <label>
          <input type="radio" bind:group={settings.alert_mode} value="alarm" />
          <span><strong>{$t('ui.pomodoroSettings.alarm')}</strong><small>{$t('ui.pomodoroSettings.keepRingingUntilYouDismissItOnAny')}</small></span>
        </label>
      </fieldset>
      {#if error}<p class="error">{$text(error)}</p>{/if}
      {#if notice}<p class="notice">{$text(notice)}</p>{/if}
      <AppButton type="submit" variant="primary" disabled={saving}>{saving ? $t('ui.geminiSettings.saving') : $t('ui.pomodoroSettings.savePomodoroSettings')}</AppButton>
    </form>
  {/if}
</section>

<style>
  .section-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
  }

  .section-heading h2,
  .section-heading p {
    margin-top: 0;
  }

  .tomato {
    display: grid;
    width: 2.3rem;
    height: 2.3rem;
    place-items: center;
    border-radius: 50%;
    background: #fff0e8;
    color: #a34e36;
    font-size: 1.25rem;
  }

  .pomodoro-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: .85rem;
    margin: .9rem 0 1rem;
  }

  .number-field {
    display: flex;
    align-items: center;
    margin-top: .35rem;
    overflow: hidden;
    border: 1px solid var(--line);
    border-radius: .55rem;
    background: #fff;
  }

  .number-field :global(input) {
    min-width: 0;
    border: 0;
    background: transparent;
  }

  .number-field small {
    padding-right: .7rem;
    color: var(--muted);
    white-space: nowrap;
  }

  .alert-mode {
    display: grid;
    gap: .55rem;
    margin: 0 0 1rem;
    padding: .85rem;
    border: 1px solid var(--line);
    border-radius: .7rem;
  }

  .alert-mode legend { padding: 0 .3rem; font-weight: 800; }
  .alert-mode label { display: flex; align-items: flex-start; gap: .6rem; margin: 0; }
  .alert-mode input { width: auto; margin-top: .2rem; }
  .alert-mode span { display: grid; gap: .12rem; }
  .alert-mode small { color: var(--muted); font-weight: 500; }

  @media (max-width: 620px) {
    .pomodoro-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
