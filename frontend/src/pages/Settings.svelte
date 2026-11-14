<script lang="ts">
  import { t, text, message, errorMessage, type Message } from '../lib/i18n';
  import { onMount } from 'svelte';
  import { api } from '../lib/api/client';
  import AccountSettings from '../lib/components/AccountSettings.svelte';
  import GeminiSettings from '../lib/components/GeminiSettings.svelte';
  import PomodoroSettings from '../lib/components/PomodoroSettings.svelte';
  import type { User } from '../lib/api/types';
  import packageInfo from '../../package.json';
  import AppButton from '../lib/components/AppButton.svelte';
  import PasswordField from '../lib/components/PasswordField.svelte';
  import TextArea from '../lib/components/TextArea.svelte';
  import LanguageSelector from '../lib/components/LanguageSelector.svelte';

  export let user: User;
  let currentPassword = '';
  let newPassword = '';
  let confirmation = '';
  let error: Message = '';
  let notice: Message = '';
  let formula = '';
  let workflowError: Message = '';
  let workflowNotice: Message = '';

  async function loadWorkflow() {
    try {
      formula = (await api.scoringSettings()).scoring_formula;
    } catch (reason) {
      workflowError = errorMessage(reason, 'ui.settings.couldNotLoadWorkflowSettings');
    }
  }

  async function saveFormula() {
    workflowError = workflowNotice = '';
    try {
      await api.updateScoringSettings(formula);
      workflowNotice = message('ui.settings.scoringFormulaSaved');
    } catch (reason) {
      workflowError = errorMessage(reason, 'ui.settings.couldNotSaveScoringFormula');
    }
  }

  onMount(() => { void loadWorkflow(); });

  async function changePassword() {
    error = '';
    notice = '';
    if (newPassword !== confirmation) {
      error = message('ui.passwordRecovery.newPasswordsDoNotMatch');
      return;
    }
    try {
      await api.changePassword(currentPassword, newPassword);
      currentPassword = newPassword = confirmation = '';
      notice = message('ui.settings.passwordChangedOtherSessionsWereSignedOut');
    } catch (reason) {
      error = errorMessage(reason, 'ui.settings.couldNotChangePassword');
    }
  }
</script>

<div class="page-heading"><div><p class="eyebrow">{$t('ui.accountSettings.yourAccount')}</p><h1>{$t('ui.app.settings')}</h1></div></div>
<div class="settings-stack narrow">
  <section class="panel"><LanguageSelector {user} /></section>
  <AccountSettings {user} />
  <section class="panel"><h2>{$t('ui.settings.scoring')}</h2><form on:submit|preventDefault={saveFormula}><label>{$t('ui.settings.scoringFormula')}<TextArea className="code-input" bind:value={formula} rows="4" /></label><p class="help">{$t('ui.settings.variablesPriorityAgedaysIdledaysDueoffsetdaysHasduedateTagvalueSupports')}</p><AppButton type="submit" variant="primary">{$t('ui.settings.saveScoringFormula')}</AppButton></form>{#if workflowError}<p class="error" role="alert">{$text(workflowError)}</p>{/if}{#if workflowNotice}<p class="notice">{$text(workflowNotice)}</p>{/if}</section>
  <PomodoroSettings />
  <GeminiSettings />
  <section class="panel">
    <h2>{$t('ui.settings.changePassword')}</h2>
    <form on:submit|preventDefault={changePassword}>
      <PasswordField id="current-password" label={$t('ui.accountSettings.currentPassword')} bind:value={currentPassword} autocomplete="current-password" required />
      <PasswordField id="new-password" label={$t('ui.passwordRecovery.newPassword')} bind:value={newPassword} minlength={10} autocomplete="new-password" required />
      <PasswordField id="confirm-new-password" label={$t('ui.passwordRecovery.confirmNewPassword')} bind:value={confirmation} minlength={10} autocomplete="new-password" required />
      {#if error}<p class="error" role="alert">{$text(error)}</p>{/if}
      {#if notice}<p class="notice">{$text(notice)}</p>{/if}
      <AppButton type="submit" variant="primary">{$t('ui.settings.changePassword')}</AppButton>
    </form>
  </section>
  <section class="panel"><h2>{$t('ui.settings.about')}</h2><p>{$t('ui.settings.nextTaskCalculatesScoresWhenYouViewYour')}</p><p class="muted">{$t('ui.settings.offlineModeCachesThisApplicationShellOnlyTask')}</p><p class="muted">{$t('ui.settings.nextTaskV', { value1: packageInfo.version })}</p></section>
</div>
