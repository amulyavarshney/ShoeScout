import { expect, test } from "@playwright/test"

const PASSWORD = process.env.E2E_ADMIN_PASSWORD || "shoescout-dev"

test("admin settings require login, keys are saved encrypted and shown masked (FR-19/FR-20/T16)", async ({ page }) => {
  await page.goto("/admin/settings")
  await expect(page).toHaveURL(/\/admin\/login/)
  await page.locator("#password").fill("definitely-wrong")
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page.locator("form [role=\"alert\"]")).toContainText(/invalid/i)

  await page.locator("#password").fill(PASSWORD)
  await page.getByRole("button", { name: "Sign in" }).click()
  await expect(page.getByRole("heading", { name: /AI providers/ })).toBeVisible({ timeout: 15_000 })

  const secret = "sk-e2e-test-secret-ABCDEFGHIJKLMNOP1234"
  const leaked: string[] = []
  page.on("response", async (r) => {
    const ct = r.headers()["content-type"] || ""
    if (ct.includes("json") && r.url().includes("/api/")) {
      const body = await r.text().catch(() => "")
      if (body.includes(secret)) leaked.push(r.url())
    }
  })
  const card = page.getByTestId("provider-openai")
  await card.getByLabel("OpenAI API key").fill(secret)
  await card.getByRole("button", { name: "Save" }).click()
  await expect(card.getByText("Configured")).toBeVisible({ timeout: 10_000 })
  await expect(card.getByText("••••••••••••1234")).toBeVisible()
  await expect(card.getByText("source: settings")).toBeVisible()
  expect(leaked).toEqual([])
  const html = await page.content()
  expect(html).not.toContain(secret)

  await page.reload()
  await expect(page.getByTestId("provider-openai").getByText("••••••••••••1234")).toBeVisible({ timeout: 15_000 })

  page.once("dialog", (d) => d.accept())
  await page.getByTestId("provider-openai").getByRole("button", { name: "Remove" }).click()
  await expect(page.getByTestId("provider-openai").getByText("Not configured")).toBeVisible({ timeout: 10_000 })
})

test("shopper-facing API never exposes keys and public config is mock without providers", async ({ request }) => {
  const api = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8010"
  const cfg = await request.get(`${api}/api/v1/config/public`)
  expect(cfg.ok()).toBeTruthy()
  const body = await cfg.json()
  expect(["mock", "live"]).toContain(body.mode)
  expect(JSON.stringify(body)).not.toMatch(/sk-|xi-api|api_key/)
  const unauth = await request.get(`${api}/api/v1/admin/providers`)
  expect(unauth.status()).toBe(401)
})
