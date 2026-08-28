import { flushPromises, mount } from '@vue/test-utils'
import { vi } from 'vitest'

const adminMocks = vi.hoisted(() => ({
  createRegressionCase: vi.fn(), deletePolicyVersion: vi.fn(), fetchAdminFeedback: vi.fn(), fetchAdminPolicyReader: vi.fn(),
  fetchAdminSession: vi.fn(), fetchAnalytics: vi.fn(), fetchIndexStatus: vi.fn(), fetchPolicies: vi.fn(),
  fetchRegressionCases: vi.fn(), loginAdmin: vi.fn(), logoutAdmin: vi.fn(), rebuildIndex: vi.fn(), retestFeedback: vi.fn(),
  testSearch: vi.fn(), updateFeedbackStatus: vi.fn(), updatePolicyVersion: vi.fn(), uploadPolicy: vi.fn(),
}))

vi.mock('../src/services/admin', () => adminMocks)

import AdminDashboardView from '../src/views/AdminDashboardView.vue'

describe('AdminDashboardView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    adminMocks.fetchAdminSession.mockResolvedValue({ authenticated: true, admin: { id: 1, username: 'hr-admin' } })
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
      query_count: 12, hit_rate: 0.75, refusal_rate: 0.08, clarification_rate: 0.17, degraded_rate: 0,
      average_latency_ms: 420, feedback_count: 1, open_feedback_count: 1, regression_case_count: 0,
      popular_questions: [{ question: '年假如何计算？', count: 4 }], missed_questions: [],
      feedback_by_category: [{ category: 'accuracy', count: 1 }], feedback_by_status: [{ status: 'open', count: 1 }],
      daily_queries: [], policy_hits: [], filters: { date_from: null, date_to: null, policy_id: null, feedback_status: null },
    })
    adminMocks.updateFeedbackStatus.mockResolvedValue({})
  })

  it('shows authenticated policy, index and retrieval management modules', async () => {
    const wrapper = mount(AdminDashboardView)
    await flushPromises()

    expect(wrapper.text()).toContain('你好，hr-admin')
    expect(wrapper.text()).toContain('休假管理制度')
    expect(wrapper.text()).toContain('原子索引')
    expect(wrapper.text()).toContain('Top 5 检索测试')
    expect(wrapper.text()).toContain('问答数据洞察')
    expect(wrapper.text()).toContain('反馈闭环与回归')
    expect(wrapper.text()).toContain('请核对这条年假回答')
    expect(wrapper.text()).toContain('30')
  })

  it('starts feedback processing and reloads governance data', async () => {
    const wrapper = mount(AdminDashboardView)
    await flushPromises()
    await wrapper.get('.feedback-actions button').trigger('click')
    await flushPromises()

    expect(adminMocks.updateFeedbackStatus).toHaveBeenCalledWith('feedback-1', 'start_processing', undefined)
    expect(adminMocks.fetchAnalytics).toHaveBeenCalled()
  })
})
