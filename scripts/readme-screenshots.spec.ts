import { test, expect } from "@playwright/test"

const FRONTEND_URL = "http://127.0.0.1:3000"
const SCREENSHOT_DIR = "/Users/bill/code/AI/NL2SQL/docs/screenshots"

test("capture README screenshots", async ({ page }) => {
  await page.setViewportSize({ width: 1512, height: 982 })

  await page.goto(FRONTEND_URL, { waitUntil: "networkidle" })
  await page.screenshot({ path: `${SCREENSHOT_DIR}/home.png`, fullPage: true })

  await page.getByPlaceholder("输入一个业务问题，系统会像分析师一样边推理边给你回答，例如：统计去年各地区的销售总额").fill("统计去年各地区的销售总额")
  await page.getByRole("button", { name: "开始查询" }).click()

  await expect(page.getByText("执行进度")).toBeVisible({ timeout: 30000 })
  await page.getByRole("button", { name: /抽取关键字/ }).click()
  await page.getByRole("button", { name: /生成SQL/ }).click()
  await page.screenshot({ path: `${SCREENSHOT_DIR}/progress.png`, fullPage: true })

  await expect(page.getByText("明细数据")).toBeVisible({ timeout: 40000 })
  await page.getByText("图表解读").scrollIntoViewIfNeeded()
  const sqlToggle = page.getByText("查看 SQL")
  if (await sqlToggle.count()) {
    await sqlToggle.first().click()
  }
  await page.screenshot({ path: `${SCREENSHOT_DIR}/result.png`, fullPage: true })
})
