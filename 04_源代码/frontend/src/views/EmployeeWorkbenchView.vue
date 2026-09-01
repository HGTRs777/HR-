<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ElAlert, ElButton, ElCheckbox, ElDialog, ElDropdown, ElDropdownItem, ElDropdownMenu, ElEmpty, ElForm, ElFormItem, ElInput, ElMessage, ElMessageBox, ElPopover, ElScrollbar, ElSkeleton, ElTag } from 'element-plus'
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/checkbox/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/theme-chalk/el-dropdown.css'
import 'element-plus/theme-chalk/el-dropdown-item.css'
import 'element-plus/theme-chalk/el-dropdown-menu.css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/scrollbar/style/css'
import 'element-plus/es/components/skeleton/style/css'
import 'element-plus/es/components/tag/style/css'

import { askQuestion, createConversation, fetchConversation, fetchConversations, fetchPolicyReader, refreshAnswer, removeConversation, replayAnswer, updateConversation } from '../services/chat'
import { fetchEmployeeSession, fetchHumanChallenge, loginEmployee, logoutEmployee } from '../services/auth'
import { fetchMyFeedback, submitFeedback } from '../services/feedback'
import SliderPuzzleCaptcha from '../components/SliderPuzzleCaptcha.vue'
import type { ChatAnswer, ConversationDetail, ConversationSummary, EmployeeSession, Evidence, FeedbackRecord, FeedbackType, HumanChallenge, PolicyReader, ScenarioChange, ScenarioState } from '../types/api'

const exampleQuestions = ['年假如何计算？', '差旅报销最晚什么时候提交？', '入职需要准备哪些材料？']
const conversations = ref<ConversationSummary[]>([])
const currentConversation = ref<ConversationDetail | null>(null)
const selectedAnswer = ref<ChatAnswer | null>(null)
const selectedEvidence = ref<Evidence | null>(null)
const policyReader = ref<PolicyReader | null>(null)
const question = ref('')
const loadingConversations = ref(false)
const loadingConversation = ref(false)
const submitting = ref(false)
const readerLoading = ref(false)
const readerDialogVisible = ref(false)
const replaying = ref(false)
const refreshing = ref(false)
const errorMessage = ref('')
const scenarioDraft = ref<ScenarioState>({})
const scenarioChanges = ref<ScenarioChange[]>([])
const feedbackRecords = ref<FeedbackRecord[]>([])
const feedbackPageVisible = ref(false)
const feedbackSubmitting = ref(false)
const quickFeedbackSubmitting = ref(false)
const sidebarCollapsed = ref(true)
const historyMobileOpen = ref(false)
const assistantMobileOpen = ref(false)
const policyChangeVisible = ref(false)
const checklistDetailsVisible = ref(false)
const checklistCompletion = reactive<Record<string, boolean[]>>({})
const feedbackError = ref('')
const evidenceError = ref('')
const lastQuestionSubmission = ref({ signature: '', at: 0 })
const titleRevealState = new WeakMap<HTMLElement, { delay?: number; frame?: number }>()
const employeeSession = ref<EmployeeSession>({ authenticated: false, employee: null })
const checkingEmployeeSession = ref(true)
const employeeLoginLoading = ref(false)
const humanChallenge = ref<HumanChallenge | null>(null)
const employeeLoginForm = reactive({ username: 'staff', password: '88888888', slider_position: null as number | null })
const feedbackForm = reactive({
  feedback_type: 'wrong_answer' as FeedbackType,
  content: '',
  is_anonymous: true,
})

