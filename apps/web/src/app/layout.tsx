import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({ variable: "--font-geist-sans", subsets: ["latin"] });
const geistMono = Geist_Mono({ variable: "--font-geist-mono", subsets: ["latin"] });

export const metadata: Metadata = {
  title: "STYLELAB",
  description: "Reads photos of the clothes you own and styles outfits from them.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // The font variable classes belong on <html>, not <body>. Tailwind 4 hoists @theme
    // tokens to :root, so a token defined as `var(--font-geist-sans), ...` is substituted
    // in :root's context — if the variable only exists on a descendant, the token computes
    // to an empty string and every element silently falls back to the UA font stack.
    <html lang="en" className={`${geistSans.variable} ${geistMono.variable}`}>
      <body>
        {/* Reveal animations are progressive enhancement. With JS off, nothing sets
            data-revealed to "true", so force every reveal visible rather than shipping a
            blank page. */}
        <noscript>
          <style>{`[data-revealed],.stagger-word{opacity:1 !important;transform:none !important}`}</style>
        </noscript>
        <a href="#main" className="sr-only focus:not-sr-only">
          Skip to content
        </a>
        <main id="main">{children}</main>
      </body>
    </html>
  );
}
