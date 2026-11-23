<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '../api/client';
  import type { NotificationSettings } from '../api/types';
  import { t, text, message, errorMessage, type Message } from '../i18n';
  import {
    detectBrowserTimezone,
    getCurrentPushEndpoint,
    pushSupportStatus,
    sha256Hex,
    subscribeCurrentDevice,
    unsubscribeCurrentDevice,
    type PushSupportStatus
  } from '../notifications';
  import AppButton from './AppButton.svelte';

  let settings: NotificationSettings | null = null;
  let support: PushSupportStatus = 'unsupported';
  let currentEndpoint: string | null = null;
  let currentHash: string | null = null;
  let timezone = detectBrowserTimezone();
  let loading = true;
  let busy = false;
  let sendingTest = false;
  let error: Message = '';
  let notice: Message = '';

  const intlWithZones = Intl as typeof Intl & { supportedValuesOf?: (key: string) => string[] };
  const supportedTimezones = (() => {
    try {
      return intlWithZones.supportedValuesOf?.('timeZone') ?? [];
    } catch {
      return [];
    }
  })();

  $: timezoneOptions =
    timezone && !supportedTimezones.includes(timezone)
      ? [timezone, ...supportedTimezones]
      : supportedTimezones;
  $: deviceSubscribed = Boolean(
    settings && currentHash && settings.endpoint_hashes.includes(currentHash)
  );
  $: canEnable = Boolean(
    settings?.push_configured &&
      settings.vapid_public_key &&
      (support === 'default' || support === 'granted') &&
      !deviceSubscribed
  );

  async function syncBrowserState() {
    support = pushSupportStatus();
    currentEndpoint = await getCurrentPushEndpoint();
    currentHash = currentEndpoint ? await sha256Hex(currentEndpoint) : null;
  }

  async function load() {
    loading = true;
    error = '';
    try {
      const [loaded] = await Promise.all([api.notificationSettings(), syncBrowserState()]);
      settings = loaded;
      timezone = loaded.timezone || detectBrowserTimezone();
    } catch (reason) {
      error = errorMessage(reason, 'ui.notifications.couldNotLoad');
    } finally {
      loading = false;
    }
  }

  async function saveTimezone() {
    busy = true;
    error = '';
    notice = '';
    try {
      settings = await api.updateNotificationSettings(timezone.trim());
      timezone = settings.timezone || timezone;
      notice = message('ui.notifications.timezoneSaved');
    } catch (reason) {
      error = errorMessage(reason, 'ui.notifications.couldNotSaveTimezone');
    } finally {
      busy = false;
    }
  }

  async function enableReminders() {
    if (!settings?.vapid_public_key) return;
    busy = true;
    error = '';
    notice = '';
    try {
      const subscription = await subscribeCurrentDevice(settings.vapid_public_key);
      const chosenTimezone = timezone.trim() || detectBrowserTimezone();
      settings = await api.subscribePush({ ...subscription, timezone: chosenTimezone });
      timezone = settings.timezone || chosenTimezone;
      await syncBrowserState();
      notice = message('ui.notifications.remindersEnabled');
    } catch (reason) {
      await syncBrowserState();
      error = errorMessage(reason, 'ui.notifications.couldNotEnable');
    } finally {
      busy = false;
    }
  }

  async function disableThisDevice() {
    busy = true;
    error = '';
    notice = '';
    try {
      const endpoint = (await unsubscribeCurrentDevice()) ?? currentEndpoint;
      if (endpoint) {
        settings = await api.unsubscribePush(endpoint);
      }
      await syncBrowserState();
      notice = message('ui.notifications.remindersDisabled');
    } catch (reason) {
      error = errorMessage(reason, 'ui.notifications.couldNotDisable');
    } finally {
      busy = false;
    }
  }

  async function sendTest() {
    sendingTest = true;
    error = '';
    notice = '';
    try {
      const result = await api.sendTestNotification(currentEndpoint);
      notice = result.message;
      settings = await api.notificationSettings();
      await syncBrowserState();
    } catch (reason) {
      error = errorMessage(reason, 'ui.notifications.couldNotSendTest');
    } finally {
      sendingTest = false;
    }
  }

  $: statusMessageKey = !settings?.push_configured
    ? 'ui.notifications.notConfigured'
    : support === 'insecure' || support === 'unsupported' || support === 'ios-install-required'
      ? 'ui.notifications.notSupported'
      : support === 'denied'
        ? 'ui.notifications.permissionDenied'
        : deviceSubscribed
          ? 'ui.notifications.enabledOnThisDevice'
          : 'ui.notifications.disabledOnThisDevice';

  onMount(load);
