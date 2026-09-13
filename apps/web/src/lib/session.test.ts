import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { renewSession, resetSessionCache, sessionToken } from "./session";

/**
 * The property every test here circles: **the browser cannot choose which user it is.**
 *
 * It can hold a token or not hold one. It never constructs one, never names a subject, and
 * never sends a user id — the API reads the subject out of its own signature. These tests
 * are mostly about not breaking that by accident while adding convenience.
 */

const KEY = "stylelab-session-token";

function mockSessionResponse(token: string) {
  return {
    ok: true,
    status: 201,
    json: async () => ({ user_id: "user_1", token, expires_in: 2_592_000 }),
  } as Response;
}

beforeEach(() => {
  localStorage.clear();
  resetSessionCache();
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("sessionToken", () => {
  it("creates a session when there is not one and remembers it", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(mockSessionResponse("tok-1"));

    expect(await sessionToken()).toBe("tok-1");

    expect(localStorage.getItem(KEY)).toBe("tok-1");
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy.mock.calls[0]?.[1]).toMatchObject({ method: "POST" });
  });

  it("reuses the stored token without calling the API", async () => {
    localStorage.setItem(KEY, "tok-existing");
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    expect(await sessionToken()).toBe("tok-existing");
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("starts exactly one session for concurrent callers", async () => {
    // The bug this prevents is not subtle. A cold wardrobe screen fires several requests at
    // once; without the shared promise each starts its own session, and the user ends up
    // with four empty wardrobes and their photographs spread across them.
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(mockSessionResponse("tok-1"));

    const tokens = await Promise.all([sessionToken(), sessionToken(), sessionToken()]);

    expect(tokens).toEqual(["tok-1", "tok-1", "tok-1"]);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it("does not send anything that names a user", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch").mockResolvedValue(mockSessionResponse("tok-1"));

    await sessionToken();

    const init = fetchSpy.mock.calls[0]?.[1];
    expect(init?.body).toBeUndefined();
  });

  it("allows a retry after a failed attempt rather than caching the failure", async () => {
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(mockSessionResponse("tok-2"));

    await expect(sessionToken()).rejects.toThrow("offline");
    expect(await sessionToken()).toBe("tok-2");
    expect(fetchSpy).toHaveBeenCalledTimes(2);
  });

  it("refuses a response that does not match the contract", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ user_id: "user_1" }),
    } as Response);

    await expect(sessionToken()).rejects.toThrow(/contract/);
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("refuses an empty token", async () => {
    // A stored empty string would read as "no session" on the next load and as a present
    // credential to the caller, which is the worst of both.
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ user_id: "user_1", token: "", expires_in: 60 }),
    } as Response);

    await expect(sessionToken()).rejects.toThrow(/contract/);
  });

  it("surfaces a non-2xx as an error rather than a token", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue({
      ok: false,
      status: 503,
      json: async () => ({}),
    } as Response);

    await expect(sessionToken()).rejects.toThrow(/503/);
  });
});

describe("renewSession", () => {
  it("discards the stored token and gets a new one", async () => {
    localStorage.setItem(KEY, "tok-stale");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockSessionResponse("tok-fresh"));

    expect(await renewSession()).toBe("tok-fresh");
    expect(localStorage.getItem(KEY)).toBe("tok-fresh");
  });

  it("is what a 401 needs after the API restarts", async () => {
    // Without SESSION_SECRET the API signs with a per-process key, so every token from
    // before a restart stops verifying. A new empty wardrobe is the honest outcome; a
    // screen of failed requests is not.
    localStorage.setItem(KEY, "tok-signed-by-the-old-process");
    vi.spyOn(globalThis, "fetch").mockResolvedValue(mockSessionResponse("tok-new-process"));

    expect(await renewSession()).toBe("tok-new-process");
  });
});
