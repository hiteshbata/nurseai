import { defineConfig } from 'playwright/test'

// RC1 smoke tests only (see tests/e2e/) -- not a comprehensive E2E suite.
// Runs against an already-running app: local dev, RC1 preview, or prod.
// Point PLAYWRIGHT_BASE_URL / PLAYWRIGHT_API_URL at the target before running.
export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: 'list',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:3000',
    trace: 'retain-on-failure',
  },
})
