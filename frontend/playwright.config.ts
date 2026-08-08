import { defineConfig } from 'playwright/test'

// This process is a plain `node` invocation, not `next dev` -- Next's own
// .env.local loading doesn't apply here, so PLAYWRIGHT_TEST_USER_EMAIL/
// PASSWORD (and PLAYWRIGHT_BASE_URL/PLAYWRIGHT_API_URL, if set there instead
// of the shell) need loading explicitly. Missing file is fine -- CI sets
// these as real environment variables instead.
try {
  process.loadEnvFile('.env.local')
} catch {}

// RC1 smoke tests only (see tests/e2e/) -- not a comprehensive E2E suite.
// Runs against an already-running app: local dev, RC1 preview, or prod.
// Point PLAYWRIGHT_BASE_URL / PLAYWRIGHT_API_URL at the target before running.
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  // Default 30s is too tight against a cold `next dev` server -- the first
  // hit after starting it has to wait on Turbopack's on-demand compile of
  // shared framework chunks (webpack.js/layout.js/main-app.js), which alone
  // has been observed taking ~27-31s. A warm server or a `next build` target
  // finishes in a few seconds either way, so this only matters cold.
  timeout: 60_000,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
})