const currentConversationId = computed(() => currentConversation.value?.id)
const answerVersions = computed(() => {
  const answers = currentConversation.value?.answers ?? []
  const active = selectedAnswer.value
  if (!active) return []
  const byId = new Map(answers.map((answer) => [answer.answer_id, answer]))
  const rootId = (answer: ChatAnswer): string => {
    let current = answer
    const visited = new Set<string>()
    while (current.source_answer_id && byId.has(current.source_answer_id) && !visited.has(current.answer_id)) {
      visited.add(current.answer_id)
      current = byId.get(current.source_answer_id)!
    }
    return current.answer_id
  }
  const activeRoot = rootId(active)
  return answers.filter((answer) => rootId(answer) === activeRoot)
})
const statusPresentation = computed(() => {
  const status = selectedAnswer.value?.status
  if (selectedAnswer.value?.decision === 'conditional') return { label: '条件不足，待补充', type: 'warning' as const }
  if (selectedAnswer.value?.decision === 'denied') return { label: '已有明确否定结论', type: 'info' as const }
  if (status === 'answer') return { label: '证据已验证', type: 'success' as const }
  if (status === 'degraded') return { label: '仅展示本地证据', type: 'warning' as const }
  if (status === 'refusal') return { label: '依据不足，已拒答', type: 'info' as const }
  if (status === 'clarification') return { label: '需要补充条件', type: 'warning' as const }
  return null
})
const actionSections = computed(() => {
  const card = selectedAnswer.value?.checklist ?? selectedAnswer.value?.action_card
  if (!card) return []
  return [
    { key: 'timeline', title: '按时办理', items: card.timeline },
    { key: 'materials', title: '准备与提交', items: card.materials },
    { key: 'cautions', title: '核对与注意', items: card.cautions },
  ].filter((section) => section.items.length)
})
const checklistCard = computed(() => selectedAnswer.value?.checklist ?? selectedAnswer.value?.action_card)
const matterLabels: Record<string, string> = {
  annual_leave: '年假', travel: '差旅报销', resignation: '离职', attendance: '考勤', onboarding: '入职转正',
}
const checklistTasks = computed(() => {
  const tasks = checklistCard.value?.tasks ?? []
  if (tasks.length) return tasks
  return actionSections.value.flatMap((section) => section.items.map((item, index) => ({
    ...item,
    id: item.id || `legacy.${section.key}.${index}`,
    category: section.key,
  })))
})
const checklistItems = computed(() => checklistTasks.value.map((item) => item.title))
const checklistItemIds = computed(() => checklistTasks.value.map((item) => item.id))
const currentChecklistCompletion = computed(() => {
  const answerId = selectedAnswer.value?.answer_id
  if (!answerId) return []
  const current = checklistCompletion[answerId] ?? []
  if (!checklistCompletion[answerId] || current.length !== checklistItems.value.length) {
    checklistCompletion[answerId] = checklistItems.value.map((_, index) => current[index] ?? false)
  }
  return checklistCompletion[answerId]
})
const completedChecklistCount = computed(() => currentChecklistCompletion.value.filter(Boolean).length)
const checklistProgress = computed(() => checklistItems.value.length ? Math.round(completedChecklistCount.value / checklistItems.value.length * 100) : 0)
const nextChecklistItem = computed(() => checklistItems.value.find((_, index) => !currentChecklistCompletion.value[index]) ?? null)
const checklistTitle = computed(() => {
  const matter = selectedAnswer.value?.scenario?.matter_type
  return `${matter ? matterLabels[matter] || '事项' : '事项'}办理`
})
const scenarioFields = computed(() => selectedAnswer.value?.scenario_form ?? [])
const employeeKnownContext = computed(() => selectedAnswer.value?.employee_context?.known ?? [])
const employeeProfileRows = computed(() => {
  const employee = employeeSession.value.employee
  if (!employee) return []
  const statusLabels: Record<string, string> = { probation: '试用期', regular: '正式员工', contractor: '合作人员' }
  return [
    ['部门', employee.department || '未配置'],
    ['职位', employee.job_title || '未配置'],
    ['员工状态', employee.employee_status ? statusLabels[employee.employee_status] || employee.employee_status : '未配置'],
    ['入职日期', employee.hire_date || '未配置'],
    ['累计工龄', employee.tenure_years === null || employee.tenure_years === undefined ? '未配置' : `${employee.tenure_years} 年`],
    ['直属负责人', employee.direct_manager || '未配置'],
    ['HRBP', employee.hrbp || '未配置'],
    ['年假额度', employee.annual_leave_entitlement === null || employee.annual_leave_entitlement === undefined ? '未配置' : `${employee.annual_leave_entitlement} 天`],
    ['年假余额', employee.annual_leave_balance === null || employee.annual_leave_balance === undefined ? '未配置' : `${employee.annual_leave_balance} 天`],
  ]
})
const confirmedScenarioCount = computed(() => scenarioFields.value.filter((field) => scenarioDraft.value[field.field] !== undefined).length)
const scenarioMode = computed<'none' | 'required' | 'confirmed'>(() => {
  if (!selectedAnswer.value || !scenarioFields.value.length) return 'none'
  if (selectedAnswer.value.decision !== 'conditional' && confirmedScenarioCount.value !== scenarioFields.value.length) return 'none'
  return confirmedScenarioCount.value === scenarioFields.value.length ? 'confirmed' : 'required'
})
const trustedEvidenceCount = computed(() => new Set(selectedAnswer.value?.claims.flatMap((claim) => claim.evidence_ids) ?? []).size)
const trustPresentation = computed(() => {
  const answer = selectedAnswer.value
  if (!answer || answer.status === 'clarification') return null
  const verified = answer.status === 'answer' && answer.claims.length > 0 && answer.claims.every((claim) => claim.evidence_validated) && answer.evidence_coverage === 1
  if (verified) return { level: '高', state: '已验证', verified: true }
  if (answer.status === 'answer' || answer.degraded) return { level: '需核对', state: '部分依据', verified: false }
  return { level: '依据不足', state: '未验证', verified: false }
})
const contextualQuestions = computed(() => {
  const matter = selectedAnswer.value?.scenario?.matter_type
  const byMatter: Record<string, string[]> = {
    annual_leave: ['年假申请需要准备什么？', '超过计划天数怎么办？'],
    travel: ['差旅报销需要哪些材料？', '超过报销期限还能提交吗？'],
    resignation: ['离职需要完成哪些交接？', '离职证明什么时候办理？'],
    attendance: ['考勤异常需要什么证明？', '超过补卡期限怎么办？'],
    onboarding: ['入职需要准备哪些材料？', '材料暂不齐全怎么办？'],
  }
  return matter ? byMatter[matter] ?? [] : []
})
const feedbackTypeCards: Array<{ value: FeedbackType; title: string; description: string }> = [
  { value: 'wrong_answer', title: '回答错误', description: '回答与制度不一致' },
  { value: 'missing_policy', title: '制度缺失', description: '找不到相关规定' },
  { value: 'unclear', title: '表述不清', description: '回答或制度难以理解' },
  { value: 'missing_process', title: '缺少办理信息', description: '不知道下一步怎么办' },
  { value: 'suggestion', title: '改进建议', description: '希望系统进一步完善' },
]
const pendingFeedbackCount = computed(() => (
  feedbackRecords.value.filter((item) => item.status === 'processing' || item.status === 'open').length
))
const employeePuzzleAligned = computed(() => (
  humanChallenge.value !== null && employeeLoginForm.slider_position !== null
  && Math.abs(employeeLoginForm.slider_position - humanChallenge.value.target_position) <= 3
))

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : '请求失败，请稍后重试'
}

function displayConversationTitle(title: string | null): string {
  return (title || '未命名会话').replace(/^\s*(?:\[演示\]|【演示】)\s*/u, '') || '未命名会话'
}

function stopTitleReveal(event: Event): void {
  const title = (event.currentTarget as HTMLElement).querySelector<HTMLElement>('.conversation-title')
  if (!title) return
  const state = titleRevealState.get(title)
  if (state?.delay) window.clearTimeout(state.delay)
  if (state?.frame) window.cancelAnimationFrame(state.frame)
  titleRevealState.delete(title)
  title.scrollLeft = 0
}

function startTitleReveal(event: Event): void {
  const title = (event.currentTarget as HTMLElement).querySelector<HTMLElement>('.conversation-title')
  if (!title) return
  stopTitleReveal(event)
  const distance = Math.max(0, title.scrollWidth - title.clientWidth)
  if (!distance) return
  const state: { delay?: number; frame?: number } = {}
  state.delay = window.setTimeout(() => {
    const startedAt = performance.now()
    const pixelsPerSecond = 42
    const animate = (now: number) => {
      title.scrollLeft = Math.min(distance, Math.floor((now - startedAt) * pixelsPerSecond / 1000))
      if (title.scrollLeft < distance) state.frame = window.requestAnimationFrame(animate)
    }
    state.frame = window.requestAnimationFrame(animate)
  }, 420)
  titleRevealState.set(title, state)
}

function answerVersionLabel(answer: ChatAnswer, index: number): string {
  const action = answer.generation_kind === 'replay'
    ? '条件更新'
    : answer.generation_kind === 'refresh' ? '按新制度回答' : '初次回答'
  return `第 ${index + 1} 版 · ${action}`
}

function toggleChecklistItem(index: number, event: Event): void {
  const answerId = selectedAnswer.value?.answer_id
  if (!answerId) return
  const next = [...currentChecklistCompletion.value]
  next[index] = (event.target as HTMLInputElement).checked
  checklistCompletion[answerId] = next
}

function captureChecklistState(): { ids: string[]; items: string[]; completion: boolean[] } {
  return { ids: [...checklistItemIds.value], items: [...checklistItems.value], completion: [...currentChecklistCompletion.value] }
}

