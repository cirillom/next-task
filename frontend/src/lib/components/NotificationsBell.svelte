<script lang="ts">
  import { createEventDispatcher, onMount } from 'svelte';
  import { api } from '../api/client';
  import type { NotificationItem } from '../api/types';
  import { formatRelativeTime } from '../format';
  import { t, text, errorMessage, type Message } from '../i18n';
  import { dismissible } from '../keyboard';

  const dispatch = createEventDispatcher<{ openNotification: { taskId: number | null } }>();

  let open = false;
  let loading = false;
  let loaded = false;
  let busy = false;
  let unreadCount = 0;
  let items: NotificationItem[] = [];
  let error: Message = '';

  async function refresh(showLoading = false) {
    if (showLoading) loading = true;
    error = '';
    try {
      const response = await api.notifications();
      unreadCount = response.unread_count;
      items = response.items;
      loaded = true;
    } catch (reason) {
      if (open || showLoading) error = errorMessage(reason, 'ui.notifications.couldNotLoadList');
    } finally {
      if (showLoading) loading = false;
    }
  }

  function toggle() {
    open = !open;
    if (open) void refresh(!loaded);
  }

  async function markAllRead() {
    busy = true;
    error = '';
    try {
      const response = await api.markNotificationsRead();
      unreadCount = response.unread_count;
      const readAt = new Date().toISOString();
      items = items.map((item) => (item.read_at ? item : { ...item, read_at: readAt }));
    } catch (reason) {
      error = errorMessage(reason, 'ui.notifications.couldNotMarkRead');
    } finally {
      busy = false;
    }
  }

  async function openItem(item: NotificationItem) {
    open = false;
    if (!item.read_at) {
      const readAt = new Date().toISOString();
      items = items.map((entry) => (entry.id === item.id ? { ...entry, read_at: readAt } : entry));
      unreadCount = Math.max(0, unreadCount - 1);
      try {
        const response = await api.markNotificationsRead([item.id]);
        unreadCount = response.unread_count;
      } catch {
        // Keep navigation responsive even if marking read fails transiently.
      }
    }
    dispatch('openNotification', { taskId: item.task_id });
  }

  function itemLabel(item: NotificationItem): string {
    if (item.kind === 'due') return $t('ui.notifications.itemDue', { title: item.task_title });
    if (item.kind === 'unblocked_due') {
      return $t('ui.notifications.itemUnblockedDue', { title: item.task_title });
    }
    if (item.kind === 'unblocked_overdue') {
      return $t('ui.notifications.itemUnblockedOverdue', { title: item.task_title });
    }
    if (item.extra_count > 0) {
      return $t('ui.notifications.itemUnblockedGroup', {
        title: item.task_title,
        count: item.extra_count
      });
    }
    return $t('ui.notifications.itemUnblocked', { title: item.task_title });
  }

  onMount(() => {
    void refresh(false);
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') void refresh(false);
    };
    const onChanged = () => {
      void refresh(false);
    };
    const timer = window.setInterval(refreshWhenVisible, 60_000);
    document.addEventListener('visibilitychange', refreshWhenVisible);
    window.addEventListener('next-task:notifications-changed', onChanged);

    return () => {
      window.clearInterval(timer);
      document.removeEventListener('visibilitychange', refreshWhenVisible);
      window.removeEventListener('next-task:notifications-changed', onChanged);
    };
  });
</script>

