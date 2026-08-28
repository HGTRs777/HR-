import { flushPromises, mount } from '@vue/test-utils'
import { vi } from 'vitest'

const chatMocks = vi.hoisted(() => ({
  askQuestion: vi.fn(),
  createConversation: vi.fn(),
  fetchConversation: vi.fn(),
  fetchConversations: vi.fn(),
  fetchPolicyReader: vi.fn(),
  refreshAnswer: vi.fn(),
  removeConversation: vi.fn(),
  replayAnswer: vi.fn(),
}))

vi.mock('../src/services/chat', () => chatMocks)

const feedbackMocks = vi.hoisted(() => ({ fetchFeedbackDetail: vi.fn(), fetchMyFeedback: vi.fn(), submitFeedback: vi.fn() }))
vi.mock('../src/services/feedback', () => feedbackMocks)

import EmployeeWorkbenchView from '../src/views/EmployeeWorkbenchView.vue'

const answer = {
  answer_id: 'answer-1',
  conversation_id: 'conversation-1',
  status: 'answer' as const,
  summary: '年假原则上提前 5 个工作日申请。',
  claims: [{ id: 'claim-1', position: 1, text: '年假原则上提前 5 个工作日申请。', evidence_ids: ['evidence-1'], evidence_validated: true }],
  scenario: {},
  action_card: {
    conclusion: '年假原则上提前 5 个工作日申请。',
    applicable_conditions: ['办理事项：年假'],
    timeline: [{ title: '休假管理制度 · 第三条', description: '年假原则上提前 5 个工作日申请。', evidence_ids: ['evidence-1'] }],
    materials: [], cautions: [],
  },
  source_answer_id: null,
  generation_kind: 'query' as const,
  evidence: [{
    id: 'evidence-1', clause_id: 3, stable_anchor: 'leave-anchor-3', policy_id: 1, policy_code: 'LEAVE-001',
    policy_title: '休假管理制度', policy_version_id: 2, policy_version: '1.0', effective_date: '2026-08-01',
    section_path: '第一章 年假', clause_number: '第三条', page_number: null, quote: '年假原则上提前 5 个工作日申请。', rank: 1,
  }],
  evidence_coverage: 1,
  knowledge_fingerprint: 'fingerprint',
  stale: false,
  degraded: false,
  degraded_reason: null,
  created_at: '2026-08-27T00:00:00Z',
}

