import { Suspense } from "react";

import { FieldWatchApp } from "@/components/FieldWatchApp";

export default function Home() {
  // The app reads its state from the URL, which is only known in the browser.
  return (
    <Suspense>
      <FieldWatchApp />
    </Suspense>
  );
}
