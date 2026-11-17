import type { Metadata, Viewport } from "next";
import { JetBrains_Mono } from "next/font/google";
import { Providers } from "@/components/providers/Providers";
import "./globals.css";

// Downloaded at build time and served from /_next/static (CSP font-src 'self'). Used for numbers only.
const data = JetBrains_Mono({ subsets: ["latin"], variable: "--nf-data", display: "swap" });

export const metadata: Metadata = {
  title: "Data quality · Finora",
  description: "How each department complies with the data rules.",
  robots: { index: false, follow: false },
};

// The theme follows the operating system (CSS `prefers-color-scheme`), so there is no pre-paint script.
export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  colorScheme: "light dark",
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#ffffff" },
    { media: "(prefers-color-scheme: dark)", color: "#0c0c0e" },
  ],
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={data.variable}>
      <body className="bg-bg text-ink antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
