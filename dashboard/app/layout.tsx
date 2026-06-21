import type { Metadata } from "next";
import Link from "next/link";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Contig Dashboard",
  description: "Inspect verified, self-healed, reproducible bioinformatics runs.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col bg-background text-foreground">
        <header className="border-b">
          <nav
            aria-label="Primary"
            className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-3"
          >
            <Link
              href="/runs"
              className="flex items-center gap-2 font-semibold tracking-tight"
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src="/logo.svg" alt="" aria-hidden="true" className="h-6 w-auto" />
              <span>Contig</span>
            </Link>
            <div className="flex items-center gap-4 text-sm text-muted-foreground">
              <Link href="/runs" className="hover:text-foreground">
                Runs
              </Link>
              <Link href="/eval" className="hover:text-foreground">
                Detector
              </Link>
            </div>
          </nav>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