</script>

<section class="panel notification-settings">
  <div class="section-heading">
    <div>
      <p class="eyebrow">{$t('ui.notifications.sectionEyebrow')}</p>
      <h2>{$t('ui.notifications.sectionTitle')}</h2>
      <p class="muted">{$t('ui.notifications.description')}</p>
    </div>
    {#if settings}
      <span class:enabled={deviceSubscribed && settings.push_configured} class="push-status">
        {$t(statusMessageKey)}
      </span>
    {/if}
  </div>

  {#if loading}
    <p class="muted">{$t('ui.notifications.loading')}</p>
  {:else if settings}
    {#if !settings.push_configured}
      <p class="help">{$t('ui.notifications.serverNotConfiguredHelp')}</p>
    {:else if support === 'ios-install-required'}
      <p class="notice">{$t('ui.notifications.iosInstallHint')}</p>
    {:else if support === 'insecure'}
      <p class="notice">{$t('ui.notifications.httpsRequired')}</p>
    {:else if support === 'denied'}
      <p class="error" role="alert">{$t('ui.notifications.permissionBlockedHelp')}</p>
    {/if}

    <form on:submit|preventDefault={saveTimezone}>
      <label>
        {$t('ui.notifications.timezone')}
        <input
          type="text"
          list="notification-timezones"
          bind:value={timezone}
          required
          disabled={busy}
        />
      </label>
      <datalist id="notification-timezones">
        {#each timezoneOptions as zone}
          <option value={zone}></option>
        {/each}
      </datalist>
      <p class="help tz-help">{$t('ui.notifications.timezoneHelp')}</p>
      <div class="push-actions">
        <AppButton type="submit" disabled={busy || !timezone.trim()}>
          {$t('ui.notifications.saveTimezone')}
        </AppButton>
        {#if canEnable}
          <AppButton variant="primary" disabled={busy} on:click={enableReminders}>
            {busy ? $t('ui.notifications.enabling') : $t('ui.notifications.enableReminders')}
          </AppButton>
        {/if}
        {#if deviceSubscribed && settings.push_configured}
          <AppButton disabled={busy || sendingTest} on:click={sendTest}>
            {sendingTest ? $t('ui.notifications.sendingTest') : $t('ui.notifications.sendTest')}
          </AppButton>
          <AppButton disabled={busy} on:click={disableThisDevice}>
            {$t('ui.notifications.disableThisDevice')}
          </AppButton>
        {/if}
      </div>
    </form>

    {#if error}<p class="error" role="alert">{$text(error)}</p>{/if}
    {#if notice}<p class="notice">{$text(notice)}</p>{/if}
    <p class="muted count-note">{$t('ui.notifications.deviceCount', { count: settings.subscription_count })}</p>
    <p class="help">{$t('ui.notifications.bestEffortNote')}</p>
  {:else if error}
    <p class="error" role="alert">{$text(error)}</p>
  {/if}
</section>

<style>
  .section-heading {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    margin-bottom: .9rem;
  }

  .section-heading .eyebrow {
    margin-bottom: .25rem;
  }

  .section-heading h2,
  .section-heading p {
    margin-top: 0;
  }

  .push-status {
    flex: none;
    border-radius: 99px;
    padding: .32rem .68rem;
    background: #efeae0;
    color: #565e59;
    font-size: .74rem;
    font-weight: 700;
  }

  .push-status.enabled {
    background: #e2f0e8;
    color: #21563d;
  }

  .tz-help {
    margin: -.45rem 0 0;
  }

  .push-actions {
    display: flex;
    flex-wrap: wrap;
    gap: .55rem;
  }

  .count-note {
    margin: .9rem 0 .25rem;
    font-size: .84rem;
  }

  @media (max-width: 560px) {
    .section-heading {
      flex-direction: column;
      gap: .5rem;
    }
  }
</style>
