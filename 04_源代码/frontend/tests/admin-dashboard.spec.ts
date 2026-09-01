import { flushPromises, mount } from '@vue/test-utils'
import { vi } from 'vitest'

const adminMocks = vi.hoisted(() => ({
  createRegressionCase: vi.fn(), deletePolicyVersion: vi.fn(), fetchAdminFeedback: vi.fn(), fetchAdminPolicyReader: vi.fn(),
  fetchAdminSession: vi.fn(), fetchAnalytics: vi.fn(), fetchClauseReferences: vi.fn(), fetchIndexStatus: vi.fn(), fetchPolicies: vi.fn(), fetchPolicyBriefing: vi.fn(), fetchPolicyInsights: vi.fn(), fetchPolicySummary: vi.fn(),
  fetchLatestPolicyGapScan: vi.fn(), fetchPolicyIssues: vi.fn(), runPolicyGapScan: vi.fn(),
  fetchRegressionCases: vi.fn(), loginAdmin: vi.fn(), logoutAdmin: vi.fn(), rebuildIndex: vi.fn(), retestFeedback: vi.fn(),
  retestPolicyIssue: vi.fn(), createPolicyIssueFromInsight: vi.fn(), updatePolicyIssue: vi.fn(),
  testSearch: vi.fn(), updateFeedbackStatus: vi.fn(), updatePolicyVersion: vi.fn(), uploadPolicy: vi.fn(),
}))

vi.mock('../src/services/admin', () => adminMocks)

const routerMocks = vi.hoisted(() => {
  const route = { query: {} as Record<string, string>, fullPath: '/admin' }
  const replace = vi.fn(async ({ query }: { query: Record<string, string> }) => {
    route.query = query
    const search = new URLSearchParams(query).toString()
    route.fullPath = `/admin${search ? `?${search}` : ''}`
  })
  return { route, replace }
})
vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return { ...actual, useRoute: () => routerMocks.route, useRouter: () => ({ replace: routerMocks.replace }) }
})

const authMocks = vi.hoisted(() => ({ fetchHumanChallenge: vi.fn() }))
vi.mock('../src/services/auth', () => authMocks)

import AdminDashboardView from '../src/views/AdminDashboardView.vue'

function makePolicyIssue(overrides: Record<string, unknown> = {}) {
  return {
    id: 1, category: 'unanswered', severity: 'high', title: '高频未回答：陪产假如何办理', description: '该问题出现 4 次。',
    suggested_action: '补充制度条款。', occurrences: 4,
    evidence: [{ ref: 'query:1', question: '陪产假如何办理', status: 'refusal', count: 4 }], scan_id: 'scan-1',
    sources: ['ai_scan', 'qa_insight'], status: 'pending', origin_question: '陪产假如何办理', processing_note: null,
    last_retest: {}, history: [], created_at: '2026-08-27T00:00:00Z', last_seen_at: '2026-08-28T00:00:00Z', resolved_at: null,
    policies: [{ policy_id: 1, policy_title: '休假管理制度' }], recent_consultations: 4, is_recurring: true,
    affects_handling: true, open_days: 5, priority_score: 304755, ...overrides,
  }
}

