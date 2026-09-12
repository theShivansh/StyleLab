"use client";

import { useState } from "react";
import { Button, ButtonLink } from "@/components/ui/Button";
import { Sheet } from "@/components/ui/Sheet";
import { cn } from "@/lib/cn";

const LINKS = [
  { href: "#how", label: "How it works" },
  { href: "#honesty", label: "What it won't do" },
  { href: "#privacy", label: "Privacy" },
];

/**
 * Responsive navbar. Links collapse into the Sheet on mobile rather than a bespoke
 * hamburger overlay, so the mobile menu inherits the native dialog's focus trap and Esc
 * handling instead of reimplementing them.
 */
export function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="border-border bg-bg/85 sticky top-0 z-10 border-b backdrop-blur-md">
      <nav
        aria-label="Main"
        className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-5 py-3 md:px-8"
      >
        <a
          href="#top"
          className="text-title flex min-h-[var(--size-touch)] items-center gap-1.5 tracking-tight"
          aria-label="STYLELAB home"
        >
          STYLELAB
          <span aria-hidden="true" className="text-accent text-base">
            ✦
          </span>
        </a>

        <ul className="hidden items-center gap-1 md:flex">
          {LINKS.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                className={cn(
                  "text-ink-muted hover:text-ink hover:bg-surface-muted inline-flex items-center",
                  "min-h-[var(--size-touch)] rounded-[var(--radius-pill)] px-3 text-sm",
                  "transition-colors duration-[var(--duration-functional)]",
                )}
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>

        <div className="flex items-center gap-2">
          <ButtonLink href="/wardrobe" size="md" className="hidden sm:inline-flex">
            Start my wardrobe
          </ButtonLink>
          <Button
            variant="secondary"
            className="md:hidden"
            aria-expanded={menuOpen}
            aria-haspopup="dialog"
            onClick={() => setMenuOpen(true)}
          >
            Menu
          </Button>
        </div>
      </nav>

      <Sheet open={menuOpen} onClose={() => setMenuOpen(false)} title="Menu">
        <ul className="space-y-1">
          {LINKS.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                onClick={() => setMenuOpen(false)}
                className="hover:bg-surface-muted flex min-h-[var(--size-touch)] items-center rounded-[var(--radius-control)] px-3 text-base"
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>
        <ButtonLink
          href="/wardrobe"
          size="lg"
          className="mt-4 w-full"
          onClick={() => setMenuOpen(false)}
        >
          Start my wardrobe
        </ButtonLink>
      </Sheet>
    </header>
  );
}
