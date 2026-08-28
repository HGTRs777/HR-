import { expect, test } from '@playwright/test'

function captureBrowserErrors(page: import('@playwright/test').Page): string[] {
  const errors: string[] = []
  page.on('console', (message) => { if (message.type() === 'error') errors.push(message.text()) })
  page.on('pageerror', (error) => errors.push(error.message))
  return errors
}

async function solveHumanCheck(page: import('@playwright/test').Page): Promise<void> {
  const targetStyle = await page.locator('.puzzle-target').getAttribute('style')
  const target = Number(targetStyle?.match(/calc\((\d+)%/)?.[1] ?? 0)
  await page.getByRole('slider', { name: '滑动拼图位置' }).fill(String(target))
  await expect(page.getByText('验证通过')).toBeVisible()
}

test('employee query, clarification/refusal and responsive workspace are integrated', async ({ page, request }, testInfo) => {
  const browserErrors = captureBrowserErrors(page)
  await page.addInitScript((sessionId) => localStorage.setItem('hr-policy-client-session-id', sessionId), `task7-e2e-${testInfo.project.name}`)
  const health = await request.get('http://127.0.0.1:5000/api/v1/health')
  expect(health.ok()).toBeTruthy()

  await page.goto('/')
  await solveHumanCheck(page)
  await page.getByRole('button', { name: '登录员工端', exact: true }).click()
  await expect(page.getByRole('heading', { name: '每条结论，都能点回制度原文' })).toBeVisible()
  await page.getByRole('button', { name: '年假如何计算？', exact: true }).click()
  await page.getByRole('button', { name: '发送问题', exact: true }).click()
  await expect(page.getByText(/回答前先确认一个关键条件|证据已验证|仅展示本地证据/).first()).toBeVisible()

  if (testInfo.project.name === 'mobile-edge') {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
    expect(overflow).toBeFalsy()
  }
  expect(browserErrors).toEqual([])
})

test('HR dashboard loads policies, analytics and feedback governance', async ({ page }) => {
  const browserErrors = captureBrowserErrors(page)
  const username = process.env.E2E_ADMIN_USERNAME ?? 'admin'
  const password = process.env.E2E_ADMIN_PASSWORD ?? '88888888'

  await page.goto('/admin')
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await solveHumanCheck(page)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '制度生命周期与可信度控制台' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '问答数据洞察' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '反馈闭环与回归' })).toBeVisible()
  await expect(page.getByText('LEAVE-001', { exact: true }).first()).toBeVisible()

  if (page.viewportSize()?.width === 393) {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
    expect(overflow).toBeFalsy()
  }
  expect(browserErrors).toEqual([])
})
