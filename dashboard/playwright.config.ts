import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;

/**
 * The smoke test runs against the real static export, built in mock mode into
 * out-mock/ and served by a small static server that applies the same clean-URL
 * rewrite CloudFront will (`/login/` -> `/login/index.html`).
 */
export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results/artifacts",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  use: {
    baseURL: `http://127.0.0.1:${PORT}`,
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } }],
  webServer: {
    command: "npm run build:mock && npm run serve:mock",
    url: `http://127.0.0.1:${PORT}/login/`,
    reuseExistingServer: !process.env.CI,
    timeout: 240_000,
  },
});
