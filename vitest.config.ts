import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

/** Two behaviours no backend test can see are tested here: following a run and restoring state from the URL. */
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  esbuild: { jsx: "automatic" },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
});
