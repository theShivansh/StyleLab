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
    <html lang="en">
      <body className={`${geistSans.variable} ${geistMono.variable}`}>
        <a href="#main" className="sr-only focus:not-sr-only">
          Skip to content
        </a>
        <main id="main">{children}</main>
      </body>
    </html>
  );
}
