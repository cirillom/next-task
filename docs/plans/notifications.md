# Task notifications

Plan for [#97](https://github.com/cirillom/next-task/issues/97). Add due-date and newly actionable task alerts to the web app. Scheduled events from [#98](https://github.com/cirillom/next-task/issues/98) can use the same delivery path after their date behavior is defined.

## User behavior

| Trigger | First-release behavior |
| --- | --- |
| Due date | One reminder at 09:00 on that calendar date in the user's saved IANA time zone. No retroactive burst when enabling notifications. |
| Timed block expires | Alert when the task actually becomes actionable, within one worker interval. |
| A blocking task is finished, abandoned, or deleted | Alert when its dependent task becomes actionable. Group several newly ready tasks into one alert. |
| Manual unblock | Update the current view immediately; no redundant system push for the action the user just performed. |

Resolve *all* active blocks before alerting. Also require an unfinished, non-abandoned, non-draft task that is eligible for the existing actionable task view; do not announce a parent that still has an unfinished child. If a due task remains blocked, skip its due reminder. When it becomes actionable, show it as due or overdue; push on timed or dependency resolution, while manual resolution is visible in the current view. Recheck these conditions before delivery so a task finished, reblocked, rescheduled, or deleted in the meantime is not announced.

The app's in-app due/ready view is the fallback for denied permissions, unsupported browsers, offline devices, and missed pushes. A push is a prompt to open the authoritative task, not a second copy of task state. Notification clicks open that task; if it no longer exists or belongs to the signed-in user, open the task list.

## Delivery design

1. Extend the existing service worker at `frontend/public/sw.js` with `push` and `notificationclick` handlers. Use persistent `showNotification`; do not use page timers or the `Notification()` constructor for scheduled delivery.
2. Put an explicit Enable reminders control in Settings. On a user click, request permission, subscribe with a VAPID public key, and register that device's subscription through an authenticated API. Show permission/unsupported status and an unsubscribe control. Do not prompt on sign-in.
3. Store one or more subscriptions per user, a per-user enabled flag and time zone, and durable reminder/delivery records. Keep the VAPID private key in protected deployment configuration. Remove this device's subscription on logout; reject subscription changes without an authenticated session. Validate subscription endpoints before sending to prevent the server from being used to reach internal URLs.
4. Run one notifier process in Compose, separate from the web request process. It checks date-based triggers and timed block expiry, and sends committed notification events to each subscribed device. Task mutations record newly actionable candidates in the same transaction as the task change; the notifier sends only after commit. Persist a unique key for each task/trigger transition and claim pending deliveries atomically so restarts or overlapping worker passes cannot create routine duplicates. Retry temporary failures with a limit; discard expired subscriptions.
5. Send a short-lived, localized payload with a task link and title. Treat push-service acceptance as an attempted delivery, not proof the device displayed it. A later task change cannot revoke a push already accepted by a browser push service, so keep its lifetime short.

Use the account language for server-generated text. Preserve date-only task semantics: the saved time zone determines *when* the 09:00 reminder is sent, not the stored due date. Decide how to handle an invalid or missing time zone at subscription time and test daylight-saving boundaries.

The current manifest already requests standalone display. On iOS and iPadOS, explain that Web Push requires adding the app to the Home Screen. Require HTTPS and use feature detection on every browser. Sources: [MDN Push subscription](https://developer.mozilla.org/en-US/docs/Web/API/PushManager/subscribe), [WebKit iOS Web Push](https://webkit.org/blog/13878/), [RFC 8030 delivery lifetime](https://datatracker.ietf.org/doc/html/rfc8030.html).

## Implementation order

1. Add the preference, subscription, and durable delivery schema plus authenticated API. Keep existing tasks and Pomodoro alerts unchanged.
2. Add Settings opt-in and the service-worker handlers. Verify one manually triggered test push before scheduling real task alerts.
3. Add the single notifier process and due-date reminders, then actionable-transition detection for timed and dependency blocks. Reuse the same delivery path for scheduled events later.
4. Add the in-app due/ready view and localized messages; document installation, permission, privacy, and deployment setup.

## Acceptance checks

- Two subscribed devices receive one alert each for one due task or newly actionable task; a different user's device receives none.
- Removing one of several blockers sends nothing. Clearing the last blocker sends once, including when a timer expires without an API request. Reblocking and resolving again can send a new alert.
- Finishing, abandoning, deleting, or rescheduling a task before delivery cancels the stale alert. Multiple newly ready tasks are grouped.
- A due task still blocked at 09:00 does not produce a misleading due alert; it appears when actionable. Repeated worker runs and restarts do not cause routine duplicates.
- Denied permission, unsupported browser, offline device, failed push service, and an expired subscription leave the app usable and the in-app due/ready view accurate.
- Tests cover user isolation, logout/account switching, time zones and daylight-saving boundaries, notification clicks, and current Pomodoro behavior.

Browser push delivery is best effort. Do not present it as a guaranteed alarm or use it for Pomodoro's existing period-end sound behavior.
