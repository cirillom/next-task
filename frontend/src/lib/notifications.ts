import { LocalizedError, message } from './i18n';

export type PushSupportStatus =
  | 'unsupported'
  | 'insecure'
  | 'ios-install-required'
  | 'denied'
  | 'granted'
  | 'default';

export function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replaceAll('-', '+').replaceAll('_', '/');
  const raw = atob(base64);
  const bytes = new Uint8Array(new ArrayBuffer(raw.length));
  for (let index = 0; index < raw.length; index += 1) {
    bytes[index] = raw.charCodeAt(index);
  }
  return bytes;
}

export function detectBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  } catch {
    return 'UTC';
  }
}

export function isIosLike(
  nav: { userAgent?: string; platform?: string; maxTouchPoints?: number } | undefined =
    typeof navigator !== 'undefined' ? navigator : undefined
): boolean {
  if (!nav) return false;
  const ua = nav.userAgent ?? '';
  if (/iPad|iPhone|iPod/.test(ua)) return true;
  return nav.platform === 'MacIntel' && (nav.maxTouchPoints ?? 0) > 1;
}

export function isStandaloneDisplay(
  win: { matchMedia?: (query: string) => { matches: boolean } } | undefined =
    typeof window !== 'undefined' ? window : undefined,
  nav: { standalone?: boolean } | undefined =
    typeof navigator !== 'undefined' ? (navigator as Navigator & { standalone?: boolean }) : undefined
): boolean {
  return Boolean(nav?.standalone || win?.matchMedia?.('(display-mode: standalone)').matches);
}

export function pushSupportStatus(env?: {
  isSecureContext?: boolean;
  hasServiceWorker?: boolean;
  hasPushManager?: boolean;
  permission?: NotificationPermission | null;
  iosLike?: boolean;
  standalone?: boolean;
}): PushSupportStatus {
  const secure =
    env?.isSecureContext ?? (typeof window !== 'undefined' ? window.isSecureContext : false);
  const hasSW =
    env?.hasServiceWorker ?? (typeof navigator !== 'undefined' && 'serviceWorker' in navigator);
  const hasPush =
    env?.hasPushManager ?? (typeof window !== 'undefined' && 'PushManager' in window);
  const ios = env?.iosLike ?? isIosLike();
  const standalone = env?.standalone ?? isStandaloneDisplay();
  const permission =
    env?.permission !== undefined
      ? env.permission
      : typeof Notification !== 'undefined'
        ? Notification.permission
        : null;

  if (!secure) return 'insecure';
  if (ios && !standalone) return 'ios-install-required';
  if (!hasSW || !hasPush || permission === null) return 'unsupported';
  return permission;
}

export async function sha256Hex(value: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, '0')).join('');
}

export async function getCurrentPushEndpoint(): Promise<string | null> {
  if (
    typeof navigator === 'undefined' ||
    !('serviceWorker' in navigator) ||
    typeof window === 'undefined' ||
    !('PushManager' in window)
  ) {
    return null;
  }
  try {
    const registration = await navigator.serviceWorker.getRegistration('/');
    const subscription = await registration?.pushManager.getSubscription();
    return subscription?.endpoint ?? null;
  } catch {
    return null;
  }
}

function sameKey(existing: ArrayBuffer | null | undefined, expected: Uint8Array): boolean {
  if (!existing) return true;
  const bytes = new Uint8Array(existing);
  return bytes.length === expected.length && bytes.every((byte, index) => byte === expected[index]);
}

export async function subscribeCurrentDevice(
  vapidPublicKey: string
): Promise<{ endpoint: string; p256dh: string; auth: string }> {
  if (
    typeof navigator === 'undefined' ||
    !('serviceWorker' in navigator) ||
    typeof window === 'undefined' ||
    !('PushManager' in window) ||
    typeof Notification === 'undefined'
  ) {
    throw new LocalizedError(message('ui.notifications.notSupported'));
  }

  let permission = Notification.permission;
  if (permission === 'default') {
    permission = await Notification.requestPermission();
  }
  if (permission !== 'granted') {
    throw new LocalizedError(message('ui.notifications.permissionDenied'));
  }

  let registration = await navigator.serviceWorker.getRegistration('/');
  if (!registration) {
    registration = await navigator.serviceWorker.register('/sw.js');
  }
  registration = await navigator.serviceWorker.ready;

  const applicationServerKey = urlBase64ToUint8Array(vapidPublicKey);
  let subscription = await registration.pushManager.getSubscription();
  if (subscription && !sameKey(subscription.options?.applicationServerKey, applicationServerKey)) {
    await subscription.unsubscribe().catch(() => false);
    subscription = null;
  }
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey
    });
  }
  const serialized = subscription.toJSON();
  const endpoint = subscription.endpoint;
  const p256dh = serialized.keys?.p256dh;
  const auth = serialized.keys?.auth;
  if (!endpoint || !p256dh || !auth) {
    throw new LocalizedError(message('ui.notifications.couldNotSubscribeThisBrowser'));
  }
  return { endpoint, p256dh, auth };
}

export async function unsubscribeCurrentDevice(): Promise<string | null> {
  if (
    typeof navigator === 'undefined' ||
    !('serviceWorker' in navigator) ||
    typeof window === 'undefined' ||
    !('PushManager' in window)
  ) {
    return null;
  }
  try {
    const registration = await navigator.serviceWorker.getRegistration('/');
    const subscription = await registration?.pushManager.getSubscription();
    if (!subscription) return null;
    const endpoint = subscription.endpoint;
    await subscription.unsubscribe().catch(() => false);
    return endpoint;
  } catch {
    return null;
  }
}

export function parseTaskHashTarget(urlOrHash: string): number | null {
  const hashIndex = urlOrHash.indexOf('#/');
  const fragment =
    hashIndex >= 0 ? urlOrHash.slice(hashIndex + 2) : urlOrHash.replace(/^\/?#?\/?/, '');
  const [view, query = ''] = fragment.split('?', 2);
  if (view !== 'tasks') return null;
  const raw = new URLSearchParams(query).get('task');
  const parsed = raw ? Number(raw) : NaN;
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
}

export function emitNotificationsChanged(): void {
  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event('next-task:notifications-changed'));
  }
}
