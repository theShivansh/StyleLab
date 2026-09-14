import { z } from "zod";
import { config } from "./config";

/**
 * The caller's identity, as far as the browser is concerned: an opaque token the API minted
 * and signed.
 *
 * ## What this is not
 *
 * Not authentication. `POST /session` hands a token to anyone who asks — there is no
 * password and no verification. Real accounts remain unbuilt (blocker B15) — S11
 * deliberately did not add them, because the phase's own acceptance criterion is that a
 * visitor reaches a composed outfit *with no account and no credentials*. What S11 did
 * instead was rate-limit session creation, so free identities stop being free quota.
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
 * ## Why the token is held in memory as well
 *
 * localStorage is how an identity survives a reload. It is not where the page keeps it. The
 * first version read storage on every request and had no other copy, so in a browser that
 * refuses site storage every single request started a new anonymous user: the upload went to
 * one, the poll for its job to another, the re-read of its garment to a third — and the card
 * said "That item isn't in your wardrobe" about a photograph that had uploaded perfectly.
 * Found on the deployed site, from the API's access log: a `POST /session` before every call.
 *
 * So the token lives in this module for the life of the page, and storage is only asked once.
 *
 * ## Why a promise is cached
 *
 * A cold wardrobe screen fires several requests at once. Without the in-flight promise each
 * one would start its own session, and the user would end up with four empty wardrobes and
 * their photographs spread across them. Renewal shares it for the same reason — see
 * `renewSession`.
 */

const STORAGE_KEY = "stylelab-session-token";

const sessionSchema = z.object({
  user_id: z.string(),
  token: z.string().min(1),
  expires_in: z.number().int().positive(),
});

/** The identity this page is using. Set once, replaced only by a renewal. */
let current: string | null = null;
let inFlight: Promise<string> | null = null;

function read(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    // Private browsing, or storage disabled. The in-memory copy carries the page.
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

function forget(token: string | null): void {
  try {
    // Only the token that was refused. Another tab may already have stored a newer one.
    if (token === null || window.localStorage.getItem(STORAGE_KEY) === token) {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // Already unavailable; `create` does not depend on it.
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

  current = parsed.data.token;
  write(parsed.data.token);
  return parsed.data.token;
}

/** Start a session unless one is already starting, and share the answer. */
function startOnce(): Promise<string> {
  // Cleared either way, so a failure can be retried.
  inFlight ??= create().finally(() => {
    inFlight = null;
  });
  return inFlight;
}

/** The current token, creating a session if there is not one yet. */
export function sessionToken(): Promise<string> {
  if (current) return Promise.resolve(current);

  const stored = read();
  if (stored) {
    current = stored;
    return Promise.resolve(stored);
  }
  return startOnce();
}

/**
 * Replace the token the API just refused — once, however many requests it refused.
 *
 * Called on a 401, which in practice means the token was signed with a key the API no longer
 * holds. `rejected` is the token that request carried, and it is what makes this safe to call
 * from several requests at once. The first caller starts a new session; the rest either join
 * that one or, arriving after it finished, find the token already replaced and use the new
 * one. Without that comparison every concurrent 401 minted its own identity, the last to
 * finish won storage, and requests from the same screen came to belong to different users.
 *
 * The honest outcome of a real 401 is still a new empty wardrobe rather than a screen of
 * failed requests — the photographs are on the server, but nothing in the browser can prove
 * they are ours.
 */
export function renewSession(rejected: string | null): Promise<string> {
  if (current !== null && current !== rejected) return Promise.resolve(current);
  if (inFlight) return inFlight;

  // Another tab may have renewed already; its token is as good as a new one of ours.
  const stored = read();
  if (stored !== null && stored !== rejected) {
    current = stored;
    return Promise.resolve(stored);
  }

  current = null;
  forget(rejected);
  return startOnce();
}

/** Test seam: drop the in-memory identity and the cached promise so each case starts cold. */
export function resetSessionCache(): void {
  current = null;
  inFlight = null;
}
