import { defineConfig, devices } from "@playwright/test";

/**
 * Playwright e2e configuration.
 *
 * This is a real, runnable smoke suite (DR-F4). The `webServer` block serves
 * the already-built SPA with `vite preview` and waits for it to accept
 * connections, so `npm run test:e2e` is self-contained and fast (no cold dev
 * server). Run `npm run build` first (CI does this in the previous job step).
 *
 * The smoke test loads the SPA: it verifies the app boots, redirects to the
 * Broker Status page, and renders the "Broker Status" heading. It intentionally
 * does not require a live backend — the heading renders regardless of broker
 * connectivity — so the test catches build/runtime regressions in the frontend
 * itself.
 */
export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: "http://127.0.0.1:5173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run preview -- --host 127.0.0.1 --port 5173 --strictPort",
    url: "http://127.0.0.1:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
  },
});
