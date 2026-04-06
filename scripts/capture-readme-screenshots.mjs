import fs from "node:fs/promises"
import path from "node:path"
import { chromium } from "playwright"

const FRONTEND_URL = "http://127.0.0.1:3000"
const SCREENSHOT_DIR = "/Users/bill/code/AI/NL2SQL/docs/screenshots"

async function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

async function main() {
  await fs.mkdir(SCREENSHOT_DIR, { recursive: true })

  const browser = await chromium.launch({ headless: true })
  const page = await browser.newPage({ viewport: { width: 1512, height: 982 }, deviceScaleFactor: 2 })

  await page.goto(FRONTEND_URL, { waitUntil: "networkidle" })
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "home.png"), fullPage: true })

  const textarea = page.getByPlaceholder("输入一个业务问题，系统会像分析师一样边推理边给你回答，例如：统计去年各地区的销售总额")
  await textarea.fill("统计去年各地区的销售总额")
  await page.getByRole("button", { name: "开始查询" }).click()

  await page.getByText("执行进度").waitFor({ timeout: 30000 })
  await page.getByRole("button", { name: /抽取关键字/ }).click()
  await page.getByRole("button", { name: /生成SQL/ }).click()
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "progress.png"), fullPage: true })

  await page.getByText("明细数据").waitFor({ timeout: 40000 })
  const sqlToggle = page.getByText("查看 SQL")
  if (await sqlToggle.count()) {
    await sqlToggle.click()
  }
  const executeToggle = page.getByRole("button", { name: /执行SQL/ })
  if (await executeToggle.count()) {
    await executeToggle.click()
  }
  await wait(1200)
  await page.screenshot({ path: path.join(SCREENSHOT_DIR, "result.png"), fullPage: true })

  await browser.close()
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
