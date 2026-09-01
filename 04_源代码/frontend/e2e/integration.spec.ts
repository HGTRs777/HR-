import { expect, test } from '@playwright/test'

test.afterEach(async ({ page }) => {
  await page.evaluate(async () => {
    const conversationId = localStorage.getItem('hr-policy-e2e-conversation-id')
    if (!conversationId) return
    await fetch(`http://127.0.0.1:5000/api/v1/conversations/${conversationId}`, { method: 'DELETE', credentials: 'include' })
    localStorage.removeItem('hr-policy-e2e-conversation-id')
  }).catch(() => undefined)
})

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

async function createIsolatedConversation(page: import('@playwright/test').Page): Promise<void> {
  const active = page.locator('.conversation-item.active')
  const previousId = await active.getAttribute('data-conversation-id')
  await page.getByRole('button', { name: /新增聊天/ }).click()
  await expect.poll(() => active.getAttribute('data-conversation-id')).not.toBe(previousId)
  const conversationId = await active.getAttribute('data-conversation-id')
  expect(conversationId).toBeTruthy()
  await page.evaluate((id) => localStorage.setItem('hr-policy-e2e-conversation-id', id!), conversationId)
}

test('employee trusted assistant keeps desktop and mobile core flows integrated', async ({ page, request }, testInfo) => {
  const browserErrors = captureBrowserErrors(page)
  await page.addInitScript((sessionId) => localStorage.setItem('hr-policy-client-session-id', sessionId), `task7-e2e-${testInfo.project.name}`)
  const health = await request.get('http://127.0.0.1:5000/api/v1/health')
  expect(health.ok()).toBeTruthy()

  await page.goto('/')
  await solveHumanCheck(page)
  await page.getByRole('button', { name: '登录员工端', exact: true }).click()
  await expect(page.getByRole('heading', { name: '今天想了解什么？' })).toBeVisible()

  if (testInfo.project.name === 'desktop-edge') {
    await expect(page.getByRole('complementary', { name: '历史对话侧边栏' })).toBeVisible()
    const expandSidebar = page.getByRole('button', { name: '展开历史对话侧边栏' })
    if (await expandSidebar.isVisible().catch(() => false)) await expandSidebar.click()
    await createIsolatedConversation(page)
    await page.getByRole('button', { name: '隐藏历史对话侧边栏' }).click()
    await expect(page.locator('.employee-app-shell')).toHaveClass(/sidebar-collapsed/)
    await page.getByRole('button', { name: '展开历史对话侧边栏' }).click()
    await expect(page.locator('.employee-app-shell')).not.toHaveClass(/sidebar-collapsed/)
  } else {
    await page.getByRole('button', { name: '历史对话', exact: true }).click()
    await expect(page.getByRole('complementary', { name: '历史对话侧边栏' })).toHaveClass(/mobile-open/)
    await createIsolatedConversation(page)
    await page.getByRole('button', { name: '隐藏历史对话侧边栏' }).click()
  }

  await page.locator('.hero-question-entry input').fill('年假如何计算？')
  await page.getByRole('button', { name: '立即咨询', exact: true }).click()
  await expect(page.getByText(/需要补充条件|AI 正在反向确认办理条件|证据已验证|仅展示本地证据/).first()).toBeVisible()

  const clarification = page.locator('.conversation-card .clarification-options button').first()
  if (testInfo.project.name === 'desktop-edge' && await clarification.isVisible().catch(() => false)) {
    await clarification.click()
    await expect(page.getByText(/回答可信度|需要补充条件|仅展示本地证据/).first()).toBeVisible()
  }

  if (testInfo.project.name === 'mobile-edge') {
    await page.getByRole('button', { name: '我的办理助手', exact: true }).click()
    await expect(page.getByRole('heading', { name: '我的情况与办理助手' })).toBeVisible()
  } else {
    await expect(page.getByRole('heading', { name: '我的情况与办理助手' })).toBeVisible()
  }

  if (testInfo.project.name === 'mobile-edge') {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
    expect(overflow).toBeFalsy()
  }
  expect(browserErrors).toEqual([])
})

