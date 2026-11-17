import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  oxc: { jsx: { runtime: "automatic" } },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      "@mocks": fileURLToPath(new URL("./mocks", import.meta.url)),
      "@finora/voice": fileURLToPath(new URL("./src/components/voice/index.ts", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: false,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}", "mocks/**/*.test.ts"],
    css: false,
  },
});
