"use client";

import {
  MutationCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { useState } from "react";

import { FailureToast } from "@/components/FailureToast";
import { LocaleProvider } from "@/i18n/LocaleProvider";
import { reportFailure } from "@/lib/failures";

export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        // Answers change every few minutes at most: coming back to the tab or opening another
        // panel within 30 s reuses them instead of asking the API again.
        defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
        // An action that fails says so in a friendly line, unless its page shows the error where
        // it happened (`meta.inline`).
        mutationCache: new MutationCache({
          onError: (_error, _variables, _context, mutation) => {
            if (!mutation.meta?.inline) reportFailure();
          },
        }),
      }),
  );
  return (
    <QueryClientProvider client={client}>
      <LocaleProvider>
        {children}
        <FailureToast />
      </LocaleProvider>
    </QueryClientProvider>
  );
}
