import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The floating dev-tools badge sits where the rail avatar lives; keep dev renders honest.
  devIndicators: false,
  // The browser flows build into their own directory (playwright.config.ts sets NEXT_DIST_DIR), so running them on the
  // machine that serves the published build no longer overwrites the bundle `next start` is serving from .next.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // The public artifact: /state alone as a static site (backend/scripts/export_state.py builds it). No server, API, store
  // or model behind it; its record is a file beside the page, made from the committed experiment record.
  ...(process.env.NEXT_PUBLIC_EXPORT === "state" ? { output: "export" as const, distDir: "out-state" } : {}),
};

export default nextConfig;
