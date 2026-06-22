import { defineConfig, devices } from "@playwright/test";

// Smoke tests for the dashboard. They load each route and exercise the verdict
// dropdown, which is exactly the class of runtime error (Base UI render rules)
// that tsc and `next build` do not catch. Playwright starts the dev server.
//
// PW_PORT overrides the port (default 3000) so the suite can run on an isolated
// dev server when another app already holds 3000. The webServer starts a dev
// server on that port and reuses one if it is already up.
const PORT = process.env.PW_PORT ?? "3000";
const BASE_URL = `http://localhost:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  // Synthetic run fixtures are copied into the runs directory before the suite
  // and removed after, so they never clutter a real dashboard.
  globalSetup: "./e2e/global-setup.ts",
  globalTeardown: "./e2e/global-teardown.ts",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `npm run dev -- --port ${PORT}`,
    url: BASE_URL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