function restoreMatchingChecklistState(previous: { ids: string[]; items: string[]; completion: boolean[] }): number {
  const answerId = selectedAnswer.value?.answer_id
  if (!answerId) return 0
  checklistCompletion[answerId] = checklistItems.value.map((item, index) => {
    let previousIndex = previous.ids.indexOf(checklistItemIds.value[index])
    if (previousIndex < 0) previousIndex = previous.items.indexOf(item)
    return previousIndex >= 0 ? Boolean(previous.completion[previousIndex]) : false
  })
  return previous.completion.filter((completed, index) => (
    completed
    && !checklistItemIds.value.includes(previous.ids[index])
    && !checklistItems.value.includes(previous.items[index])
  )).length
}

function exportChecklist(): void {
  if (!selectedAnswer.value || !checklistItems.value.length) return
  const lines = [
    checklistTitle.value,
    `已确认条件：${checklistCard.value?.applicable_conditions.join('；') || '无'}`,
    `完成进度：${completedChecklistCount.value}/${checklistItems.value.length}（${checklistProgress.value}%）`,
    ...checklistItems.value.map((item, index) => `${currentChecklistCompletion.value[index] ? '☑' : '☐'} ${item}`),
    '制度依据：',
    ...selectedAnswer.value.evidence.map((item) => `- ${item.policy_title} ${item.clause_number || item.section_path}（v${item.policy_version}）`),
  ]
  const url = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `${checklistTitle.value}.txt`
  link.click()
  URL.revokeObjectURL(url)
  ElMessage.success('清单已导出')
}

function feedbackTypeLabel(type: FeedbackType): string {
  return { helpful: '回答有帮助', wrong_answer: '回答错误', missing_policy: '制度缺失', outdated_policy: '制度过期', unclear: '表述不清', missing_process: '缺少办理信息', suggestion: '改进建议' }[type]
}

function feedbackEventLabel(action: string): string {
  return {
    submitted: '意见已提交', start_processing: 'HR 已受理', return_open: '等待重新处理',
    retested: '已完成核验', resolve: '已解决', reject: '未进入制度修正流程',
  }[action] || '处理状态已更新'
}

function formatTimelineTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
}

function collapseSidebar(): void {
  if (typeof window !== 'undefined' && window.innerWidth <= 760) historyMobileOpen.value = false
  else sidebarCollapsed.value = true
}

function openHistory(): void {
  if (typeof window !== 'undefined' && window.innerWidth <= 760) {
    sidebarCollapsed.value = false
    historyMobileOpen.value = true
  }
  else sidebarCollapsed.value = false
}

function openAssistant(): void {
  assistantMobileOpen.value = true
}

function feedbackStatusLabel(status: FeedbackRecord['status']): string {
  return { open: '待处理', processing: '处理中', resolved: '已解决', rejected: '已驳回' }[status]
}

function feedbackStatusType(status: FeedbackRecord['status']): 'warning' | 'primary' | 'success' | 'info' {
  return status === 'open' ? 'warning' : status === 'processing' ? 'primary' : status === 'resolved' ? 'success' : 'info'
}

async function loadFeedbackList(): Promise<void> {
  try {
    feedbackRecords.value = await fetchMyFeedback()
    feedbackError.value = ''
  } catch (error) {
    feedbackError.value = readableError(error)
  }
}

