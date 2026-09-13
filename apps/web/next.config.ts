import type { NextConfig } from "next";

/**
 * Response headers, added in S11.
 *
 * This file was `{ /* config options here *\/ }` until the release audit looked at it. The
 * product serves private photographs of the inside of people's homes and had no
 * `Content-Security-Policy`, no `frame-ancestors`, and no `nosniff` — every default a
 * browser applies when a site says nothing, which are the permissive ones.
 *
 * The API origin has to appear in two directives because the browser talks to it directly:
 * `connect-src` for the fetches, and `img-src` because a wardrobe image is an `<img src>`
 * pointing at a signed capability URL on the API (docs/SECURITY-PRIVACY.md). Read from
 * `NEXT_PUBLIC_API_URL` so a deployment that points the web app at a different API does not
 * also have to remember to edit a policy.
 */
const apiOrigin = (() => {
  const configured = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  try {
    return new URL(configured).origin;
  } catch {
    // A malformed value is caught properly by the zod schema in src/lib/config.ts, which
    // runs in the application. Here it must not take the build down — a header that falls
    // back to same-origin is wrong in a visible, debuggable way.
    return "'self'";
  }
})();

/**
 * Two relaxations that exist only while `next dev` is running, and must never ship.
 *
 * Found by loading the page rather than by reasoning about it: the first strict policy
 * written here rendered a blank screen, and the console said why — *"eval() is not
 * supported in this environment... React requires eval() in development mode"*. Dev React
 * uses it to rebuild stack traces across environments; production React never does. The
 * websocket is Fast Refresh.
 *
 * Gated on `NODE_ENV` rather than on a flag, because `next build` sets it to `production`
 * and there is nothing to remember.
 */
const isDev = process.env.NODE_ENV !== "production";
const devScript = isDev ? " 'unsafe-eval'" : "";
const devConnect = isDev ? " ws: http://localhost:*" : "";

const csp = [
  "default-src 'self'",
  // Next inlines its bootstrap and its streamed flight data as `<script>` elements, so
  // `'unsafe-inline'` is required until a nonce is plumbed through middleware. Named rather
  // than quietly omitted: this is the one directive in the list that is weaker than it
  // looks, and the nonce is the follow-up (blocker B21).
  `script-src 'self' 'unsafe-inline'${devScript}`,
  // Tailwind emits a stylesheet, but `app/layout.tsx` also carries a `<noscript><style>`
  // that makes reveal animations visible with JavaScript off. That is a deliberate
  // accessibility fallback and it is inline.
  "style-src 'self' 'unsafe-inline'",
  // `data:` for the extraction preview the browser renders before an upload completes;
  // `blob:` for the object URLs the picker creates. Both are same-document by nature.
  `img-src 'self' data: blob: ${apiOrigin}`,
  // `next/font` self-hosts Google fonts at build time, so no external font origin.
  "font-src 'self'",
  `connect-src 'self' ${apiOrigin}${devConnect}`,
  // The product has no embeds, no plugins, and no reason to be framed. `frame-ancestors`
  // is the one that stops a clickjacking overlay over somebody's wardrobe.
  "frame-ancestors 'none'",
  "frame-src 'none'",
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "upgrade-insecure-requests",
].join("; ");

const nextConfig: NextConfig = {
  // The version of Next a site runs is not information a visitor needs and is information
  // somebody scanning for a known bug does.
  poweredByHeader: false,

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Content-Type-Options", value: "nosniff" },
          // Redundant beside `frame-ancestors` for any current browser, and free.
          { key: "X-Frame-Options", value: "DENY" },
          // A wardrobe URL carries an outfit id. Sending a full URL to a third party on an
          // outbound link — the trend citations on the result screen are exactly that —
          // would leak it. Origin only, and only over HTTPS.
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // Nothing in the product uses any of these. A `capture` attribute on the file
          // input would need `camera=(self)`; there is not one, and the accept list is a
          // plain MIME allow-list.
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
          },
          // Two years, subdomains included. Harmless over plain HTTP — browsers ignore it —
          // so it does not need to be conditional on the environment.
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
