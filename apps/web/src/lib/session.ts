import { z } from "zod";
import { config } from "./config";

/**
 * The caller's identity, as far as the browser is concerned: an opaque token the API minted
 * and signed.
 *
 * ## What this is not
 *
 * Not authentication. `POST /session` hands a token to anyone who asks — there is no
 * password and no verification. Real accounts arrive with Supabase auth in S11.
 *
 * What matters now is the shape, because the shape is what the ownership boundary rests on.
 * The browser **cannot choose which user it is**: it holds a token or it does not, and the
 * API reads the subject out of its own signature. A `X-User-Id` header would have been
 * three lines and would have made every ownership check in the API decorative.
 *
 * ## Why localStorage rather than a cookie
 *
 * A cookie that works cross-origin in development (`localhost:3000` calling
 * `localhost:8000`) needs `SameSite=None; Secure`, which needs HTTPS, which a local run
 * does not have. A bearer header has neither constraint. The trade is XSS exposure, which
 * is the accepted trade for a pre-auth anonymous token and is called out in
 * `docs/SECURITY-PRIVACY.md`.
 *
 * ## Why a promise is cached
 *
 * A cold wardrobe screen fires several requests at once. Without the in-flight promise each
 * one would start its own session, and the user would end up with four empty wardrobes and
 * their photographs spread across them.
 */

const STORAGE_KEY = "stylelab-session-token";

const sessionSchema = z.object({
  user_id: z.string(),
  token: z.string().min(1),
  expires_in: z.number().int().positive(),
});

let inFlight: Promise<string> | null = null;

function read(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    // Private browsing, or storage disabled. A session per page load still works.
    return null;
  }
}

function write(token: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, token);
  } catch {
    // Nothing to do and nothing to tell the user: the token lives in memory for this page.
  }
}

async function create(): Promise<string> {
  const response = await fetch(`${config.env.NEXT_PUBLIC_API_URL}/api/v1/session`, {
    method: "POST",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(`could not start a session (${response.status})`);

  const parsed = sessionSchema.safeParse(await response.json());
  if (!parsed.success) throw new Error("the session response did not match the contract");

  write(parsed.data.token);
  return parsed.data.token;
}

/** The current token, creating a session if there is not one yet. */
export function sessionToken(): Promise<string> {
  const existing = read();
  if (existing) return Promise.resolve(existing);

  // Shared across concurrent callers, and cleared either way so a failure can be retried.
  inFlight ??= create().finally(() => {
    inFlight = null;
  });
  return inFlight;
}

/**
 * Throw the current token away and start again.
 *
 * Called on a 401, which in practice means the API restarted: without `SESSION_SECRET` set
 * it signs with a per-process key, so every token from before the restart stops verifying.
 * The honest outcome is a new empty wardrobe rather than a screen of failed requests — the
 * photographs are still on the server, but nothing in the browser can prove they are ours.
 */
export async function renewSession(): Promise<string> {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Already unavailable; `create` does not depend on it.
  }
  inFlight = null;
  return sessionToken();
}

/** Test seam: drop the cached promise so each case starts cold. */
export function resetSessionCache(): void {
  inFlight = null;
}
