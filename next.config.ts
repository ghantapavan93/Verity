import type { NextConfig } from "next";

// The browser's protections on every page, whatever edge is in front: Caddy set them (deploy/cloud/Caddyfile), but a
// Cloudflare Tunnel, the workstation's edge, sets none (observed on the live site, 2026-10-13). The API sends the same
// set (backend app/main.py SECURITY_HEADERS). A page's Content-Security-Policy is src/proxy.ts's, with its script nonce,
// and takes the place of the one here (checked on a production build, 2026-10-30); this one stays on what the proxy does
// not serve, the files in public/ and Next's built files.
export const SECURITY_HEADERS = [
  { key: "Strict-Transport-Security", value: "max-age=31536000" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
];

const STATIC_EXPORT = process.env.NEXT_PUBLIC_EXPORT === "state";

const nextConfig: NextConfig = {
  // The floating dev-tools badge sits where the rail avatar lives; keep dev renders honest.
  devIndicators: false,
  // No response names the server's software.
  poweredByHeader: false,
  // A static export has no server to send headers (its host sets them), and Next refuses headers() there.
  ...(STATIC_EXPORT ? {} : { headers: async () => [{ source: "/:path*", headers: SECURITY_HEADERS }] }),
  // The browser flows build into their own directory (playwright.config.ts sets NEXT_DIST_DIR), so running them on the
  // machine that serves the published build no longer overwrites the bundle `next start` is serving from .next.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // The public artifact: /state alone as a static site (backend/scripts/export_state.py builds it). No server, API, store
  // or model behind it; its record is a file beside the page, made from the committed experiment record.
  ...(STATIC_EXPORT ? { output: "export" as const, distDir: "out-state" } : {}),
};

export default nextConfig;
