import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    ".next/**",
    "out/**",
    "out-mock/**",
    "node_modules/**",
    "test-results/**",
    "playwright-report/**",
    "next-env.d.ts",
    // Third-party audio worklets copied by scripts/voice-assets.mjs (voice builds only).
    "public/voice/**",
  ]),
]);

export default eslintConfig;
