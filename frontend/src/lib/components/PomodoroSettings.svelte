<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '../api/client';
  import type { PomodoroSettings } from '../api/types';

  let settings: PomodoroSettings = {
    focus_minutes: 25,
    short_break_minutes: 5,
    long_break_minutes: 15,
    short_breaks_before_long: 3
  };
  let loading = true;
  let saving = false;
  let error = '';
  let notice = '';

  async function load() {
    try {
      settings = await api.pomodoroSettings();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not load Pomodoro settings';
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
      notice = 'Pomodoro settings saved.';
    } catch (reason) {
      error = reason instanceof Error ? reason.message : 'Could not save Pomodoro settings';
    } finally {
      saving = false;
    }
  }

  onMount(load);
</script>

<section class="panel pomodoro-settings">
  <div class="section-heading">
    <div>
      <h2>Pomodoro</h2>
      <p class="muted">Choose the rhythm used by Focus sessions.</p>
    </div>
    <span class="tomato" aria-hidden="true">◉</span>
  </div>

  {#if loading}
    <p class="muted">Loading Pomodoro settings…</p>
  {:else}
    <form on:submit|preventDefault={save}>
      <div class="pomodoro-grid">
        <label>
          Focus time
          <span class="number-field"><input type="number" min="1" max="180" bind:value={settings.focus_minutes} required /><small>min</small></span>
        </label>
        <label>
          Short break
          <span class="number-field"><input type="number" min="1" max="60" bind:value={settings.short_break_minutes} required /><small>min</small></span>
        </label>
        <label>
          Long break
          <span class="number-field"><input type="number" min="1" max="180" bind:value={settings.long_break_minutes} required /><small>min</small></span>
        </label>
        <label>
          Short breaks before long
          <span class="number-field"><input type="number" min="1" max="12" bind:value={settings.short_breaks_before_long} required /><small>breaks</small></span>
        </label>
      </div>
      {#if error}<p class="error">{error}</p>{/if}
      {#if notice}<p class="notice">{notice}</p>{/if}
      <button class="primary" disabled={saving}>{saving ? 'Saving…' : 'Save Pomodoro settings'}</button>
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

  .number-field input {
    min-width: 0;
    border: 0;
    background: transparent;
  }

  .number-field small {
    padding-right: .7rem;
    color: var(--muted);
    white-space: nowrap;
  }

  @media (max-width: 620px) {
    .pomodoro-grid {
      grid-template-columns: 1fr;
    }
  }
</style>
