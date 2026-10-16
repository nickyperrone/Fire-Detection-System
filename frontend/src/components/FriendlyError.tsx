"use client";

/** What a person sees when the app breaks: no codes, no stack, a way back. It does not use the
 * app's providers, so it works even when they are what broke; the language is the browser's. */
export function FriendlyError({ onRetry }: { onRetry?: () => void }) {
  const es = !(
    typeof navigator !== "undefined" && !navigator.language.startsWith("es")
  );
  return (
    <main
      style={{
        minHeight: "100dvh",
        display: "grid",
        placeItems: "center",
        padding: 24,
        textAlign: "center",
        background: "#0b0e13",
        color: "#e2e8f0",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div style={{ maxWidth: 360 }}>
        {/* eslint-disable-next-line @next/next/no-img-element -- a tiny static SVG */}
        <img src="/icon.svg" alt="" width={56} height={56} />
        <h1 style={{ fontSize: 22, margin: "16px 0 8px" }}>
          {es ? "Algo no salió bien" : "Something went wrong"}
        </h1>
        <p style={{ color: "#94a3b8", lineHeight: 1.5 }}>
          {es
            ? "No es tu culpa. Probá de nuevo en un momento; tus campos y alertas siguen funcionando."
            : "It is not your fault. Try again in a moment; your fields and alerts keep working."}
        </p>
        <button
          onClick={() => (onRetry ? onRetry() : window.location.assign("/"))}
          style={{
            display: "inline-block",
            marginTop: 20,
            padding: "12px 22px",
            borderRadius: 16,
            background: "#5bc7e8",
            color: "#0b0e13",
            fontWeight: 600,
            border: "none",
            cursor: "pointer",
            fontSize: 16,
          }}
        >
          {es ? "Reintentar" : "Try again"}
        </button>
      </div>
    </main>
  );
}