async function loadHumanChallenge(): Promise<void> {
  try {
    humanChallenge.value = await fetchHumanChallenge()
    employeeLoginForm.slider_position = null
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function submitEmployeeLogin(): Promise<void> {
  if (!employeeLoginForm.username.trim() || !employeeLoginForm.password || !employeePuzzleAligned.value || !humanChallenge.value) {
    ElMessage.warning('请完整填写账号、密码并完成滑动拼图')
    return
  }
  employeeLoginLoading.value = true
  try {
    employeeSession.value = await loginEmployee(
      employeeLoginForm.username.trim(), employeeLoginForm.password,
      humanChallenge.value.challenge_id, Number(employeeLoginForm.slider_position),
    )
    employeeLoginForm.password = ''
    employeeLoginForm.slider_position = null
    await Promise.all([loadConversationList(), loadFeedbackList()])
    const first = conversations.value[0]
    if (first) await openConversation(first.id)
    ElMessage.success('员工登录成功')
  } catch (error) {
    ElMessage.error(readableError(error))
    await loadHumanChallenge()
  } finally {
    employeeLoginLoading.value = false
  }
}

async function signOutEmployee(): Promise<void> {
  try {
    await logoutEmployee()
    employeeSession.value = { authenticated: false, employee: null }
    feedbackPageVisible.value = false
    conversations.value = []
    feedbackRecords.value = []
    currentConversation.value = null
    selectedAnswer.value = null
    employeeLoginForm.password = '88888888'
    await loadHumanChallenge()
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function loadConversationList(): Promise<void> {
  loadingConversations.value = true
  try {
    conversations.value = await fetchConversations()
  } catch (error) {
    errorMessage.value = readableError(error)
  } finally {
    loadingConversations.value = false
  }
}

async function openConversation(id: string): Promise<void> {
  loadingConversation.value = true
  errorMessage.value = ''
  try {
    currentConversation.value = await fetchConversation(id)
    selectedAnswer.value = currentConversation.value.answers.at(-1) ?? null
    scenarioDraft.value = { ...(selectedAnswer.value?.scenario ?? currentConversation.value.scenario) }
    scenarioChanges.value = []
    checklistDetailsVisible.value = false
    selectedEvidence.value = null
    policyReader.value = null
  } catch (error) {
    errorMessage.value = readableError(error)
  } finally {
    loadingConversation.value = false
  }
}

function chooseAnswer(answer: ChatAnswer): void {
  selectedAnswer.value = answer
  scenarioDraft.value = { ...answer.scenario }
  scenarioChanges.value = []
  checklistDetailsVisible.value = false
  selectedEvidence.value = null
  policyReader.value = null
}

async function startConversation(): Promise<void> {
  try {
    const created = await createConversation()
    await loadConversationList()
    await openConversation(created.id)
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function deleteConversation(item: ConversationSummary): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定删除“${item.title || '未命名会话'}”及其历史回答吗？`, '删除会话', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
    await removeConversation(item.id)
    if (currentConversationId.value === item.id) {
      currentConversation.value = null
      selectedAnswer.value = null
      selectedEvidence.value = null
      policyReader.value = null
    }
    await loadConversationList()
    ElMessage.success('会话已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(readableError(error))
  }
}

async function renameConversation(item: ConversationSummary): Promise<void> {
  try {
    const result = await ElMessageBox.prompt('输入新的会话名称', '重命名会话', {
      inputValue: displayConversationTitle(item.title),
      inputPlaceholder: '请输入会话名称',
      inputValidator: (value) => value.trim() ? true : '会话名称不能为空',
      confirmButtonText: '保存', cancelButtonText: '取消',
    })
    const title = result.value.trim()
    await updateConversation(item.id, { title })
    if (currentConversation.value?.id === item.id) currentConversation.value.title = title
    await loadConversationList()
    ElMessage.success('会话名称已更新')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(readableError(error))
  }
}

async function togglePinnedConversation(item: ConversationSummary): Promise<void> {
  try {
    await updateConversation(item.id, { is_pinned: !item.is_pinned })
    await loadConversationList()
    ElMessage.success(item.is_pinned ? '已取消置顶' : '聊天已置顶')
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function handleConversationCommand(item: ConversationSummary, command: 'rename' | 'pin' | 'delete'): Promise<void> {
  if (command === 'rename') await renameConversation(item)
  else if (command === 'pin') await togglePinnedConversation(item)
  else await deleteConversation(item)
}

function chooseExample(value: string): void {
  question.value = value
}

async function submitSuggested(value: string): Promise<void> {
  question.value = value
  await submitQuestion()
}

async function submitQuestion(): Promise<void> {
  if (submitting.value) return
  const normalized = question.value.trim()
  if (!normalized) {
    ElMessage.warning('请输入制度问题')
    return
  }
  const now = Date.now()
  const signature = `${currentConversationId.value ?? 'new'}:${normalized}`
  if (lastQuestionSubmission.value.signature === signature && now - lastQuestionSubmission.value.at < 1500) return
  lastQuestionSubmission.value = { signature, at: now }
  submitting.value = true
  errorMessage.value = ''
  try {
    const answer = await askQuestion({ question: normalized, conversation_id: currentConversationId.value })
    question.value = ''
    await Promise.all([loadConversationList(), openConversation(answer.conversation_id)])
    selectedAnswer.value = answer
  } catch (error) {
    errorMessage.value = readableError(error)
  } finally {
    submitting.value = false
  }
}

async function reloadOperation(
  answer: ChatAnswer,
  changes: ScenarioChange[] = [],
  previousChecklist?: { ids: string[]; items: string[]; completion: boolean[] },
): Promise<number> {
  await Promise.all([loadConversationList(), openConversation(answer.conversation_id)])
  selectedAnswer.value = answer
  scenarioDraft.value = { ...answer.scenario }
  scenarioChanges.value = changes
  checklistDetailsVisible.value = false
  return previousChecklist ? restoreMatchingChecklistState(previousChecklist) : 0
}

function updateScenarioField(field: string, type: 'select' | 'number' | 'boolean', event: Event): void {
  const raw = (event.target as HTMLInputElement | HTMLSelectElement).value
  const next = { ...scenarioDraft.value }
  if (raw === '') delete next[field]
  else if (type === 'number') next[field] = Number(raw)
  else if (type === 'boolean') next[field] = raw === 'true'
  else {
    const configured = scenarioFields.value.find((item) => item.field === field)
    next[field] = configured?.options?.find((option) => String(option.value) === raw)?.value ?? raw
  }
  scenarioDraft.value = next
}

async function runReplay(): Promise<void> {
  const answer = selectedAnswer.value
  if (!answer) return
  replaying.value = true
  errorMessage.value = ''
  try {
    const previousChecklist = captureChecklistState()
    if (previousChecklist.completion.some(Boolean)) {
      await ElMessageBox.confirm('条件变化将更新当前办理清单。相同事项的完成状态会保留，新增事项将保持未完成。', '更新办理条件', {
        type: 'warning', confirmButtonText: '继续更新', cancelButtonText: '取消',
      })
    }
    const result = await replayAnswer({ answer_id: answer.answer_id, scenario: scenarioDraft.value })
    const resetCount = await reloadOperation(result.answer, result.meta.scenario_changes, previousChecklist)
    ElMessage.success(resetCount
      ? `${result.meta.recalculation_message} ${resetCount} 项已完成任务因清单变化无法可靠保留，已重置为未完成。`
      : result.meta.recalculation_message)
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') errorMessage.value = readableError(error)
  } finally {
    replaying.value = false
  }
}

async function refreshSelected(): Promise<void> {
  const answer = selectedAnswer.value
  if (!answer) return
  refreshing.value = true
  errorMessage.value = ''
  try {
    const previousChecklist = captureChecklistState()
    if (previousChecklist.completion.some(Boolean)) {
      await ElMessageBox.confirm('当前制度版本已变化。刷新后将重新核验清单，并保留仍然相同的已完成事项。', '按当前制度刷新', {
        type: 'warning', confirmButtonText: '重新核验', cancelButtonText: '保留当前清单',
      })
    }
    const result = await refreshAnswer(answer.answer_id)
    const resetCount = await reloadOperation(result.answer, [], previousChecklist)
    ElMessage.success(resetCount
      ? `已按当前启用制度生成新回答；${resetCount} 项已完成任务因流程变化无法可靠保留，已重置为未完成。`
      : '已按当前启用制度生成新回答，旧回答仍保留在历史中')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') errorMessage.value = readableError(error)
  } finally {
    refreshing.value = false
  }
}

function openFeedbackPage(type: FeedbackType = 'wrong_answer'): void {
  Object.assign(feedbackForm, { feedback_type: type, content: '', is_anonymous: true })
  feedbackPageVisible.value = true
}

async function markHelpful(): Promise<void> {
  const answer = selectedAnswer.value
  if (!answer) return
  quickFeedbackSubmitting.value = true
  try {
    await submitFeedback({ answer_id: answer.answer_id, feedback_type: 'helpful', content: '这条回答对我有帮助。', is_anonymous: true })
    await loadFeedbackList()
    ElMessage.success('谢谢你的反馈')
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    quickFeedbackSubmitting.value = false
  }
}

async function sendFeedback(): Promise<void> {
  const answer = selectedAnswer.value
  if (!answer || !feedbackForm.content.trim()) {
    ElMessage.warning('请填写意见内容')
    return
  }
  feedbackSubmitting.value = true
  try {
    await submitFeedback({
      answer_id: answer.answer_id,
      feedback_type: feedbackForm.feedback_type,
      content: feedbackForm.content.trim(),
      is_anonymous: feedbackForm.is_anonymous,
      submitter_name: feedbackForm.is_anonymous ? null : employeeSession.value.employee?.display_name ?? null,
    })
    await loadFeedbackList()
    ElMessage.success('意见已提交，可在处理时间线中跟踪结果')
  } catch (error) {
    errorMessage.value = readableError(error)
  } finally {
    feedbackSubmitting.value = false
  }
}

function evidenceById(id: string): Evidence | undefined {
  return selectedAnswer.value?.evidence.find((item) => item.id === id)
}

async function focusEvidence(evidence: Evidence): Promise<void> {
  selectedEvidence.value = evidence
  readerDialogVisible.value = true
  readerLoading.value = true
  try {
    evidenceError.value = ''
    if (policyReader.value?.policy_version_id !== evidence.policy_version_id) {
      policyReader.value = await fetchPolicyReader(evidence.policy_version_id)
    }
    await nextTick()
    const target = Array.from(document.querySelectorAll<HTMLElement>('[data-anchor]')).find(
      (element) => element.dataset.anchor === evidence.stable_anchor,
    )
    target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  } catch (error) {
    policyReader.value = null
    evidenceError.value = readableError(error)
  } finally {
    readerLoading.value = false
  }
}

async function openPolicyVersion(versionId: number): Promise<void> {
  policyChangeVisible.value = false
  selectedEvidence.value = null
  readerDialogVisible.value = true
  readerLoading.value = true
  try {
    evidenceError.value = ''
    policyReader.value = await fetchPolicyReader(versionId)
  } catch (error) {
    policyReader.value = null
    evidenceError.value = readableError(error)
  } finally {
    readerLoading.value = false
  }
}

onMounted(async () => {
  try {
    employeeSession.value = await fetchEmployeeSession()
    if (employeeSession.value.authenticated) {
      await Promise.all([loadConversationList(), loadFeedbackList()])
      const first = conversations.value[0]
      if (first) await openConversation(first.id)
    } else {
      await loadHumanChallenge()
    }
  } catch (error) {
    ElMessage.error(readableError(error))
    await loadHumanChallenge()
  } finally {
    checkingEmployeeSession.value = false
  }
})
</script>

<template>
  <el-skeleton v-if="checkingEmployeeSession" :rows="8" animated />

  <section v-else-if="!employeeSession.authenticated" class="admin-login-shell employee-login-shell">
    <div class="login-story employee-login-story">
      <p class="eyebrow">实训模拟企业 HR 制度知识库</p>
      <h1>登录后，继续你的制度咨询与意见跟踪</h1>
      <p>查询历史、情景推演和意见处理进度都会保存在员工账号下，便于跨次查看。</p>
      <div class="login-feature-grid"><span>历史咨询可追溯</span><span>意见进度可跟踪</span><span>制度证据可核验</span></div>
      <div class="login-assurance" aria-label="员工使用流程"><span><b>01</b>登录账号</span><span><b>02</b>查询制度</span><span><b>03</b>跟踪意见</span></div>
    </div>
    <el-form class="login-card" label-position="top" @submit.prevent="submitEmployeeLogin">
      <div class="login-card-heading"><span class="panel-index">员工认证</span><h2>登录员工工作台</h2><p>演示账号：staff　密码：88888888</p></div>
      <el-form-item label="用户名"><el-input v-model="employeeLoginForm.username" autocomplete="username" placeholder="请输入员工用户名" /></el-form-item>
      <el-form-item label="密码"><el-input v-model="employeeLoginForm.password" type="password" show-password autocomplete="current-password" placeholder="请输入登录密码" /></el-form-item>
      <el-form-item label="人机验证">
        <slider-puzzle-captcha v-if="humanChallenge" v-model="employeeLoginForm.slider_position" :challenge="humanChallenge" @refresh="loadHumanChallenge" />
        <el-skeleton v-else :rows="2" animated />
      </el-form-item>
      <el-button native-type="submit" type="primary" size="large" :loading="employeeLoginLoading" :disabled="!employeePuzzleAligned">登录员工端</el-button>
    </el-form>
  </section>

  <template v-else>
  <section class="hero-panel compact employee-hero employee-hero-condensed">
    <div class="hero-copy">
      <p class="eyebrow">实训模拟企业 HR 制度知识库</p>
      <h1>今天想了解什么？</h1>
      <p>每条结论都能点回制度原文；需要办理时，会继续确认你的情况并给出下一步。</p>
      <div class="hero-proof" aria-label="产品可信能力">
        <span><i aria-hidden="true"></i>制度原文可追溯</span>
        <span><i aria-hidden="true"></i>办理条件可推演</span>
        <span><i aria-hidden="true"></i>低依据主动拒答</span>
      </div>
      <div class="hero-question-entry"><input v-model="question" type="text" maxlength="1000" placeholder="输入你的问题，例如：我今年有几天年假？" @keydown.enter.prevent="submitQuestion" /><el-button type="primary" :loading="submitting" @click="submitQuestion">立即咨询</el-button></div>
      <div class="hero-common-questions"><span>常问</span><button v-for="item in exampleQuestions" :key="item" type="button" @click="submitSuggested(item)">{{ item.replace(/[？?]$/u, '') }}</button></div>
    </div>
    <div class="hero-cta">
      <el-popover placement="bottom-end" trigger="click" :width="310" popper-class="employee-profile-popover">
        <template #reference><button type="button" class="employee-profile-trigger">{{ employeeSession.employee?.display_name }} <span aria-hidden="true">⌄</span></button></template>
        <div class="employee-profile-summary"><header><strong>个人信息</strong><small>默认收起，仅供本人查看</small></header><dl><div v-for="row in employeeProfileRows" :key="row[0]"><dt>{{ row[0] }}</dt><dd>{{ row[1] }}</dd></div></dl><el-button class="employee-profile-logout" plain @click="signOutEmployee">退出登录</el-button></div>
      </el-popover>
      <div class="hero-actions"><el-button type="primary" plain @click="openFeedbackPage()">意见投递<span v-if="pendingFeedbackCount" class="button-count">{{ pendingFeedbackCount }}</span></el-button></div>
    </div>
  </section>

  <el-alert v-if="errorMessage" class="page-alert" type="error" :title="errorMessage" show-icon closable @close="errorMessage = ''" />

  <div v-if="!feedbackPageVisible" class="mobile-workbench-actions"><button type="button" @click="openHistory">历史对话</button><button type="button" @click="openAssistant">我的办理助手</button></div>
  <button v-if="historyMobileOpen || assistantMobileOpen" class="mobile-drawer-backdrop" type="button" aria-label="关闭侧边面板" @click="historyMobileOpen = false; assistantMobileOpen = false"></button>

  <section v-if="!feedbackPageVisible" class="employee-app-shell" :class="{ 'sidebar-collapsed': sidebarCollapsed }" aria-label="可信制度问答工作台">
    <aside class="employee-sidebar" :class="{ 'mobile-open': historyMobileOpen }" aria-label="历史对话侧边栏">
      <div class="sidebar-heading">
        <template v-if="!sidebarCollapsed"><div><span>历史对话</span><strong>{{ conversations.length }} 个会话</strong></div><button type="button" aria-label="隐藏历史对话侧边栏" @click="collapseSidebar">‹</button></template>
        <button v-else type="button" aria-label="展开历史对话侧边栏" title="展开历史对话" @click="openHistory">›</button>
      </div>
      <template v-if="!sidebarCollapsed">
        <el-button class="sidebar-new-chat" type="primary" @click="startConversation">＋ 新增聊天</el-button>
        <el-skeleton v-if="loadingConversations" :rows="4" animated />
        <el-scrollbar v-else class="conversation-list" max-height="calc(100vh - 340px)">
          <div v-for="item in conversations" :key="item.id" class="conversation-item" :class="{ active: currentConversationId === item.id, pinned: item.is_pinned }" :data-conversation-id="item.id" @mouseenter="startTitleReveal" @mouseleave="stopTitleReveal" @focusin="startTitleReveal" @focusout="stopTitleReveal">
            <button type="button" class="conversation-open-button" @click="openConversation(item.id); historyMobileOpen = false">
              <span class="conversation-title-wrap"><strong class="conversation-title" :title="displayConversationTitle(item.title)"><span>{{ displayConversationTitle(item.title) }}</span></strong><small><span v-if="item.is_pinned" class="pinned-label">已置顶 · </span>{{ item.message_count }} 条消息</small></span>
            </button>
            <span class="conversation-actions"><span v-if="item.has_stale_answers" class="stale-dot" title="含过期回答">!</span><el-dropdown trigger="click" placement="bottom-end" popper-class="conversation-more-popper" @command="handleConversationCommand(item, $event as 'rename' | 'pin' | 'delete')"><button type="button" class="conversation-more-button" :aria-label="`${displayConversationTitle(item.title)}的更多操作`" title="更多操作" @click.stop>•••</button><template #dropdown><el-dropdown-menu><el-dropdown-item command="rename"><span class="conversation-menu-icon" aria-hidden="true">✎</span>重命名</el-dropdown-item><el-dropdown-item command="pin"><span class="conversation-menu-icon" aria-hidden="true">⌖</span>{{ item.is_pinned ? '取消置顶' : '置顶聊天' }}</el-dropdown-item><el-dropdown-item command="delete" divided class="conversation-delete-command"><span class="conversation-menu-icon" aria-hidden="true">⌫</span>删除</el-dropdown-item></el-dropdown-menu></template></el-dropdown></span>
          </div>
          <div v-if="!conversations.length" class="sidebar-empty"><p>还没有历史会话</p><el-button size="small" plain @click="startConversation">开始第一次咨询</el-button></div>
        </el-scrollbar>
      </template>
    </aside>

    <section class="employee-main-grid">
    <article class="workspace-card featured conversation-panel">
      <div class="panel-heading">
        <div><span class="panel-index">01</span><h2>制度咨询</h2></div>
        <el-tag effect="plain">AI 多轮对话</el-tag>
      </div>

      <div class="conversation-surface">
      <div class="chat-stream" aria-live="polite">
        <el-skeleton v-if="loadingConversation" :rows="5" animated />
        <template v-else-if="currentConversation?.messages.length">
          <div v-for="message in currentConversation.messages" :key="message.id" class="chat-message" :class="message.role">
            <span>{{ message.role === 'user' ? '你' : '制度助手' }}</span><p>{{ message.content }}</p>
          </div>
        </template>
        <div v-else class="chat-empty-state"><strong>我现在想问什么？</strong><p>可以直接描述你的问题，制度助手会先给结论，再提供可追溯的制度依据。</p><button type="button" @click="chooseExample('我今年有几天年假？')">试试：我今年有几天年假？</button></div>
      </div>

      <div v-if="contextualQuestions.length" class="question-list compact-list contextual-followups">
        <span>你还可以问</span><button v-for="item in contextualQuestions" :key="item" type="button" @click="submitSuggested(item)">{{ item }}</button>
      </div>
      <div class="question-composer">
        <el-input v-model="question" type="textarea" :rows="3" maxlength="1000" show-word-limit resize="none" placeholder="继续追问，例如：超过期限还能提交吗？" @keydown.ctrl.enter.prevent="submitQuestion" />
        <div><small>{{ currentConversation ? '继续当前会话，不会丢失上下文' : 'Ctrl + Enter 发送' }}</small><el-button type="primary" :loading="submitting" @click="submitQuestion">发送问题</el-button></div>
      </div>
      </div>
    </article>

    <article class="workspace-card answer-panel employee-assistant-panel" :class="{ 'mobile-open': assistantMobileOpen }">
      <div class="panel-heading">
        <div><span class="panel-index">02</span><h2>我的情况与办理助手</h2></div>
        <el-tag v-if="statusPresentation" :type="statusPresentation.type" effect="dark">{{ statusPresentation.label }}</el-tag>
        <button class="mobile-panel-close" type="button" aria-label="关闭我的办理助手" @click="assistantMobileOpen = false">×</button>
      </div>

      <template v-if="selectedAnswer">
        <div v-if="answerVersions.length > 1" class="answer-history" aria-label="当前回答版本">
          <button v-for="(answer, index) in answerVersions" :key="answer.answer_id" type="button" :class="{ active: selectedAnswer.answer_id === answer.answer_id }" @click="chooseAnswer(answer)">
            {{ answerVersionLabel(answer, index) }}
          </button>
        </div>
        <section v-if="selectedAnswer.stale" class="policy-update-card">
          <header><span>⚠</span><div><strong>相关制度已更新，建议重新核验。</strong><small>历史回答和清单继续保留，但不再代表当前有效制度口径。</small></div></header>
          <div v-for="update in selectedAnswer.policy_updates ?? []" :key="update.policy_id" class="policy-version-change"><strong>{{ update.policy_title }}</strong><span>回答依据：v{{ update.previous_version }} · {{ update.previous_effective_date }}</span><b>→</b><span>当前有效：v{{ update.current_version }} · {{ update.current_effective_date }}</span></div>
          <div class="policy-update-actions"><el-button size="small" @click="policyChangeVisible = true">查看制度变化</el-button><el-button type="warning" size="small" :loading="refreshing" @click="refreshSelected">按当前制度重新回答</el-button></div>
        </section>
        <el-alert v-if="selectedAnswer.degraded" class="answer-alert" type="warning" :title="selectedAnswer.summary || '当前仅展示本地检索证据'" show-icon :closable="false" />

        <div v-if="scenarioChanges.length" class="scenario-diff" aria-label="情景变化摘要">
          <strong>本次条件变化</strong>
          <span v-for="item in scenarioChanges" :key="item.field">{{ item.label }}：{{ item.before_label }} → {{ item.after_label }}</span>
        </div>

        <section v-if="employeeKnownContext.length" class="scenario-sandbox employee-profile-context compact-context-card">
          <div><div><span class="scenario-state-icon">✓</span><strong>已自动结合你的员工信息</strong></div><small>仅显示与当前问题相关的条件</small></div>
          <div class="condition-chips compact-context-chips" aria-label="已自动使用的相关条件"><span v-for="field in employeeKnownContext" :key="field.field">{{ field.label }}：{{ field.value_label }}</span></div>
        </section>

        <section v-if="scenarioMode !== 'none'" class="scenario-sandbox" :class="{ confirmed: scenarioMode === 'confirmed' }">
          <div><div><span class="scenario-state-icon">{{ scenarioMode === 'confirmed' ? '✓' : '!' }}</span><strong>{{ scenarioMode === 'confirmed' ? '已使用的补充条件' : '还需要确认' }}</strong></div><small>{{ selectedAnswer.clarification?.question || `${confirmedScenarioCount} / ${scenarioFields.length} 条件已确认` }}</small></div>
          <p class="scenario-matter">办理事项：<strong>{{ matterLabels[String(scenarioDraft.matter_type)] || '待识别' }}</strong></p>
          <div class="scenario-condition-table" role="table" aria-label="办理所需条件">
            <div v-for="field in scenarioFields" :key="field.field" class="scenario-condition-row" role="row">
              <strong>{{ field.label }}<small v-if="field.unit">（{{ field.unit }}）</small></strong>
              <input v-if="field.type === 'number'" class="native-input" type="number" :min="field.min" :max="field.max" :step="field.step" :value="scenarioDraft[field.field] ?? ''" @input="updateScenarioField(field.field, field.type, $event)" />
              <select v-else class="native-input" :value="String(scenarioDraft[field.field] ?? '')" @change="updateScenarioField(field.field, field.type, $event)"><option value="">请选择</option><option v-for="option in field.options" :key="String(option.value)" :value="String(option.value)">{{ option.label }}</option></select>
              <el-tag size="small" :type="scenarioDraft[field.field] !== undefined ? 'success' : 'warning'">{{ scenarioDraft[field.field] !== undefined ? '已确认' : '待确认' }}</el-tag>
              <small v-if="field.constraint_hint" class="scenario-constraint-hint">{{ field.constraint_hint }}</small>
            </div>
          </div>
          <el-button type="primary" plain :loading="replaying" :disabled="confirmedScenarioCount !== scenarioFields.length" @click="runReplay">补充后重新判断</el-button>
          <small v-if="completedChecklistCount" class="checklist-update-note">修改条件会重新生成清单；相同事项的完成状态会保留。</small>
        </section>

        <section v-if="selectedAnswer.status === 'answer' && checklistCard && checklistItems.length" class="process-checklist-card checklist-directly-after-sandbox">
          <header class="process-checklist-heading"><div><span>办理清单</span><h3>{{ checklistTitle }}</h3></div><strong>{{ completedChecklistCount }} / {{ checklistItems.length }}</strong></header>
          <div class="checklist-progress-copy"><span>办理进度</span><strong>{{ completedChecklistCount }} / {{ checklistItems.length }} · {{ checklistProgress }}%</strong></div>
          <div class="checklist-progress-track" role="progressbar" :aria-valuenow="checklistProgress" aria-valuemin="0" aria-valuemax="100"><span :style="{ width: `${checklistProgress}%` }"></span></div>
          <div v-if="nextChecklistItem" class="checklist-next-step"><span>下一步</span><strong>{{ nextChecklistItem }}</strong></div>
          <div v-else class="checklist-complete-message">✓ 办理清单已全部完成</div>
          <ul class="process-checklist-items" aria-label="办理任务清单">
            <li v-for="(item, index) in checklistItems" :key="`${selectedAnswer.answer_id}-${checklistItemIds[index]}`" :class="{ completed: currentChecklistCompletion[index], next: item === nextChecklistItem }">
              <label><input type="checkbox" :checked="currentChecklistCompletion[index]" @change="toggleChecklistItem(index, $event)" /><span>{{ item }}</span></label>
            </li>
          </ul>
          <div class="process-checklist-actions"><button type="button" @click="checklistDetailsVisible = !checklistDetailsVisible">{{ checklistDetailsVisible ? '收起流程' : '查看流程' }}</button><button type="button" @click="exportChecklist">导出清单</button></div>
          <div v-if="checklistDetailsVisible" class="checklist-flow-details">
            <p class="process-flow-disclaimer">以下是事项应经过的办理环节，不代表真实审批进度；实际状态请以业务系统为准。</p>
            <div v-if="checklistCard.estimated_completion" class="process-estimate"><span>预计完成时间</span><strong>{{ checklistCard.estimated_completion }}</strong></div>
            <ol v-if="checklistCard.process_flow?.length" class="business-process-line" aria-label="办理流程">
              <li v-for="step in checklistCard.process_flow" :key="step.id">
                <span class="process-node" aria-hidden="true"></span><div><strong>{{ step.label }}</strong><p>{{ step.detail }}</p><small v-if="step.person_configured === false">未关联具体经办人</small></div>
              </li>
            </ol>
            <template v-else><section v-for="section in actionSections" :key="section.key" class="action-section"><h4>{{ section.title }}</h4><article v-for="step in section.items" :key="`${section.key}-${step.title}-${step.description}`"><strong>{{ step.title }}</strong><p>{{ step.description }}</p></article></section></template>
            <div v-if="checklistCard.basis_evidence_ids?.length" class="process-basis"><span>制度依据</span><div class="evidence-links"><button v-for="id in checklistCard.basis_evidence_ids" :key="id" type="button" :disabled="!evidenceById(id)" @click="evidenceById(id) && focusEvidence(evidenceById(id)!)">查看对应条款</button></div></div>
          </div>
        </section>

        <section v-else-if="selectedAnswer.status !== 'clarification'" class="checklist-empty-state"><strong>办理清单</strong><p>{{ scenarioMode === 'required' ? '补充必要条件后，这里会根据制度依据生成办理清单。' : '当前回答没有可验证的办理步骤。' }}</p></section>

        <div v-if="trustPresentation" class="trust-summary-card"><div><span>回答可信度</span><strong>{{ trustPresentation.level }}</strong></div><div><span>制度依据</span><strong>{{ trustedEvidenceCount }} 条</strong></div><div><span>证据状态</span><strong :class="{ verified: trustPresentation.verified }">{{ trustPresentation.verified ? '✓ ' : '' }}{{ trustPresentation.state }}</strong></div><button v-if="selectedAnswer.evidence.length" type="button" @click="selectedAnswer.evidence[0] && focusEvidence(selectedAnswer.evidence[0])">查看依据</button></div>

        <el-empty v-if="selectedAnswer.status === 'refusal'" description="知识库依据不足，系统没有生成制度结论" :image-size="64" />

        <section class="answer-feedback-prompt"><span>这个回答有帮助吗？</span><div><button type="button" :disabled="quickFeedbackSubmitting" @click="markHelpful">👍 有帮助</button><button type="button" @click="openFeedbackPage('wrong_answer')">👎 有问题</button></div></section>

      </template>
      <div v-else class="assistant-empty-state"><strong>我的情况与办理助手</strong><p>提出问题后，这里会按需展示需要补充的条件、可信制度依据和现有办理清单。</p></div>
    </article>
    </section>
  </section>

  <section v-else class="employee-feedback-page" aria-label="意见投递中心">
    <header class="standalone-page-heading">
      <div><span class="panel-index">意见中心</span><h2>意见投递与处理进度</h2><p>意见会关联当前制度回答；取消匿名后，系统自动使用登录账号姓名，无需重复填写。</p></div>
      <el-button @click="feedbackPageVisible = false">返回制度咨询</el-button>
    </header>
    <div class="feedback-dialog-layout feedback-page-layout">
      <section class="feedback-records-section">
        <div class="dialog-section-heading"><div><strong>投递记录</strong><span>可查看 HR 处理状态与回复时间线</span></div><el-tag effect="plain">{{ feedbackRecords.length }} 条</el-tag></div>
        <el-alert v-if="feedbackError" type="warning" title="意见记录暂时加载失败" :description="feedbackError" show-icon :closable="false" />
        <el-scrollbar v-if="feedbackRecords.length" max-height="560px" class="employee-feedback-list">
          <article v-for="item in feedbackRecords" :key="item.id">
            <div><strong>{{ feedbackTypeLabel(item.feedback_type) }}</strong><el-tag size="small" :type="feedbackStatusType(item.status)">{{ feedbackStatusLabel(item.status) }}</el-tag></div>
            <p>{{ item.content }}</p>
            <ol class="feedback-timeline natural-feedback-timeline"><li v-for="event in item.events" :key="event.id" :class="{ complete: true }"><time>{{ formatTimelineTime(event.created_at) }}</time><strong>{{ feedbackEventLabel(event.action) }}</strong><p v-if="event.note">{{ event.note }}</p></li><li v-if="item.status === 'open'" class="pending"><time>等待中</time><strong>等待 HR 受理</strong></li><li v-else-if="item.status === 'processing'" class="pending"><time>进行中</time><strong>正在核对相关制度</strong></li></ol>
          </article>
        </el-scrollbar>
        <el-empty v-else description="还没有投递记录" :image-size="52" />
      </section>
      <section class="feedback-submit-section">
        <div class="dialog-section-heading"><div><strong>投递新意见</strong><span>{{ selectedAnswer ? '✓ 已关联当前制度回答、会话与制度依据' : '请先选择一条回答再投递' }}</span></div></div>
        <el-form label-position="top">
          <el-form-item label="你遇到了什么问题？"><div class="feedback-type-card-grid"><button v-for="item in feedbackTypeCards" :key="item.value" type="button" :class="{ active: feedbackForm.feedback_type === item.value }" @click="feedbackForm.feedback_type = item.value"><strong>{{ item.title }}</strong><span>{{ item.description }}</span></button></div></el-form-item>
          <el-form-item label="具体哪里有问题？"><el-input v-model="feedbackForm.content" type="textarea" :rows="4" maxlength="1000" show-word-limit placeholder="请说明哪里不准确、缺少什么，或你希望如何改进" /></el-form-item>
          <el-checkbox v-model="feedbackForm.is_anonymous">匿名提交（系统不会保存姓名）</el-checkbox>
          <p v-if="!feedbackForm.is_anonymous" class="account-identity-note">将以 {{ employeeSession.employee?.display_name }} 的身份提交</p>
        </el-form>
        <el-button class="feedback-submit-button" type="primary" :disabled="!selectedAnswer" :loading="feedbackSubmitting" @click="sendFeedback">提交意见</el-button>
      </section>
    </div>
  </section>

  <el-dialog v-model="policyChangeVisible" title="制度版本变化" width="min(720px, 94vw)">
    <div v-if="selectedAnswer?.policy_updates?.length" class="policy-change-dialog"><article v-for="update in selectedAnswer.policy_updates" :key="update.policy_id"><h3>{{ update.policy_title }}</h3><div><section><span>回答依据</span><strong>v{{ update.previous_version }}</strong><small>生效于 {{ update.previous_effective_date }}</small><el-button size="small" @click="openPolicyVersion(update.previous_version_id)">查看历史原文</el-button></section><b>→</b><section class="current"><span>当前有效</span><strong>v{{ update.current_version }}</strong><small>生效于 {{ update.current_effective_date }}</small><el-button size="small" type="primary" plain @click="openPolicyVersion(update.current_version_id)">查看当前原文</el-button></section></div></article></div>
    <el-empty v-else description="暂时无法获取具体版本变化，请直接按当前制度重新回答" :image-size="56" />
  </el-dialog>

  <el-dialog v-model="readerDialogVisible" :title="policyReader?.policy_title || '制度依据'" width="min(900px, 94vw)" class="policy-reader-dialog">
    <el-skeleton v-if="readerLoading" :rows="8" animated />
    <template v-else-if="policyReader">
      <div class="reader-meta"><strong>{{ policyReader.policy_title }}</strong><span>{{ policyReader.policy_code }} · v{{ policyReader.policy_version }} · 生效于 {{ policyReader.effective_date }}</span></div>
      <el-scrollbar class="policy-clauses" max-height="65vh">
        <article v-for="clause in policyReader.clauses" :key="clause.stable_anchor" class="policy-clause" :class="{ highlighted: selectedEvidence?.stable_anchor === clause.stable_anchor }" :data-anchor="clause.stable_anchor">
          <div><span>{{ clause.section_path || '制度正文' }}</span><strong>{{ clause.clause_number || '条款' }}</strong></div><p>{{ clause.text }}</p>
        </article>
      </el-scrollbar>
    </template>
    <div v-else class="reader-error-state"><el-empty description="暂时无法获取制度依据" :image-size="64" /><p>{{ evidenceError }}</p><el-button v-if="selectedEvidence" type="primary" plain @click="focusEvidence(selectedEvidence)">重新加载</el-button></div>
  </el-dialog>
  </template>
</template>
