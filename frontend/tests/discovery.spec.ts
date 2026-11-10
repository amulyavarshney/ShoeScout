import { expect, test } from "@playwright/test"

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => sessionStorage.clear())
})

test("typed search returns 3-5 in-stock cards and keeps context (T01/T02/T15)", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByText("Ready")).toBeVisible({ timeout: 20_000 })
  await expect(page.getByText(/Demo mode: fictional catalogue/)).toBeVisible()

  await page.getByTestId("text-input").fill("I want red Nike shoes")
  await page.getByTestId("send-button").click()
  await expect(page.getByTestId("results-heading")).toContainText("Matching shoes", { timeout: 20_000 })
  const cards = page.getByTestId("product-card")
  const n = await cards.count()
  expect(n).toBeGreaterThanOrEqual(3)
  expect(n).toBeLessThanOrEqual(5)
  await expect(cards.first()).toContainText("In stock")
  await expect(page.getByTestId("message-assistant").last()).toContainText("red Nike")

  await page.getByTestId("text-input").fill("size 9")
  await page.getByTestId("send-button").click()
  await expect(page.getByTestId("message-user").last()).toContainText("size 9")
  await expect(cards.first()).toContainText("size 9", { timeout: 20_000 })
})

test("product details sheet shows sizes and store availability without a nearest claim (FR-09/FR-12/FR-18)", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByText("Ready")).toBeVisible({ timeout: 20_000 })
  await page.getByTestId("text-input").fill("red shoes")
  await page.getByTestId("send-button").click()
  await expect(page.getByTestId("results-heading")).toContainText("Matching shoes", { timeout: 20_000 })
  await page.getByTestId("product-card").first().getByRole("button", { name: "Details" }).click()
  await expect(page.getByRole("radiogroup", { name: "Size" })).toBeVisible()
  await page.getByRole("radiogroup", { name: "Size" }).getByRole("radio").first().click()
  await expect(page.getByText("Listed alphabetically")).toBeVisible({ timeout: 15_000 })
  await expect(page.getByText("Nearest", { exact: true })).toHaveCount(0)
  await expect(page.getByTestId("use-location")).toBeVisible()
})

test("voice button works with a fake microphone and falls back gracefully in demo mode (FR-01/FR-17)", async ({ page }) => {
  await page.goto("/")
  await expect(page.getByText("Ready")).toBeVisible({ timeout: 20_000 })
  await page.getByTestId("voice-button").click()
  // Demo mode: either browser speech recognition starts (Listening…) or a clear typed-fallback error appears.
  await expect(page.getByText(/Listening…|Type instead|type your request/i).first()).toBeVisible({ timeout: 10_000 })
  await expect(page.getByTestId("text-input")).toBeEnabled()
})
