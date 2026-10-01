"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useSyncExternalStore,
} from "react";

import { type Locale, LOCALES, MESSAGES, type Messages } from "./messages";

const STORAGE_KEY = "field-watch-locale";
const CHANGE_EVENT = "field-watch-locale-change";
// Server render and hydration use this, so the HTML always matches; the browser's saved or
// preferred language is applied right after.
const SERVER_LOCALE: Locale = "es";

// Used when storage is blocked (private windows): the choice lasts for this visit.
let chosenThisVisit: Locale | null = null;

function isLocale(value: string | null): value is Locale {
  return value !== null && (LOCALES as string[]).includes(value);
}

function browserLocale(): Locale {
  if (chosenThisVisit) return chosenThisVisit;
  try {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    if (isLocale(saved)) return saved;
  } catch {
    // Storage blocked; fall back to the browser language.
  }
  return navigator.language.toLowerCase().startsWith("es") ? "es" : "en";
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGE_EVENT, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange);
    window.removeEventListener("storage", onChange);
  };
}

type LocaleContext = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Messages;
};

const Context = createContext<LocaleContext | null>(null);

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const locale = useSyncExternalStore(
    subscribe,
    browserLocale,
    () => SERVER_LOCALE,
  );

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((next: Locale) => {
    chosenThisVisit = next;
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // Not saved; chosenThisVisit keeps it for this visit.
    }
    window.dispatchEvent(new Event(CHANGE_EVENT));
  }, []);

  return (
    <Context.Provider value={{ locale, setLocale, t: MESSAGES[locale] }}>
      {children}
    </Context.Provider>
  );
}

export function useLocale(): LocaleContext {
  const context = useContext(Context);
  if (!context) throw new Error("useLocale must be used inside LocaleProvider");
  return context;
}
