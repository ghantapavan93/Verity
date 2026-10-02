import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    // The browser flows build here (playwright.config.ts); until this line, linting after the flows had run
    // linted their build output and failed.
    ".next-e2e/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // The API is Python; its virtualenv carries JavaScript of its own that is not ours to lint.
    "backend/**",
  ]),
  // The boundary the constitution draws, enforced: components render what the API decided. They reach the API
  // through src/lib/api.ts and its types through src/lib/types.ts, never through a raw fetch, a raw event
  // stream, or the generated schema. An exception is written next to its reason with a disable comment.
  {
    files: ["src/components/**/*.{ts,tsx}", "src/app/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-globals": [
        "error",
        { name: "fetch", message: "Components do not call the API themselves; add the call to src/lib/api.ts." },
        { name: "EventSource", message: "Streams are followed in src/lib/api.ts, not in components." },
      ],
      "no-restricted-imports": [
        "error",
        { patterns: [{ group: ["**/api.schema", "**/api.schema.ts"], message: "Import API types from src/lib/types.ts, not the generated schema." }] },
      ],
    },
  },
]);

export default eslintConfig;
