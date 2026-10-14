import type { Metadata, Viewport } from "next";

import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Field Watch",
  // In Spanish, like the first render (LocaleProvider): it is what a shared link shows.
  description:
    "Tus campos, vigilados por satélite: fuegos cerca, cuándo pulverizar, rayos y clima adverso, con alertas por mail o Telegram.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
  themeColor: "#0b0e13",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="es">
      <body className="font-sans antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
