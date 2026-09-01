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
  updateConversation: vi.fn(),
}))

vi.mock('../src/services/chat', () => chatMocks)

const authMocks = vi.hoisted(() => ({
  fetchEmployeeSession: vi.fn(), fetchHumanChallenge: vi.fn(), loginEmployee: vi.fn(), logoutEmployee: vi.fn(),
}))
vi.mock('../src/services/auth', () => authMocks)

const feedbackMocks = vi.hoisted(() => ({ fetchFeedbackDetail: vi.fn(), fetchMyFeedback: vi.fn(), submitFeedback: vi.fn() }))
vi.mock('../src/services/feedback', () => feedbackMocks)

import EmployeeWorkbenchView from '../src/views/EmployeeWorkbenchView.vue'

const answer = {
  answer_id: 'answer-1',
  conversation_id: 'conversation-1',
  status: 'answer' as const,
  decision: 'informational' as const,
  question_type: 'deadline' as const,
  answer_focus: '年假申请提前期限',
  primary_answer: '年假原则上提前 5 个工作日申请。',
  conclusion: '需要',
  decision_statement: '年假原则上提前 5 个工作日申请。',
  summary: '年假原则上提前 5 个工作日申请。',
  reason_title: null,
  reason_items: [],
  chat_answer: '【明确结论】\n年假原则上提前 5 个工作日申请。',
  claims: [{ id: 'claim-1', position: 1, text: '年假原则上提前 5 个工作日申请。', evidence_ids: ['evidence-1'], evidence_validated: true }],
  next_steps: [{ text: '提前 5 个工作日提交年假申请。', evidence_ids: ['evidence-1'] }],
  missing_conditions: [],
  scenario: { matter_type: 'annual_leave' },
  employee_context: {
    known: [],
    missing: [],
  },
  action_card: {
    conclusion: '年假原则上提前 5 个工作日申请。',
    applicable_conditions: ['办理事项：年假'],
    generation_source: 'structured_template',
    estimated_completion: null,
    basis_evidence_ids: ['evidence-1'],
    tasks: [{ id: 'annual.submit', title: '提交年假申请', description: '从休假入口发起申请。', evidence_ids: ['evidence-1'], category: 'action' }],
    process_flow: [{ id: 'annual.employee', label: '员工发起年假申请', detail: '填写休假时间。', evidence_ids: ['evidence-1'] }],
    timeline: [],
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
    vi.resetAllMocks()
    HTMLElement.prototype.scrollIntoView = vi.fn()
    authMocks.fetchEmployeeSession.mockResolvedValue({
      authenticated: true,
      employee: {
        id: 1, username: 'staff', display_name: '陈晨 · 工号 E1001', department: '产品与技术中心',
        job_title: '软件工程师', employee_status: 'regular', hire_date: '2023-03-01', tenure_years: 3.5,
        direct_manager: '王强', hrbp: '李娜', annual_leave_entitlement: 5, annual_leave_balance: 3,
      },
    })
    chatMocks.fetchConversations.mockResolvedValue([{
      id: 'conversation-1', title: '[演示] 很长的年假如何计算以及审批流程？', scenario: {}, message_count: 2, answer_count: 1,
      is_pinned: false, has_stale_answers: false, created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:00Z',
    }])
    chatMocks.fetchConversation.mockResolvedValue({
      id: 'conversation-1', title: '年假如何计算？', is_pinned: false, scenario: {},
      messages: [
        { id: 1, role: 'user', content: '年假如何计算？', created_at: '2026-08-27T00:00:00Z' },
        { id: 2, role: 'assistant', content: answer.chat_answer, created_at: '2026-08-27T00:00:01Z' },
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
    chatMocks.updateConversation.mockResolvedValue({ id: 'conversation-1', title: '年假如何计算？', is_pinned: true, updated_at: '2026-08-27T00:00:02Z' })
  })

  it('shows the employee login and human check before entering the workbench', async () => {
    authMocks.fetchEmployeeSession.mockResolvedValueOnce({ authenticated: false, employee: null })
    authMocks.fetchHumanChallenge.mockResolvedValueOnce({ challenge_id: 'challenge-1', prompt: '拖动拼图块，使其与缺口完全重合', target_position: 58, pattern_seed: 120, expires_in: 300 })
    const wrapper = mount(EmployeeWorkbenchView, { attachTo: document.body })
    await flushPromises()

    expect(wrapper.text()).toContain('登录员工工作台')
    expect(wrapper.text()).toContain('staff')
    expect(wrapper.text()).toContain('拖动拼图块')
  })

  it('renders conversations, verified claims and a stable-anchor reader', async () => {
    const wrapper = mount(EmployeeWorkbenchView)
    await flushPromises()

    expect(wrapper.findAll('.workspace-card')).toHaveLength(2)
    expect(wrapper.get('.employee-app-shell').classes()).toContain('sidebar-collapsed')
    expect(wrapper.text()).not.toContain('新增聊天')
    await wrapper.get('[aria-label="展开历史对话侧边栏"]').trigger('click')
    expect(wrapper.text()).toContain('历史对话')
    expect(wrapper.text()).toContain('新增聊天')
    expect(wrapper.text()).toContain('制度咨询')
    expect(wrapper.text()).toContain('实训模拟企业 HR 制度知识库')
    expect(wrapper.text()).toContain('我的情况与办理助手')
    const assistantMessage = wrapper.get('.chat-message.assistant').text()
    expect(assistantMessage).toContain('【明确结论】\n年假原则上提前 5 个工作日申请。')
    expect(assistantMessage.match(/年假原则上提前 5 个工作日申请。/g)).toHaveLength(1)
    expect(wrapper.get('.answer-panel').text()).not.toContain('年假原则上提前 5 个工作日申请。')
    expect(wrapper.text()).not.toContain('结合当前情况，原因是')
    expect(wrapper.text()).toContain('证据已验证')
    expect(wrapper.find('.structured-answer').exists()).toBe(false)
    expect(wrapper.text()).toContain('回答可信度')
    expect(wrapper.text()).toContain('制度依据1 条')
    expect(wrapper.text()).toContain('办理清单年假办理')
    expect(wrapper.text()).toContain('0 / 1 · 0%')
    expect(wrapper.text()).toContain('下一步')
    expect(wrapper.text()).toContain('查看流程')
    expect(wrapper.text()).toContain('导出清单')
    expect(wrapper.text()).not.toContain('[演示]')
    expect(wrapper.get('.conversation-title').attributes('title')).toBe('很长的年假如何计算以及审批流程？')

    await wrapper.get('.employee-profile-trigger').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('个人信息')
    expect(document.body.textContent).toContain('软件工程师')
    expect(document.body.textContent).toContain('王强')

    await wrapper.get('.process-checklist-items input').setValue(true)
    expect(wrapper.text()).toContain('1 / 1 · 100%')
    expect(wrapper.text()).toContain('办理清单已全部完成')

    await wrapper.get('.process-checklist-actions button').trigger('click')
    expect(wrapper.text()).toContain('员工发起年假申请')

    await wrapper.get('.evidence-links button').trigger('click')
    await flushPromises()

    expect(chatMocks.fetchPolicyReader).toHaveBeenCalledWith(2)
    const clause = wrapper.get('[data-anchor="leave-anchor-3"]')
    expect(clause.classes()).toContain('highlighted')
    expect(clause.text()).toContain('年假原则上提前 5 个工作日申请')

    await wrapper.get('[aria-label="隐藏历史对话侧边栏"]').trigger('click')
    expect(wrapper.get('.employee-app-shell').classes()).toContain('sidebar-collapsed')
    await wrapper.get('[aria-label="展开历史对话侧边栏"]').trigger('click')
    expect(wrapper.text()).toContain('年假如何计算？')
    wrapper.unmount()
  })

  it('renders employee tasks separately from the business process line', async () => {
    const workflowAnswer = {
      ...answer,
      action_card: {
        conclusion: answer.summary,
        applicable_conditions: ['办理事项：漏打卡/补卡'],
        generation_source: 'structured_template',
        estimated_completion: null,
        basis_evidence_ids: ['evidence-1'],
        tasks: [
          { id: 'missed_punch.confirm_time', title: '确认漏打卡日期和时间', description: '核对异常记录。', evidence_ids: ['evidence-1'], category: 'action' },
          { id: 'missed_punch.submit', title: '提交补卡申请', description: '从考勤入口提交。', evidence_ids: ['evidence-1'], category: 'action' },
        ],
        process_flow: [
          { id: 'missed_punch.employee', label: '员工发起补卡申请', detail: '填写日期和原因。', evidence_ids: ['evidence-1'] },
          { id: 'missed_punch.manager', label: '王强（直属负责人）', detail: '审批补卡申请。', evidence_ids: ['evidence-1'], person_configured: true },
          { id: 'missed_punch.hr', label: '产品技术中心 HRBP / 考勤负责人（当前系统未配置具体人员）', detail: '复核考勤记录。', evidence_ids: ['evidence-1'], person_configured: false },
        ],
        timeline: [], materials: [], cautions: [],
      },
    }
    chatMocks.fetchConversation.mockResolvedValueOnce({
      id: 'conversation-1', title: '补卡', is_pinned: false, scenario: {}, messages: [], answers: [workflowAnswer],
      created_at: answer.created_at, updated_at: answer.created_at,
    })
    const wrapper = mount(EmployeeWorkbenchView)
    await flushPromises()

    expect(wrapper.get('.process-checklist-items').text()).toContain('确认漏打卡日期和时间')
    expect(wrapper.get('.process-checklist-items').text()).not.toContain('休假管理制度')
    await wrapper.get('.process-checklist-actions button').trigger('click')
    expect(wrapper.get('.business-process-line').text()).toContain('员工发起补卡申请')
    expect(wrapper.get('.business-process-line').text()).toContain('王强（直属负责人）')
    expect(wrapper.get('.business-process-line').text()).toContain('当前系统未配置具体人员')
    expect(wrapper.text()).toContain('不代表真实审批进度')
  })

  it('does not render profile questions after a decisive probation denial', async () => {
    const deniedAnswer = {
      ...answer,
      decision: 'denied' as const,
      question_type: 'eligibility' as const,
      answer_focus: '试用期员工是否具备年假资格',
      primary_answer: '不可以申请年假。试用期员工当前不符合申请条件。',
      conclusion: '不可以',
      decision_statement: '试用期员工当前不符合年假申请条件。',
      summary: '不可以',
      chat_answer: '【明确结论】\n不可以申请年假。\n\n【为什么不可以？】\n你当前处于试用期，制度明确不具备年假申请资格。',
      next_steps: [],
      missing_conditions: [],
      scenario: { matter_type: 'annual_leave', employee_status: 'probation' },
      scenario_form: [],
      clarification: undefined,
      employee_context: {
        known: [{ field: 'employee_status', label: '员工状态', value: 'probation', value_label: '试用期', source: 'employee_profile' as const }],
        missing: [],
      },
    }
    chatMocks.fetchConversation.mockResolvedValueOnce({
      id: 'conversation-1', title: '试用期年假怎么申请？', is_pinned: false, scenario: deniedAnswer.scenario,
      messages: [{ id: 2, role: 'assistant', content: deniedAnswer.chat_answer, created_at: answer.created_at }],
      answers: [deniedAnswer], created_at: answer.created_at, updated_at: answer.created_at,
    })

    const wrapper = mount(EmployeeWorkbenchView)
    await flushPromises()

    expect(wrapper.get('.chat-message.assistant').text()).toContain('【明确结论】\n不可以申请年假。')
    expect(wrapper.get('.answer-panel').text()).not.toContain('不可以申请年假。')
    expect(wrapper.text()).toContain('已自动结合你的员工信息')
    expect(wrapper.text()).toContain('员工状态：试用期')
    expect(wrapper.text()).not.toContain('累计工龄（')
    expect(wrapper.text()).not.toContain('补充我的情况')
  })

  it('keeps rename, pin and delete inside the conversation more menu', async () => {
    const wrapper = mount(EmployeeWorkbenchView, { attachTo: document.body })
    await flushPromises()
    await wrapper.get('[aria-label="展开历史对话侧边栏"]').trigger('click')
    expect(wrapper.find('.delete-link').exists()).toBe(false)

    await wrapper.get('.conversation-more-button').trigger('click')
    await flushPromises()
    const menuText = document.body.textContent || ''
    expect(menuText).toContain('重命名')
    expect(menuText).toContain('置顶聊天')
    expect(menuText).toContain('删除')
    const pinItem = Array.from(document.querySelectorAll<HTMLElement>('.el-dropdown-menu__item')).find((item) => item.textContent?.includes('置顶聊天'))
    pinItem?.click()
    await flushPromises()
    expect(chatMocks.updateConversation).toHaveBeenCalledWith('conversation-1', { is_pinned: true })
    wrapper.unmount()
  })

  it('submits a clarification choice as a scenario replay and shows the diff', async () => {
    const clarificationAnswer = {
      ...answer,
      answer_id: 'clarification-1',
      status: 'clarification' as const,
      decision: 'conditional' as const,
      question_type: 'quota' as const,
      answer_focus: '当前员工可享受的年假天数',
      primary_answer: '条件不足，暂时无法判断。',
      conclusion: '条件不足，暂时无法判断',
      summary: '条件不足，暂时无法判断',
      next_steps: [], missing_conditions: ['累计工龄'],
      claims: [], evidence: [], evidence_coverage: 0,
      scenario: { matter_type: 'annual_leave' },
      chat_answer: '【明确结论】\n条件不足，暂时无法判断。\n\n还需要确认你的累计工龄，请在右侧补充后，我会重新判断。',
      clarification: {
        slot: 'tenure_years', question: '你的累计工作年限属于哪一档？',
        options: [{ value: 3, label: '满 1 年、不满 10 年' }],
      },
      scenario_form: [{ field: 'tenure_years', label: '累计工龄', type: 'select', required: true, answered: false, value: null, options: [{ value: 3, label: '满 1 年、不满 10 年' }] }],
      employee_context: { known: [], missing: [{ field: 'tenure_years', label: '累计工龄', value: null, value_label: '未配置', source: 'employee_profile' as const }] },
      action_card: { applicable_conditions: [], timeline: [], materials: [], cautions: [] },
    }
    chatMocks.fetchConversation.mockResolvedValueOnce({
      id: 'conversation-1', title: '年假如何计算？', scenario: clarificationAnswer.scenario,
      messages: [{ id: 2, role: 'assistant', content: clarificationAnswer.chat_answer, created_at: answer.created_at }], answers: [clarificationAnswer],
      created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:01Z',
    }).mockResolvedValueOnce({
      id: 'conversation-1', title: '年假如何计算？', scenario: { matter_type: 'annual_leave', tenure_years: 3 },
      messages: [], answers: [clarificationAnswer, { ...answer, scenario: { matter_type: 'annual_leave', tenure_years: 3 }, source_answer_id: 'clarification-1', generation_kind: 'replay' as const }],
      created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:02Z',
    })
    chatMocks.replayAnswer.mockResolvedValue({
      answer: { ...answer, scenario: { matter_type: 'annual_leave', tenure_years: 3 }, source_answer_id: 'clarification-1', generation_kind: 'replay' },
      meta: { previous_answer_id: 'clarification-1', scenario_changes: [{ field: 'tenure_years', label: '累计工龄', before: null, after: 3, before_label: '未设置', after_label: '3 年' }], recalculation_message: '条件已更新，回答和办理建议已重新计算。' },
    })

    const wrapper = mount(EmployeeWorkbenchView)
    await flushPromises()
    expect(wrapper.get('.chat-message.assistant').text()).toContain('请在右侧补充后，我会重新判断')
    expect(wrapper.find('.structured-answer').exists()).toBe(false)
    expect(wrapper.get('.answer-panel').text()).toContain('还需要确认')
    expect(wrapper.get('.answer-panel').text()).toContain('累计工龄')
    await wrapper.get('.scenario-condition-row select').setValue('3')
    await wrapper.get('.scenario-sandbox > button').trigger('click')
    await flushPromises()

    expect(chatMocks.replayAnswer).toHaveBeenCalledWith({
      answer_id: 'clarification-1', scenario: { matter_type: 'annual_leave', tenure_years: 3 },
    })
    expect(wrapper.text()).toContain('累计工龄：未设置 → 3 年')
    expect(wrapper.text()).toContain('第 2 版 · 条件更新')
  })

  it('refreshes a stale answer without replacing its source id', async () => {
    const staleAnswer = { ...answer, stale: true }
    chatMocks.fetchConversation.mockResolvedValueOnce({
      id: 'conversation-1', title: '年假如何计算？', scenario: {}, messages: [], answers: [staleAnswer],
      created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:01Z',
    }).mockResolvedValueOnce({
      id: 'conversation-1', title: '年假如何计算？', scenario: {}, messages: [], answers: [staleAnswer, { ...answer, answer_id: 'answer-2', source_answer_id: 'answer-1', generation_kind: 'refresh' as const }],
      created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:02Z',
    })
    chatMocks.refreshAnswer.mockResolvedValue({
      answer: { ...answer, answer_id: 'answer-2', source_answer_id: 'answer-1', generation_kind: 'refresh', stale: false },
      meta: { previous_answer_id: 'answer-1', previous_knowledge_fingerprint: 'old', current_knowledge_fingerprint: 'new' },
    })

    const wrapper = mount(EmployeeWorkbenchView)
    await flushPromises()
    expect(wrapper.text()).toContain('相关制度已更新，建议重新核验。')
    await wrapper.findAll('.policy-update-actions button')[1].trigger('click')
    await flushPromises()

    expect(chatMocks.refreshAnswer).toHaveBeenCalledWith('answer-1')
    expect(wrapper.text()).toContain('第 2 版 · 按新制度回答')
  })

  it('prevents duplicate question requests while the current submission is pending', async () => {
    chatMocks.askQuestion.mockReturnValue(new Promise(() => {}))
    const wrapper = mount(EmployeeWorkbenchView)
    await flushPromises()

    await wrapper.get('.question-composer textarea').setValue('年假如何计算？')
    const send = wrapper.get('.question-composer').get('button')
    await send.trigger('click')
    await send.trigger('click')

    expect(chatMocks.askQuestion).toHaveBeenCalledTimes(1)
  })

  it('opens a standalone feedback page and uses the signed-in identity for named feedback', async () => {
    feedbackMocks.fetchMyFeedback
      .mockResolvedValueOnce([])
      .mockResolvedValueOnce([{
        id: 'feedback-1', answer_id: 'answer-1', is_anonymous: false, submitter_name: '陈晨 · 工号 E1001',
        feedback_type: 'unclear', content: '希望把办理材料写得更清楚。', auto_category: 'usability', status: 'open',
        events: [{ id: 1, actor_type: 'employee', action: 'submitted', note: '匿名提交', event_data: {}, created_at: '2026-08-27T00:00:00Z' }],
        created_at: '2026-08-27T00:00:00Z', updated_at: '2026-08-27T00:00:00Z',
      }])
    const wrapper = mount(EmployeeWorkbenchView)
    await flushPromises()

    await wrapper.get('.hero-actions button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.employee-feedback-page').exists()).toBe(true)
    expect(wrapper.find('.el-dialog').exists()).toBe(false)
    await wrapper.get('.feedback-submit-section input[type="checkbox"]').setValue(false)
    expect(wrapper.text()).toContain('将以 陈晨 · 工号 E1001 的身份提交')
    const textarea = wrapper.findAll('textarea').at(-1)!
    await textarea.setValue('希望把办理材料写得更清楚。')
    await wrapper.get('.feedback-submit-button').trigger('click')
    await flushPromises()

    expect(feedbackMocks.submitFeedback).toHaveBeenCalledWith(expect.objectContaining({
      answer_id: 'answer-1', is_anonymous: false, submitter_name: '陈晨 · 工号 E1001',
    }))
    expect(wrapper.text()).toContain('希望把办理材料写得更清楚')
    expect(wrapper.text()).toContain('待处理')
    expect(wrapper.text()).toContain('意见已提交')
    expect(wrapper.text()).toContain('等待 HR 受理')
  })

  it('submits lightweight helpful feedback through the existing feedback system', async () => {
    const wrapper = mount(EmployeeWorkbenchView)
    await flushPromises()

    await wrapper.findAll('.answer-feedback-prompt button')[0].trigger('click')
    await flushPromises()

    expect(feedbackMocks.submitFeedback).toHaveBeenCalledWith({
      answer_id: 'answer-1', feedback_type: 'helpful', content: '这条回答对我有帮助。', is_anonymous: true,
    })
  })

  it('isolates checklist completion when switching conversations', async () => {
    const secondAnswer = {
      ...answer, answer_id: 'answer-2', conversation_id: 'conversation-2', summary: '差旅报销应按制度提交。',
      scenario: { matter_type: 'travel' },
      action_card: { conclusion: '差旅报销应按制度提交。', applicable_conditions: ['办理事项：差旅报销'], timeline: [],
        materials: [{ title: '差旅制度 · 第一条', description: '提交真实凭证。', evidence_ids: ['evidence-1'] }], cautions: [] },
    }
    chatMocks.fetchConversations.mockResolvedValue([
      { id: 'conversation-1', title: '年假', is_pinned: false, scenario: {}, message_count: 2, answer_count: 1, has_stale_answers: false, created_at: answer.created_at, updated_at: answer.created_at },
      { id: 'conversation-2', title: '差旅', is_pinned: false, scenario: {}, message_count: 2, answer_count: 1, has_stale_answers: false, created_at: answer.created_at, updated_at: answer.created_at },
    ])
    chatMocks.fetchConversation.mockImplementation(async (id: string) => ({
      id, title: id === 'conversation-1' ? '年假' : '差旅', is_pinned: false, scenario: {}, messages: [],
      answers: [id === 'conversation-1' ? answer : secondAnswer], created_at: answer.created_at, updated_at: answer.created_at,
    }))
    const wrapper = mount(EmployeeWorkbenchView)
    await flushPromises()

    await wrapper.get('.process-checklist-items input').setValue(true)
    await wrapper.get('[aria-label="展开历史对话侧边栏"]').trigger('click')
    await wrapper.findAll('.conversation-open-button')[1].trigger('click')
    await flushPromises()
    expect((wrapper.get('.process-checklist-items input').element as HTMLInputElement).checked).toBe(false)
    await wrapper.findAll('.conversation-open-button')[0].trigger('click')
    await flushPromises()
    expect((wrapper.get('.process-checklist-items input').element as HTMLInputElement).checked).toBe(true)
  })
})