describe('AdminDashboardView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    routerMocks.route.query = {}
    routerMocks.route.fullPath = '/admin'
    HTMLElement.prototype.scrollIntoView = vi.fn()
    adminMocks.fetchAdminSession.mockResolvedValue({ authenticated: true, admin: { id: 1, username: 'hr-admin', display_name: '李娜 · 工号 HR1001' } })
    adminMocks.fetchPolicies.mockResolvedValue({
      items: [{
        id: 1, code: 'LEAVE-001', title: '休假管理制度', category: '休假', active_version_id: 2, version_count: 1,
        created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:00Z',
        versions: [{ id: 2, version: '1.0', effective_date: '2026-08-01', status: 'active', file_name: 'leave.md',
          mime_type: 'text/markdown', size_bytes: 1024, file_sha256: 'a'.repeat(64), parsed_at: '2026-08-27T00:00:00Z',
          parse_error: null, clause_count: 6, created_at: '2026-08-27T00:00:00Z' }],
      }],
      meta: { page: 1, page_size: 100, total: 1, pages: 1 },
    })
    adminMocks.fetchIndexStatus.mockResolvedValue({
      status: 'ready', fingerprint: 'fingerprint', current_knowledge_fingerprint: 'fingerprint', stale: false,
      clause_count: 30, active_clause_count: 30, embedding_model: 'BAAI/bge-small-zh-v1.5', chunker_version: 'clause-v1',
      built_at: '2026-08-27T00:00:00Z', error: null,
    })
    adminMocks.fetchAdminPolicyReader.mockResolvedValue({
      policy_id: 1, policy_code: 'LEAVE-001', policy_title: '休假管理制度', category: '休假', policy_version_id: 2,
      policy_version: '1.0', effective_date: '2026-08-01', status: 'active', clauses: [{ clause_id: 3,
        stable_anchor: 'leave-anchor-3', section_path: '第一章 年假', clause_number: '第三条', page_number: 2,
        paragraph_index: 3, text: '年假按累计工龄确定。' }],
    })
    adminMocks.fetchClauseReferences.mockResolvedValue({
      clause_id: 3, total_references: 7, question_count: 1, questions: [{ question: '年假如何计算？',
        reference_count: 7, average_rank: 1.4, last_referenced_at: '2026-08-27T00:00:00Z' }],
    })
    adminMocks.fetchAdminFeedback.mockResolvedValue([{
      id: 'feedback-1', answer_id: 'answer-1', conversation_id: 'conversation-1', primary_policy_id: 1,
      submitter_name: null, is_anonymous: true, feedback_type: 'wrong_answer', content: '请核对这条年假回答。',
      auto_category: 'accuracy', status: 'open', last_retest: null,
      answer_snapshot: { question: '年假如何计算？' },
      events: [{ id: 1, actor_type: 'employee', action: 'submitted', note: '匿名提交', event_data: {}, created_at: '2026-08-27T00:00:00Z' }],
      created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:00Z',
    }])
    adminMocks.fetchRegressionCases.mockResolvedValue([])
    adminMocks.fetchAnalytics.mockResolvedValue({
      query_count: 12, hit_rate: 0.75, trusted_hit_rate: 0.82, finalized_query_count: 10, refusal_rate: 0.08, clarification_rate: 0.17, degraded_rate: 0,
      average_latency_ms: 420, feedback_count: 1, open_feedback_count: 1, regression_case_count: 0,
      popular_questions: [{ question: '年假如何计算？', count: 4, status_counts: { answer: 4 }, latest_status: 'answer',
        last_seen_at: '2026-08-27T00:00:00Z', average_top_score: 0.82, average_retrieval_latency_ms: 80,
        average_total_latency_ms: 420, policies: [{ policy_id: 1, policy_title: '休假管理制度' }], feedback_count: 1,
        latest_answer: '年假按累计工龄确定。', ever_missed: false, reason: null, issue_category: null }], missed_questions: [],
      feedback_by_category: [{ category: 'accuracy', count: 1 }], feedback_by_status: [{ status: 'open', count: 1 }],
      daily_queries: [], daily_quality: [{ date: '2026-08-27', query_count: 12, hit_rate: 0.75, clarification_rate: 0.17,
        refusal_rate: 0.08, average_latency_ms: 420 }], period_comparison: { query_count: 0.2, hit_rate: 0.05,
        trusted_hit_rate: 0.03, negative_feedback_count: 0, average_latency_ms: -0.1 }, policy_hits: [], filters: { date_from: null, date_to: null,
        policy_id: null, feedback_status: null, answer_status: null, question_type: null, only_missed: false, only_negative: false },
    })
    adminMocks.fetchLatestPolicyGapScan.mockResolvedValue({
      id: 'scan-1', trigger_type: 'scheduled', status: 'completed', summary: '已完成定期扫描。', query_count: 12,
      policy_count: 1, model_name: null, error_message: null, started_at: '2026-08-27T00:00:00Z',
      completed_at: '2026-08-27T00:00:01Z', issues: [{ id: 1, category: 'unanswered', severity: 'high',
        title: '高频未回答：陪产假如何办理', description: '该问题出现 4 次。', suggested_action: '补充制度条款。', occurrences: 4,
        evidence: [{ ref: 'query:1', question: '陪产假如何办理', status: 'refusal', count: 4 }] }],
    })
    adminMocks.fetchPolicyIssues.mockResolvedValue([makePolicyIssue()])
    const summary = { generated_at: '2026-09-01T02:00:00Z', pending_issues: 1, severity_counts: { high: 1, medium: 0, low: 0 },
      new_this_week: 1, new_issue_ids: [1], weak_policy_count: 1, weak_policy_ids: [1], high_previous_week: 0, high_week_change: 1 }
    adminMocks.fetchPolicySummary.mockResolvedValue(summary)
    adminMocks.fetchPolicyBriefing.mockImplementation(async (range: 'today' | 'week') => ({
      range, range_label: range === 'today' ? '今日' : '本周', generated_at: '2026-09-01T02:00:00Z',
      period: { start: range === 'today' ? '2026-08-31T16:00:00Z' : '2026-08-30T16:00:00Z', end: '2026-09-01T02:00:00Z' }, summary,
      overview: { consultations: range === 'today' ? 3 : 12, new_issues: range === 'today' ? 0 : 1, pending_issues: 1,
        resolved_issues: range === 'today' ? 0 : 1, high_pending_issues: 1 },
      priority_issues: [{ id: 1, severity: 'high', status: 'pending', title: '高频未回答：陪产假如何办理', consultations: range === 'today' ? 1 : 4,
        previous_period_consultations: 1, policies: [{ policy_id: 1, policy_title: '休假管理制度' }] }],
      concern_categories: [{ category: '休假', count: range === 'today' ? 3 : 8, share: range === 'today' ? 1 : 0.6667, previous_count: 5, change: 3 }],
      weak_policies: [{ policy_id: 1, policy_title: '休假管理制度', category: '休假', unresolved_count: 1, high_count: 1, consultations: range === 'today' ? 3 : 8, issue_ids: [1] }],
      changes: { consultations: { current: range === 'today' ? 3 : 12, previous: 8, change: 4 }, new_issues: { current: range === 'today' ? 0 : 1, previous: 0, change: 1 },
        resolved_issues: { current: range === 'today' ? 0 : 1, previous: 1, change: -1 }, leading_category: { category: '休假', count: 8, share: 0.6667, previous_count: 5, change: 3 } },
    }))
    adminMocks.fetchPolicyInsights.mockImplementation(async (days: 7 | 30) => ({
      generated_at: '2026-09-01T02:00:00Z', days,
      week: { consultations: 12, previous_consultations: 8, consultation_change_rate: 0.5, pending_issues: 1,
        severity_counts: { high: 1, medium: 0, low: 0 }, new_issues: 1, new_issue_ids: [1],
        new_issue_categories: [{ category: '休假', count: 1 }], resolved_issues: 1, resolved_issue_ids: [2], average_resolution_hours: 26 },
      daily_trend: Array.from({ length: days }, (_, index) => ({ date: `2026-08-${String(index + 1).padStart(2, '0')}`, consultations: index === 0 ? 4 : 0, new_issues: index === 0 ? 1 : 0, leading_category: index === 0 ? '休假' : null })),
      attention_changes: [{ category: '休假', current: 8, previous: 5, change_rate: 0.6, policy_ids: [1], questions: [{ question: '年假如何计算？', count: 4 }] }],
      weak_policies: [{ policy_id: 1, policy_title: '休假管理制度', category: '休假', pending_count: 1,
        severity_counts: { high: 1, medium: 0, low: 0 }, consultations: 8, issue_ids: [1] }],
    }))
    adminMocks.updateFeedbackStatus.mockResolvedValue({})
    adminMocks.testSearch.mockResolvedValue({
      question: '年假如何计算？', knowledge_fingerprint: 'fingerprint',
      results: [{ rank: 1, clause_id: 3, stable_anchor: 'leave-anchor-3', policy_id: 1, policy_code: 'LEAVE-001',
        policy_title: '休假管理制度', policy_version_id: 2, policy_version: '1.0', effective_date: '2026-08-01',
        section_path: '第一章 年假', clause_number: '第三条', page_number: null, text: '年假按累计工龄确定。',
        vector_score: 0.82, vector_rank: 1, bm25_score: 1.3, bm25_rank: 1, rrf_score: 0.03279 }],
    })
  })

  it('shows the HR login and human check before entering the console', async () => {
    adminMocks.fetchAdminSession.mockResolvedValueOnce({ authenticated: false, admin: null })
    authMocks.fetchHumanChallenge.mockResolvedValueOnce({ challenge_id: 'challenge-2', prompt: '拖动拼图块，使其与缺口完全重合', target_position: 66, pattern_seed: 240, expires_in: 300 })
    const wrapper = mount(AdminDashboardView)
    await flushPromises()

    expect(wrapper.text()).toContain('登录 HR 控制台')
    expect(wrapper.text()).toContain('admin')
    expect(wrapper.text()).toContain('拖动拼图块')
  })

  it('shows the HR policy operations workbench with the technical tools demoted', async () => {
    const wrapper = mount(AdminDashboardView)
    await flushPromises()

    expect(wrapper.text()).toContain('你好，李娜 · 工号 HR1001')
    expect(wrapper.text()).toContain('实训模拟企业 HR 制度知识库')
    expect(wrapper.text()).toContain('休假管理制度')
    expect(wrapper.text()).toContain('HR 制度工作简报')
    expect(wrapper.text()).toContain('待处理制度问题')
    expect(wrapper.text()).toContain('待完善制度')
    expect(wrapper.text()).toContain('高级信息与发布工具')
    expect(wrapper.text()).toContain('本周数据摘要')
    expect(wrapper.text()).toContain('员工关注变化')
    expect(wrapper.text()).toContain('待完善制度排行')
    expect(wrapper.text()).toContain('制度问题中心')
    expect(wrapper.text()).toContain('高频未回答：陪产假如何办理')
    expect(wrapper.text()).toContain('问答发现')
    expect(wrapper.text()).toContain('近 7 天 4 次')
    expect(wrapper.text()).toContain('30')
    expect(wrapper.get('.admin-hero-side .button-count').text()).toBe('1')
    expect(wrapper.findAll('.admin-module-nav button')).toHaveLength(3)
    expect(wrapper.get('.admin-module-nav button[title="制度管理"]').attributes('aria-label')).toContain('制度管理')

    await wrapper.findAll('.admin-hero-side button')[0].trigger('click')
    expect(wrapper.text()).toContain('反馈闭环与回归')
    expect(wrapper.text()).toContain('请核对这条年假回答')
  })

  it('makes all four management metrics keyboard accessible and drillable', async () => {
    const wrapper = mount(AdminDashboardView, { attachTo: document.body })
    await flushPromises()

    const metrics = wrapper.findAll('.management-metric-card')
    expect(metrics).toHaveLength(4)
    expect(metrics.every((card) => card.attributes('role') === 'button' && card.attributes('tabindex') === '0')).toBe(true)
    await metrics[0].trigger('click')
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalled()
    await metrics[1].trigger('click')
    await metrics[2].trigger('click')
    await metrics[3].trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('当前仅显示存在待处理问题的制度')
    wrapper.unmount()
  })

  it('switches between different daily and weekly briefings and opens the matching detail', async () => {
    const wrapper = mount(AdminDashboardView, { attachTo: document.body, global: { stubs: { teleport: true } } })
    await flushPromises()

    expect(adminMocks.fetchPolicyBriefing).toHaveBeenCalledWith('today')
    expect(wrapper.text()).toContain('员工今日主要关注')
    await wrapper.get('.briefing-range-switch button:last-child').trigger('click')
    await flushPromises()
    expect(adminMocks.fetchPolicyBriefing).toHaveBeenCalledWith('week')
    await wrapper.get('.briefing-open-button').trigger('click')
    expect(wrapper.text()).toContain('本周概览')
    expect(wrapper.text()).toContain('员工最关心')
    expect(wrapper.text()).toContain('待完善制度')
    expect(wrapper.text()).toContain('本周变化')
    expect(wrapper.text()).toContain('休假管理制度')
    expect(wrapper.text()).toContain('本周相关咨询')

    await wrapper.get('.briefing-priority-list button').trigger('click')
    expect(wrapper.text()).toContain('制度问题详情')
    expect(routerMocks.route.query).toMatchObject({ module: 'issues', issue: '1' })
    wrapper.unmount()
  })

  it('routes briefing concern categories and weak policies into the matching modules', async () => {
    const wrapper = mount(AdminDashboardView, { attachTo: document.body, global: { stubs: { teleport: true } } })
    await flushPromises()
    await wrapper.get('.briefing-range-switch button:last-child').trigger('click')
    await wrapper.get('.briefing-open-button').trigger('click')

    await wrapper.get('.briefing-category-list button').trigger('click')
    await flushPromises()
    expect(routerMocks.route.query).toMatchObject({ module: 'insights', category: '休假' })
    expect(wrapper.text()).toContain('当前员工关注：休假')

    await wrapper.get('.briefing-open-button').trigger('click')
    await wrapper.get('.briefing-weak-list button').trigger('click')
    await flushPromises()
    expect(routerMocks.route.query).toMatchObject({ module: 'issues', policy: 'LEAVE-001', status: 'open' })
    expect(wrapper.get('[aria-label="涉及制度"]').element).toBeTruthy()
    wrapper.unmount()
  })

  it('restores issue filters from the URL and links an issue back to its policy', async () => {
    routerMocks.route.query = { module: 'issues', risk: 'high', status: 'open', policy: 'LEAVE-001' }
    routerMocks.route.fullPath = '/admin?module=issues&risk=high&status=open&policy=LEAVE-001'
    const wrapper = mount(AdminDashboardView)
    await flushPromises()

    expect(wrapper.get('#admin-module-gaps select[aria-label="涉及制度"]').element).toHaveProperty('value', '1')
    expect(wrapper.get('.highest-priority-card h3').text()).toContain('陪产假')
    await wrapper.get('.priority-card-body dd button').trigger('click')
    await flushPromises()
    expect(routerMocks.route.query).toMatchObject({ module: 'policies', policy: 'LEAVE-001' })
    expect(wrapper.text()).toContain('制度详情')
  })

  it('shows zero for successful empty statistics and isolates briefing failures', async () => {
    adminMocks.fetchPolicySummary.mockResolvedValueOnce({ generated_at: '2026-09-01T02:00:00Z', pending_issues: 0,
      severity_counts: { high: 0, medium: 0, low: 0 }, new_this_week: 0, new_issue_ids: [], weak_policy_count: 0,
      weak_policy_ids: [], high_previous_week: null, high_week_change: null })
    adminMocks.fetchPolicyBriefing.mockRejectedValueOnce(new Error('404'))
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    const wrapper = mount(AdminDashboardView)
    await flushPromises()

    expect(wrapper.findAll('.management-metric-card').map((card) => card.text())).toEqual(expect.arrayContaining([
      expect.stringContaining('待处理制度问题0'), expect.stringContaining('高风险问题0'),
      expect.stringContaining('本周新增问题0'), expect.stringContaining('待完善制度0'),
    ]))
    expect(wrapper.text()).toContain('工作简报暂时无法加载')
    expect(wrapper.text()).not.toContain('The requested URL was not found')
    expect(wrapper.text()).toContain('休假管理制度')
    consoleSpy.mockRestore()
  })

  it('shows actionable HR insights and switches the trend between 7 and 30 days', async () => {
    const wrapper = mount(AdminDashboardView, { attachTo: document.body, global: { stubs: { teleport: true } } })
    await flushPromises()

    const insightMetrics = wrapper.findAll('.hr-insight-metrics .metric-card')
    expect(insightMetrics).toHaveLength(4)
    expect(insightMetrics[0].text()).toContain('本周员工咨询12')
    expect(insightMetrics[1].text()).toContain('高 1 · 中 0 · 低 0')
    expect(wrapper.text()).toContain('本周员工共咨询 12 次')
    expect(wrapper.text()).toContain('休假管理制度')

    await wrapper.findAll('#employee-policy-trend .range-switch button')[1].trigger('click')
    await flushPromises()
    expect(adminMocks.fetchPolicyInsights).toHaveBeenCalledWith(30)

    await wrapper.get('.attention-change-table button').trigger('click')
    expect(routerMocks.route.query).toMatchObject({ module: 'issues', policyCategory: '休假', status: 'open' })
    expect(wrapper.text()).toContain('当前员工关注类别：休假')

    await wrapper.get('.weak-policy-ranking li > div > button').trigger('click')
    await flushPromises()
    expect(routerMocks.route.query).toMatchObject({ module: 'issues', policy: 'LEAVE-001', status: 'open' })
    wrapper.unmount()
  })

  it('renders meaningful empty states for insight data', async () => {
    adminMocks.fetchPolicyInsights.mockResolvedValueOnce({ generated_at: '2026-09-01T02:00:00Z', days: 7,
      week: { consultations: 0, previous_consultations: 0, consultation_change_rate: null, pending_issues: 0,
        severity_counts: { high: 0, medium: 0, low: 0 }, new_issues: 0, new_issue_ids: [], new_issue_categories: [],
        resolved_issues: 0, resolved_issue_ids: [], average_resolution_hours: null },
      daily_trend: Array.from({ length: 7 }, (_, index) => ({ date: `2026-08-0${index + 1}`, consultations: 0, new_issues: 0, leading_category: null })),
      attention_changes: [], weak_policies: [] })
    const wrapper = mount(AdminDashboardView)
    await flushPromises()

    expect(wrapper.text()).toContain('最近 7 天暂无咨询和新增制度问题')
    expect(wrapper.text()).toContain('当前类别暂无可比较咨询')
    expect(wrapper.text()).toContain('当前类别暂无待完善制度')
    expect(wrapper.findAll('.hr-insight-metrics .metric-card').every((card) => card.text().includes('0'))).toBe(true)
  })

  it('shows dynamic issue overview and orders multiple high-risk issues by operational priority', async () => {
    adminMocks.fetchPolicyIssues.mockResolvedValueOnce([
      makePolicyIssue({ id: 2, title: '高风险但咨询较少', recent_consultations: 1, priority_score: 301000 }),
      makePolicyIssue({ id: 3, title: '中风险高频问题', severity: 'medium', recent_consultations: 20, priority_score: 220000 }),
      makePolicyIssue({ id: 1, title: '高风险且持续高频', recent_consultations: 8, priority_score: 308750 }),
    ])
    const wrapper = mount(AdminDashboardView)
    await flushPromises()

    expect(wrapper.findAll('.issue-overview button').map((item) => item.text())).toEqual(expect.arrayContaining([
      expect.stringContaining('待处理问题3'), expect.stringContaining('高风险2'),
      expect.stringContaining('中风险1'), expect.stringContaining('低风险0'),
    ]))
    expect(wrapper.get('.highest-priority-card h3').text()).toBe('高风险且持续高频')
    expect(wrapper.findAll('.compact-policy-issue-list h4').map((item) => item.text())).toEqual(['高风险但咨询较少', '中风险高频问题'])

    await wrapper.findAll('.issue-overview button')[1].trigger('click')
    expect(wrapper.get('.highest-priority-card h3').text()).toBe('高风险且持续高频')
    expect(wrapper.findAll('.compact-policy-issue-list h4').map((item) => item.text())).toEqual(['高风险但咨询较少'])
  })

  it.each([
    { name: '没有高风险时选择中风险', issues: [makePolicyIssue({ id: 2, severity: 'low', title: '低风险问题', priority_score: 100010 }), makePolicyIssue({ id: 1, severity: 'medium', title: '中风险问题', priority_score: 200010 })], expected: '中风险问题' },
    { name: '只有低风险时选择低风险', issues: [makePolicyIssue({ severity: 'low', title: '唯一低风险问题', priority_score: 100010 })], expected: '唯一低风险问题' },
  ])('$name', async ({ issues, expected }) => {
    adminMocks.fetchPolicyIssues.mockResolvedValueOnce(issues)
    const wrapper = mount(AdminDashboardView)
    await flushPromises()
    expect(wrapper.get('.highest-priority-card h3').text()).toBe(expected)
  })

  it('shows the completed empty state when no open issue remains', async () => {
    adminMocks.fetchPolicyIssues.mockResolvedValueOnce([makePolicyIssue({ status: 'resolved', resolved_at: '2026-09-01T00:00:00Z', priority_score: 0 })])
    const wrapper = mount(AdminDashboardView)
    await flushPromises()

    expect(wrapper.text()).toContain('待处理问题已全部完成')
    expect(wrapper.findAll('.issue-overview button')[0].text()).toContain('0')
    expect(wrapper.find('.highest-priority-card').exists()).toBe(false)
  })

  it('refreshes the overview and selects the next issue after the current issue is resolved', async () => {
    const processing = makePolicyIssue({ id: 1, status: 'processing', title: '正在处理的高风险问题', last_retest: {
      passed: true, question: '陪产假如何办理', previous_status: 'unanswered', current_status: 'trusted_hit',
      knowledge_fingerprint: 'fingerprint', top_score: 0.8, citations: [], run_at: '2026-09-01T00:00:00Z',
    } })
    const next = makePolicyIssue({ id: 2, severity: 'medium', title: '下一项中风险问题', priority_score: 200100 })
    const resolved = { ...processing, status: 'resolved', resolved_at: '2026-09-01T01:00:00Z', priority_score: 0 }
    adminMocks.fetchPolicyIssues.mockResolvedValueOnce([processing, next]).mockResolvedValueOnce([next, resolved])
    adminMocks.updatePolicyIssue.mockResolvedValueOnce(resolved)
    const wrapper = mount(AdminDashboardView, { attachTo: document.body, global: { stubs: { teleport: true } } })
    await flushPromises()

    const continueButton = wrapper.findAll('.highest-priority-card button').find((button) => button.text().includes('继续处理'))
    await continueButton!.trigger('click')
    const resolveButton = wrapper.findAll('.drawer-sticky-actions button').find((button) => button.text().includes('标记已解决'))
    await resolveButton!.trigger('click')
    await flushPromises()

    expect(adminMocks.updatePolicyIssue).toHaveBeenCalledWith(1, 'resolve', undefined)
    expect(wrapper.get('.highest-priority-card h3').text()).toBe('下一项中风险问题')
    expect(wrapper.findAll('.issue-overview button')[0].text()).toContain('1')
    expect(routerMocks.route.query).toMatchObject({ module: 'issues', status: 'open' })
    expect(routerMocks.route.query).not.toHaveProperty('issue')
    wrapper.unmount()
  })

  it('drills from policy to clauses and only shows real answer references on request', async () => {
    const wrapper = mount(AdminDashboardView, { attachTo: document.body, global: { stubs: { teleport: true } } })
    await flushPromises()

    await wrapper.get('.clause-count-link').trigger('click')
    await flushPromises()
    expect(adminMocks.fetchAdminPolicyReader).toHaveBeenCalledWith(2)
    expect(document.body.textContent).toContain('条款目录')
    await wrapper.get('.clause-directory button').trigger('click')
    expect(document.body.textContent).toContain('年假按累计工龄确定。')
    const referenceButton = wrapper.findAll('button').find((button) => button.text().includes('查看问答引用'))
    expect(referenceButton).toBeTruthy()
    await referenceButton!.trigger('click')
    await flushPromises()
    expect(adminMocks.fetchClauseReferences).toHaveBeenCalledWith(3)
    expect(document.body.textContent).toContain('该条款共被 7 个回答引用')
    expect(document.body.textContent).toContain('平均检索排名 1.4')
    wrapper.unmount()
  })

  it('starts feedback processing and reloads governance data', async () => {
    const wrapper = mount(AdminDashboardView)
    await flushPromises()
    await wrapper.findAll('.admin-hero-side button')[0].trigger('click')
    await wrapper.get('.feedback-actions button').trigger('click')
    await flushPromises()

    expect(adminMocks.updateFeedbackStatus).toHaveBeenCalledWith('feedback-1', 'start_processing', undefined)
    expect(adminMocks.fetchAdminFeedback).toHaveBeenCalledTimes(2)
  })

  it('runs retrieval validation and reveals the result with visible feedback', async () => {
    const wrapper = mount(AdminDashboardView, { attachTo: document.body })
    await flushPromises()
    await wrapper.get('.search-test-card button').trigger('click')
    await flushPromises()

    expect(adminMocks.testSearch).toHaveBeenCalledWith('年假如何计算？')
    expect(wrapper.text()).toContain('检索完成，找到 1 条相关制度依据')
    expect(wrapper.text()).toContain('本次 Top 5 检索合格')
    expect(wrapper.text()).toContain('查看诊断详情')
    expect(HTMLElement.prototype.scrollIntoView).not.toHaveBeenCalled()
    expect(wrapper.get('.admin-module-nav button[title="制度管理"]').classes()).toContain('active')
    await wrapper.get('.search-verdict-card button').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('Top 5 检索诊断详情')
    expect(document.body.textContent).toContain('年假按累计工龄确定')
    wrapper.unmount()
  })

  it('switches the active navigation icon when a module enters the reading area', async () => {
    let observerCallback: IntersectionObserverCallback | undefined
    class FakeIntersectionObserver {
      constructor(callback: IntersectionObserverCallback) { observerCallback = callback }
      observe = vi.fn()
      disconnect = vi.fn()
      unobserve = vi.fn()
      takeRecords = () => []
      root = null
      rootMargin = ''
      thresholds = []
    }
    vi.stubGlobal('IntersectionObserver', FakeIntersectionObserver)
    const wrapper = mount(AdminDashboardView, { attachTo: document.body })
    await flushPromises()
    const gapModule = wrapper.get('#admin-module-gaps').element
    observerCallback?.([{
      target: gapModule, isIntersecting: true, intersectionRatio: 0.8,
    } as IntersectionObserverEntry], {} as IntersectionObserver)
    await flushPromises()

    const gapButton = wrapper.get('.admin-module-nav button[title="问题中心"]')
    expect(gapButton.classes()).toContain('active')
    expect(gapButton.text()).toContain('问题中心')
    wrapper.unmount()
    vi.unstubAllGlobals()
  })

  it('keeps core HR data visible when policy gap scanning fails', async () => {
    adminMocks.fetchLatestPolicyGapScan.mockRejectedValueOnce(new Error('扫描服务暂不可用'))
    const wrapper = mount(AdminDashboardView)
    await flushPromises()

    expect(wrapper.text()).toContain('休假管理制度')
    expect(wrapper.text()).toContain('本周员工咨询')
    expect(wrapper.text()).toContain('12')
    expect(wrapper.text()).toContain('制度扫描暂不可用，问题中心其他数据不受影响')
  })
})
