import { test, expect } from 'playwright/test'

const apiBaseURL = process.env.PLAYWRIGHT_API_URL || 'http://localhost:8000'

test('/health returns 200', async ({ request }) => {
  const response = await request.get(`${apiBaseURL}/health`)
  expect(response.status()).toBe(200)

  const body = await response.json()
  expect(body.status).toBeTruthy()
})