describe('EmployeeWorkbenchView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    HTMLElement.prototype.scrollIntoView = vi.fn()
    chatMocks.fetchConversations.mockResolvedValue([{
      id: 'conversation-1', title: '年假如何计算？', scenario: {}, message_count: 2, answer_count: 1,
      has_stale_answers: false, created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:00Z',
    }])
    chatMocks.fetchConversation.mockResolvedValue({
      id: 'conversation-1', title: '年假如何计算？', scenario: {},
      messages: [
        { id: 1, role: 'user', content: '年假如何计算？', created_at: '2026-08-27T00:00:00Z' },
        { id: 2, role: 'assistant', content: answer.summary, created_at: '2026-08-27T00:00:01Z' },
      ],
      answers: [answer], created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:01Z',
    })
    chatMocks.fetchPolicyReader.mockResolvedValue({
      policy_id: 1, policy_code: 'LEAVE-001', policy_title: '休假管理制度', category: '休假',
      policy_version_id: 2, policy_version: '1.0', effective_date: '2026-08-01', status: 'active',
      clauses: [{ clause_id: 3, stable_anchor: 'leave-anchor-3', section_path: '第一章 年假', clause_number: '第三条', page_number: null, paragraph_index: 3, text: '年假原则上提前 5 个工作日申请。' }],
    })
    feedbackMocks.fetchMyFeedback.mockResolvedValue([])
    feedbackMocks.submitFeedback.mockResolvedValue({ id: 'feedback-1' })
  })

  it('renders conversations, verified claims and a stable-anchor reader', async () => {
    const wrapper = mount(EmployeeWorkbenchView)
    await flushPromises()

    expect(wrapper.findAll('.workspace-card')).toHaveLength(3)
    expect(wrapper.text()).toContain('多轮对话')
    expect(wrapper.text()).toContain('证据已验证')
    expect(wrapper.text()).toContain('证据覆盖率')
    expect(wrapper.text()).toContain('一问一办')
    expect(wrapper.text()).toContain('办理时间线')

    await wrapper.get('.evidence-links button').trigger('click')
    await flushPromises()

    expect(chatMocks.fetchPolicyReader).toHaveBeenCalledWith(2)
    const clause = wrapper.get('[data-anchor="leave-anchor-3"]')
    expect(clause.classes()).toContain('highlighted')
    expect(clause.text()).toContain('年假原则上提前 5 个工作日申请')
  })

  it('submits a clarification choice as a scenario replay and shows the diff', async () => {
    const clarificationAnswer = {
      ...answer,
      answer_id: 'clarification-1',
      status: 'clarification' as const,
      summary: '你的累计工作年限属于哪一档？',
      claims: [], evidence: [], evidence_coverage: 0,
      scenario: { matter_type: 'annual_leave' },
      clarification: {
        slot: 'tenure_years', question: '你的累计工作年限属于哪一档？',
        options: [{ value: 3, label: '满 1 年、不满 10 年' }],
      },
      action_card: { applicable_conditions: [], timeline: [], materials: [], cautions: [] },
    }
    chatMocks.fetchConversation.mockResolvedValueOnce({
      id: 'conversation-1', title: '年假如何计算？', scenario: clarificationAnswer.scenario,
      messages: [], answers: [clarificationAnswer],
      created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:01Z',
    }).mockResolvedValueOnce({
      id: 'conversation-1', title: '年假如何计算？', scenario: { matter_type: 'annual_leave', tenure_years: 3 },
      messages: [], answers: [clarificationAnswer, { ...answer, scenario: { matter_type: 'annual_leave', tenure_years: 3 }, generation_kind: 'replay' as const }],
      created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:02Z',
    })
    chatMocks.replayAnswer.mockResolvedValue({
      answer: { ...answer, scenario: { matter_type: 'annual_leave', tenure_years: 3 }, generation_kind: 'replay' },
      meta: { previous_answer_id: 'clarification-1', scenario_changes: [{ field: 'tenure_years', label: '累计工龄', before: null, after: 3, before_label: '未设置', after_label: '3 年' }] },
    })

    const wrapper = mount(EmployeeWorkbenchView)
    await flushPromises()
    expect(wrapper.text()).toContain('回答前先确认一个关键条件')
    await wrapper.get('.clarification-options button').trigger('click')
    await flushPromises()

    expect(chatMocks.replayAnswer).toHaveBeenCalledWith({
      answer_id: 'clarification-1', scenario: { matter_type: 'annual_leave', tenure_years: 3 },
    })
    expect(wrapper.text()).toContain('累计工龄：未设置 → 3 年')
    expect(wrapper.text()).toContain('情景推演')
  })

  it('refreshes a stale answer without replacing its source id', async () => {
    const staleAnswer = { ...answer, stale: true }
    chatMocks.fetchConversation.mockResolvedValueOnce({
      id: 'conversation-1', title: '年假如何计算？', scenario: {}, messages: [], answers: [staleAnswer],
      created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:01Z',
    }).mockResolvedValueOnce({
      id: 'conversation-1', title: '年假如何计算？', scenario: {}, messages: [], answers: [staleAnswer, { ...answer, answer_id: 'answer-2', generation_kind: 'refresh' as const }],
      created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:02Z',
    })
    chatMocks.refreshAnswer.mockResolvedValue({
      answer: { ...answer, answer_id: 'answer-2', source_answer_id: 'answer-1', generation_kind: 'refresh', stale: false },
      meta: { previous_answer_id: 'answer-1', previous_knowledge_fingerprint: 'old', current_knowledge_fingerprint: 'new' },
    })

    const wrapper = mount(EmployeeWorkbenchView)
    await flushPromises()
    await wrapper.get('.stale-refresh button').trigger('click')
    await flushPromises()

    expect(chatMocks.refreshAnswer).toHaveBeenCalledWith('answer-1')
    expect(wrapper.text()).toContain('保鲜刷新')
  })

  it('submits an anonymous co-creation feedback tied to the selected answer', async () => {
    feedbackMocks.fetchMyFeedback
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{
        id: 'feedback-1', answer_id: 'answer-1', is_anonymous: true, submitter_name: null,
        feedback_type: 'unclear', content: '希望把办理材料写得更清楚。', auto_category: 'usability', status: 'open',
        events: [{ id: 1, actor_type: 'employee', action: 'submitted', note: '匿名提交', event_data: {}, created_at: '2026-08-27T00:00:00Z' }],
        created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:00Z',
      }])
    const wrapper = mount(EmployeeWorkbenchView)
    await flushPromises()

    await wrapper.get('.feedback-community-heading button').trigger('click')
    await flushPromises()
    const textarea = wrapper.findAll('textarea').at(-1)!
    await textarea.setValue('希望把办理材料写得更清楚。')
    await wrapper.findAll('.el-dialog__footer button').at(-1)!.trigger('click')
    await flushPromises()

    expect(feedbackMocks.submitFeedback).toHaveBeenCalledWith(expect.objectContaining({
      answer_id: 'answer-1', is_anonymous: true, submitter_name: null,
    }))
    expect(wrapper.text()).toContain('希望把办理材料写得更清楚')
    expect(wrapper.text()).toContain('待处理')
  })
})
