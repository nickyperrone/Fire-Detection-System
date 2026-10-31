// Field Watch's service worker: it only shows push alerts and handles their buttons
// (docs/13-notifications.md#push). It caches nothing and does not touch the app's pages.

const es = (self.navigator.language || "es").toLowerCase().startsWith("es");
const TEXT = es
  ? {
      open: "Abrir",
      mute: "🔕 Desuscribirme",
      muted: "🔕 Listo: no te aviso más de eso",
      mutedBody: "Lo cambiás en Notificaciones.",
      failed: "No se pudo desuscribir. Probá desde Notificaciones.",
    }
  : {
      open: "Open",
      mute: "🔕 Unsubscribe",
      muted: "🔕 Done: no more of those",
      mutedBody: "You can change it in Notifications.",
      failed: "Could not unsubscribe. Try from Notifications.",
    };

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) =>
  event.waitUntil(self.clients.claim()),
);

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  const actions = [{ action: "open", title: TEXT.open }];
  if (data.unsubscribe) actions.push({ action: "mute", title: TEXT.mute });
  event.waitUntil(
    self.registration.showNotification(data.title || "Field Watch", {
      body: data.body || "",
      // One notification per field: a newer one replaces the older and rings again.
      tag: data.tag || "field-watch",
      renotify: !data.silent,
      silent: Boolean(data.silent),
      // An alert stays until someone looks at it; a distant fire does not insist.
      requireInteraction: !data.silent,
      icon: "/icon.svg",
      data: { url: data.url, unsubscribe: data.unsubscribe },
      actions,
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  const { url, unsubscribe } = event.notification.data || {};
  event.notification.close();

  if (event.action === "mute" && unsubscribe) {
    // One tap, no sign-in: the link carries its own proof (see the unsubscribe route).
    event.waitUntil(
      fetch(unsubscribe, { method: "POST" })
        .then((response) => {
          if (!response.ok) throw new Error("not unsubscribed");
          return self.registration.showNotification(TEXT.muted, {
            body: TEXT.mutedBody,
            tag: "field-watch-muted",
            silent: true,
          });
        })
        .catch(() =>
          self.registration.showNotification(TEXT.failed, {
            tag: "field-watch-muted",
          }),
        ),
    );
    return;
  }

  const target = url || "/";
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then(async (windows) => {
        // The app is already open: take it to the field instead of opening another window.
        for (const window of windows) {
          if (
            new URL(window.url).origin === self.location.origin &&
            "navigate" in window
          ) {
            await window.navigate(target);
            return window.focus();
          }
        }
        return self.clients.openWindow(target);
      }),
  );
});