<div class="notifications-menu">
  <button
    type="button"
    class="bell-button"
    class:active={open}
    aria-label={unreadCount > 0
      ? $t('ui.notifications.bellUnreadLabel', { count: unreadCount })
      : $t('ui.notifications.bellLabel')}
    aria-expanded={open}
    aria-controls={open ? 'notifications-popover' : undefined}
    title={$t('ui.notifications.bellLabel')}
    on:click={toggle}
  >
    <svg viewBox="0 0 24 24" aria-hidden="true">
      <path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
      <path d="M13.73 21a2 2 0 0 1-3.46 0" />
    </svg>
    {#if unreadCount > 0}
      <span class="bell-badge">{unreadCount > 99 ? '99+' : unreadCount}</span>
    {/if}
  </button>

  {#if open}
    <div
      id="notifications-popover"
      use:dismissible={() => (open = false)}
      class="notifications-popover"
      role="dialog"
      aria-label={$t('ui.notifications.heading')}
    >
      <div class="popover-header">
        <strong>{$t('ui.notifications.heading')}</strong>
        {#if unreadCount > 0}
          <button type="button" class="mark-read-button" disabled={busy} on:click={markAllRead}>
            {$t('ui.notifications.markAllRead')}
          </button>
        {/if}
      </div>

      {#if error}<p class="error" role="alert">{$text(error)}</p>{/if}

      {#if loading && !items.length}
        <p class="empty-state">{$t('ui.notifications.loadingList')}</p>
      {:else if !items.length}
        <p class="empty-state">{$t('ui.notifications.empty')}</p>
      {:else}
        <ul class="notifications-list">
          {#each items as item (item.id)}
            <li>
              <button
                type="button"
                class:unread={!item.read_at}
                aria-label={$t('ui.notifications.openTask', { title: item.task_title })}
                on:click={() => void openItem(item)}
              >
                <span class="item-label">{itemLabel(item)}</span>
                <small>{formatRelativeTime(item.created_at)}</small>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</div>

<style>
  .notifications-menu {
    position: relative;
    flex: 0 0 auto;
  }

  .bell-button {
    position: relative;
    display: grid;
    width: 2.35rem;
    height: 2.35rem;
    place-items: center;
    border: 1px solid #cbc8be;
    border-radius: .55rem;
    background: #fff;
    color: var(--ink);
    padding: 0;
  }

  .bell-button:hover,
  .bell-button.active {
    border-color: var(--forest);
    background: #f5f8f5;
    color: var(--forest);
  }

  .bell-button svg {
    width: 1.15rem;
    height: 1.15rem;
    fill: none;
    stroke: currentColor;
    stroke-linecap: round;
    stroke-linejoin: round;
    stroke-width: 1.9;
  }

  .bell-badge {
    position: absolute;
    top: -.35rem;
    right: -.35rem;
    display: grid;
    min-width: 1.15rem;
    height: 1.15rem;
    place-items: center;
    border: 2px solid var(--paper);
    border-radius: 999px;
    background: var(--forest);
    color: #fff;
    padding: 0 .22rem;
    font-size: .62rem;
    font-weight: 800;
    line-height: 1;
    font-variant-numeric: tabular-nums;
  }

  .notifications-popover {
    position: absolute;
    top: calc(100% + .5rem);
    right: 0;
    z-index: 35;
    width: min(23rem, calc(100vw - 2rem));
    max-height: min(26rem, calc(100vh - 6rem));
    overflow-y: auto;
    border: 1px solid var(--line);
    border-radius: .75rem;
    background: var(--paper);
    box-shadow: 0 .75rem 2rem rgba(31, 37, 33, .16);
    padding: .85rem;
    color: var(--ink);
  }

  .popover-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .75rem;
    margin-bottom: .6rem;
  }

  .popover-header strong {
    font-size: .92rem;
  }

  .mark-read-button {
    border: 0;
    background: transparent;
    color: var(--forest-2);
    padding: .15rem .25rem;
    font-size: .76rem;
    font-weight: 750;
  }

  .mark-read-button:hover:not(:disabled) {
    text-decoration: underline;
    text-underline-offset: .12rem;
  }

  .empty-state {
    margin: .5rem 0;
    color: var(--muted);
    font-size: .84rem;
    text-align: center;
  }

  .notifications-list {
    display: grid;
    gap: .35rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .notifications-list button {
    display: grid;
    width: 100%;
    gap: .2rem;
    border: 1px solid #e6e1d6;
    border-radius: .55rem;
    background: #fff;
    color: var(--ink);
    padding: .55rem .65rem;
    text-align: left;
  }

  .notifications-list button.unread {
    border-left: 3px solid var(--forest);
    background: #f4f8f5;
  }

  .notifications-list button:hover {
    border-color: var(--forest-2);
  }

  .item-label {
    font-size: .84rem;
    font-weight: 650;
    line-height: 1.35;
    overflow-wrap: anywhere;
  }

  .notifications-list small {
    color: var(--muted);
    font-size: .74rem;
  }

  @media (max-width: 760px) {
    .notifications-popover {
      position: fixed;
      top: calc(100% + .25rem);
      right: .8rem;
      left: auto;
      width: min(23rem, calc(100vw - 1.6rem));
    }
  }
</style>