test('HR policy management loads real summary and switches daily and weekly briefings', async ({ page }, testInfo) => {
  test.setTimeout(75_000)
  const browserErrors = captureBrowserErrors(page)
  const username = process.env.E2E_ADMIN_USERNAME ?? 'admin'
  const password = process.env.E2E_ADMIN_PASSWORD ?? '88888888'

  await page.goto('/admin')
  await page.getByLabel('用户名', { exact: true }).fill(username)
  await page.getByLabel('密码', { exact: true }).fill(password)
  await solveHumanCheck(page)
  await page.getByRole('button', { name: '登录', exact: true }).click()
  await expect(page.getByRole('heading', { name: '制度运营工作台' })).toBeVisible()
  await expect(page.getByText('LEAVE-001', { exact: true }).first()).toBeVisible()
  const metrics = page.locator('.management-metric-card')
  await expect(metrics).toHaveCount(4)
  const apiData = await page.evaluate(async () => {
    const load = async (path: string) => (await (await fetch(`http://127.0.0.1:5000/api/v1${path}`, { credentials: 'include' })).json()).data
    const [summary, today, week] = await Promise.all([
      load('/admin/policy-summary'), load('/admin/policy-briefing?range=today'), load('/admin/policy-briefing?range=week'),
    ])
    return { summary, today, week }
  })
  const expectedMetrics = [apiData.summary.pending_issues, apiData.summary.severity_counts.high, apiData.summary.new_this_week, apiData.summary.weak_policy_count]
  for (let index = 0; index < 4; index += 1) {
    await expect(metrics.nth(index).locator('strong').first()).toHaveText(String(expectedMetrics[index]))
    await expect(metrics.nth(index)).not.toContainText('—')
  }
  expect(apiData.today.range).toBe('today')
  expect(apiData.week.range).toBe('week')
  await expect(page.getByText('员工今日主要关注')).toBeVisible()
  await page.getByRole('button', { name: '本周', exact: true }).click()
  await expect(page.getByText(/本周新增 \d+ 个制度问题/)).toBeVisible()
  await page.getByRole('button', { name: '查看完整简报' }).click()
  await expect(page.getByRole('dialog', { name: 'HR 制度周报' })).toBeVisible()
  await expect(page.getByText('本周概览', { exact: true })).toBeVisible()
  const concernCategory = page.locator('.briefing-category-list button').first()
  if (await concernCategory.isVisible().catch(() => false)) {
    const category = (await concernCategory.locator('strong').textContent()) || ''
    await concernCategory.click()
    expect(new URL(page.url()).searchParams.get('module')).toBe('insights')
    expect(new URL(page.url()).searchParams.get('category')).toBe(category)
    await expect(page.getByText(`当前员工关注：${category}`)).toBeVisible()
    await page.getByRole('button', { name: '查看完整简报' }).click()
  }
  const priorityIssue = page.locator('.briefing-issue-link').first()
  if (await priorityIssue.isVisible().catch(() => false)) {
    await priorityIssue.click()
    expect(new URL(page.url()).searchParams.get('module')).toBe('issues')
    expect(new URL(page.url()).searchParams.get('issue')).toBeTruthy()
    await expect(page.locator('.el-drawer:visible')).toContainText('制度问题详情')
    await page.locator('.el-drawer:visible .el-drawer__close-btn').click()
  } else {
    await page.getByRole('dialog', { name: 'HR 制度周报' }).locator('.el-dialog__headerbtn').click()
  }
  const firstPolicy = page.locator('.policy-title-link').first()
  const firstPolicyTitle = await firstPolicy.textContent()
  await firstPolicy.click()
  await expect(page.locator('.el-drawer:visible')).toContainText(firstPolicyTitle || '')
  await page.locator('.el-drawer:visible .el-drawer__close-btn').click()

  const insightSection = page.locator('#admin-module-analytics')
  await insightSection.scrollIntoViewIfNeeded()
  const insightMetrics = insightSection.locator('.hr-insight-metrics .metric-card')
  await expect(insightMetrics).toHaveCount(4)
  const insightData = await page.evaluate(async () => {
    const response = await fetch('http://127.0.0.1:5000/api/v1/admin/policy-insights?days=7', { credentials: 'include' })
    return (await response.json()).data
  })
  const expectedInsightMetrics = [
    insightData.week.consultations,
    insightData.week.pending_issues,
    insightData.week.new_issues,
    insightData.week.resolved_issues,
  ]
  for (let index = 0; index < 4; index += 1) {
    await expect(insightMetrics.nth(index).locator('strong').first()).toHaveText(String(expectedInsightMetrics[index]))
  }
  await expect(insightSection.getByText('本周数据摘要', { exact: true })).toBeVisible()

  const thirtyDayResponse = page.waitForResponse((response) => response.url().includes('/admin/policy-insights?days=30') && response.ok())
  await page.locator('#employee-policy-trend').getByRole('button', { name: '最近 30 天' }).click()
  expect((await (await thirtyDayResponse).json()).data.days).toBe(30)
  await expect(page.locator('#employee-policy-trend').getByRole('button', { name: '最近 30 天' })).toHaveClass(/active/)

  const attentionCategory = page.locator('.attention-change-table button').first()
  if (await attentionCategory.isVisible().catch(() => false)) {
    const category = (await attentionCategory.locator('strong').textContent()) || ''
    await attentionCategory.click()
    expect(new URL(page.url()).searchParams.get('module')).toBe('issues')
    expect(new URL(page.url()).searchParams.get('policyCategory')).toBe(category)
    await expect(page.getByText(`当前员工关注类别：${category}`)).toBeVisible()
    await page.getByRole('button', { name: '数据洞察' }).click()
  }
  const weakPolicy = page.locator('.weak-policy-ranking li > div > button').first()
  if (await weakPolicy.isVisible().catch(() => false)) {
    const weakPolicyTitle = (await weakPolicy.textContent()) || ''
    await weakPolicy.click()
    expect(new URL(page.url()).searchParams.get('module')).toBe('issues')
    expect(new URL(page.url()).searchParams.get('policy')).toBeTruthy()
    if (testInfo.project.name === 'desktop-edge') {
      await page.reload()
      await expect(page.locator('#admin-module-gaps select[aria-label="涉及制度"] option:checked')).toHaveText(weakPolicyTitle)
    }
    const linkedPolicy = page.locator('.highest-priority-card .priority-card-body dd button').first()
    if (await linkedPolicy.isVisible().catch(() => false)) {
      const linkedPolicyTitle = (await linkedPolicy.textContent())?.replace(/[《》]/g, '') || ''
      await linkedPolicy.click()
      expect(new URL(page.url()).searchParams.get('module')).toBe('policies')
      expect(new URL(page.url()).searchParams.get('policy')).toBeTruthy()
      await expect(page.locator('.el-drawer:visible')).toContainText(linkedPolicyTitle)
      await page.locator('.el-drawer:visible .el-drawer__close-btn').click()
    }
  }

  await page.getByRole('button', { name: '问题中心' }).click()
  const issueCenter = page.locator('#admin-module-gaps')
  await issueCenter.scrollIntoViewIfNeeded()
  const issueOverview = issueCenter.locator('.issue-overview button')
  await expect(issueOverview).toHaveCount(4)
  const issueRows = await page.evaluate(async () => {
    const response = await fetch('http://127.0.0.1:5000/api/v1/admin/policy-issues', { credentials: 'include' })
    return (await response.json()).data
  })
  const openIssues = issueRows.filter((item: { status: string }) => item.status !== 'resolved')
  const expectedOverview = [
    openIssues.length,
    openIssues.filter((item: { severity: string }) => item.severity === 'high').length,
    openIssues.filter((item: { severity: string }) => item.severity === 'medium').length,
    openIssues.filter((item: { severity: string }) => item.severity === 'low').length,
  ]
  for (let index = 0; index < 4; index += 1) {
    await expect(issueOverview.nth(index).locator('strong')).toHaveText(String(expectedOverview[index]))
  }
  await expect(issueCenter.getByText('已按处理优先级排序', { exact: true })).toBeVisible()
  if (openIssues.length) {
    await expect(issueCenter.locator('.highest-priority-card h3')).toHaveText(openIssues[0].title)
    await issueCenter.getByRole('button', { name: '查看详情' }).click()
    await expect(page.locator('.el-drawer:visible')).toContainText('制度问题详情')
    await page.locator('.el-drawer:visible .el-drawer__close-btn').click()
  } else {
    await expect(issueCenter.getByText('待处理问题已全部完成')).toBeVisible()
  }
  await expect(issueCenter.getByLabel('问题类型')).toBeVisible()
  await expect(issueCenter.getByLabel('涉及制度')).toBeVisible()

  if (page.viewportSize()?.width === 393) {
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)
    expect(overflow).toBeFalsy()
  }
  expect(browserErrors).toEqual([])
})
