import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The floating dev-tools badge sits where the rail avatar lives; keep dev renders honest.
  devIndicators: false,
  // The browser flows build into their own directory (playwright.config.ts sets NEXT_DIST_DIR), so running them on the
  // machine that serves the published build no longer overwrites the bundle `next start` is serving from .next.
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
