import type { Metadata } from "next";

// Self-hosted font files (no third-party font CDN at build or run time).
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";
import "@fontsource/ibm-plex-mono/400.css";
import "@fontsource/ibm-plex-mono/500.css";
import "@fontsource/source-serif-4/400.css";
import "@fontsource/source-serif-4/500.css";
import "@fontsource/source-serif-4/400-italic.css";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Sageboard — Your data. Your questions. Clear decisions.",
    template: "%s · Sageboard",
  },
  description:
    "Sageboard is an autonomous AI data analyst: ask business questions in plain language and get validated SQL, charts and evidence-backed insights.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full">
      <body className="flex min-h-full flex-col">{children}</body>
    </html>
  );
}
