<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { ElAlert, ElButton, ElCheckbox, ElDialog, ElEmpty, ElForm, ElFormItem, ElInput, ElMessage, ElMessageBox, ElOption, ElScrollbar, ElSelect, ElSkeleton, ElTag } from 'element-plus'
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/checkbox/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/scrollbar/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/skeleton/style/css'
import 'element-plus/es/components/tag/style/css'

import { askQuestion, createConversation, fetchConversation, fetchConversations, fetchPolicyReader, refreshAnswer, removeConversation, replayAnswer } from '../services/chat'
import { fetchMyFeedback, submitFeedback } from '../services/feedback'
import type { ChatAnswer, ClarificationOption, ConversationDetail, ConversationSummary, Evidence, FeedbackRecord, FeedbackType, PolicyReader, ScenarioChange, ScenarioState } from '../types/api'

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
const replaying = ref(false)
const refreshing = ref(false)
const errorMessage = ref('')
const scenarioDraft = ref<ScenarioState>({})
const scenarioChanges = ref<ScenarioChange[]>([])
const feedbackRecords = ref<FeedbackRecord[]>([])
const feedbackDialogVisible = ref(false)
const feedbackSubmitting = ref(false)
const feedbackForm = reactive({
  feedback_type: 'wrong_answer' as FeedbackType,
  content: '',
  is_anonymous: true,
  submitter_name: '',
})

const currentConversationId = computed(() => currentConversation.value?.id)
const statusPresentation = computed(() => {
  const status = selectedAnswer.value?.status
  if (status === 'answer') return { label: '证据已验证', type: 'success' as const }
  if (status === 'degraded') return { label: '仅展示本地证据', type: 'warning' as const }
  if (status === 'refusal') return { label: '依据不足，已拒答', type: 'info' as const }
  if (status === 'clarification') return { label: '需要补充条件', type: 'warning' as const }
  return null
})
const actionSections = computed(() => {
  const card = selectedAnswer.value?.action_card
  if (!card) return []
  return [
    { key: 'timeline', title: '办理时间线', items: card.timeline },
    { key: 'materials', title: '材料与申请', items: card.materials },
    { key: 'cautions', title: '注意事项', items: card.cautions },
  ].filter((section) => section.items.length)
})

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : '请求失败，请稍后重试'
}

function feedbackTypeLabel(type: FeedbackType): string {
  return { wrong_answer: '回答错误', missing_policy: '制度缺失', outdated_policy: '制度过期', unclear: '表述不清', suggestion: '改进建议' }[type]
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
  } catch (error) {
    errorMessage.value = readableError(error)
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

function chooseExample(value: string): void {
  question.value = value
}

async function submitQuestion(): Promise<void> {
  const normalized = question.value.trim()
  if (!normalized) {
    ElMessage.warning('请输入制度问题')
    return
  }
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

async function reloadOperation(answer: ChatAnswer, changes: ScenarioChange[] = []): Promise<void> {
  await Promise.all([loadConversationList(), openConversation(answer.conversation_id)])
  selectedAnswer.value = answer
  scenarioDraft.value = { ...answer.scenario }
  scenarioChanges.value = changes
}

async function applyClarification(option: ClarificationOption): Promise<void> {
  const answer = selectedAnswer.value
  const slot = answer?.clarification?.slot
  if (!answer || !slot) return
  replaying.value = true
  errorMessage.value = ''
  try {
    const scenario = { ...answer.scenario, [slot]: option.value }
    const result = await replayAnswer({ answer_id: answer.answer_id, scenario })
    await reloadOperation(result.answer, result.meta.scenario_changes)
  } catch (error) {
    errorMessage.value = readableError(error)
  } finally {
    replaying.value = false
  }
}

function updateScenarioText(field: 'employee_status' | 'matter_type', event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  const next = { ...scenarioDraft.value }
  if (value) next[field] = value
  else delete next[field]
  scenarioDraft.value = next
}

function updateScenarioNumber(field: 'tenure_years' | 'duration_days', event: Event): void {
  const value = (event.target as HTMLInputElement).value
  const next = { ...scenarioDraft.value }
  if (value === '') delete next[field]
  else next[field] = Number(value)
  scenarioDraft.value = next
}

async function runReplay(): Promise<void> {
  const answer = selectedAnswer.value
  if (!answer) return
  replaying.value = true
  errorMessage.value = ''
  try {
    const result = await replayAnswer({ answer_id: answer.answer_id, scenario: scenarioDraft.value })
    await reloadOperation(result.answer, result.meta.scenario_changes)
  } catch (error) {
    errorMessage.value = readableError(error)
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
    const result = await refreshAnswer(answer.answer_id)
    await reloadOperation(result.answer)
    ElMessage.success('已按当前启用制度生成新回答，旧回答仍保留在历史中')
  } catch (error) {
    errorMessage.value = readableError(error)
  } finally {
    refreshing.value = false
  }
}

function openFeedbackDialog(): void {
  if (!selectedAnswer.value) return
  Object.assign(feedbackForm, { feedback_type: 'wrong_answer', content: '', is_anonymous: true, submitter_name: '' })
  feedbackDialogVisible.value = true
}

async function sendFeedback(): Promise<void> {
  const answer = selectedAnswer.value
  if (!answer || !feedbackForm.content.trim()) {
    ElMessage.warning('请填写意见内容')
    return
  }
  if (!feedbackForm.is_anonymous && !feedbackForm.submitter_name.trim()) {
    ElMessage.warning('实名意见请填写姓名')
    return
  }
  feedbackSubmitting.value = true
  try {
    await submitFeedback({
      answer_id: answer.answer_id,
      feedback_type: feedbackForm.feedback_type,
      content: feedbackForm.content.trim(),
      is_anonymous: feedbackForm.is_anonymous,
      submitter_name: feedbackForm.is_anonymous ? null : feedbackForm.submitter_name.trim(),
    })
    feedbackDialogVisible.value = false
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
  readerLoading.value = true
  try {
    if (policyReader.value?.policy_version_id !== evidence.policy_version_id) {
      policyReader.value = await fetchPolicyReader(evidence.policy_version_id)
    }
    await nextTick()
    const target = Array.from(document.querySelectorAll<HTMLElement>('[data-anchor]')).find(
      (element) => element.dataset.anchor === evidence.stable_anchor,
    )
    target?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    readerLoading.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadConversationList(), loadFeedbackList()])
  const first = conversations.value[0]
  if (first) await openConversation(first.id)
})
</script>

<template>
  <section class="hero-panel compact employee-hero">
    <div class="hero-copy">
      <p class="eyebrow">员工制度助手</p>
      <h1>每条结论，都能点回制度原文</h1>
      <p>支持多轮追问、低依据拒答和 DeepSeek 异常降级。系统只展示服务端已验证的制度结论。</p>
      <div class="hero-proof" aria-label="产品可信能力">
        <span><i aria-hidden="true"></i>制度原文可追溯</span>
        <span><i aria-hidden="true"></i>办理条件可推演</span>
        <span><i aria-hidden="true"></i>低依据主动拒答</span>
      </div>
    </div>
    <div class="hero-cta">
      <small>无需录入员工敏感档案</small>
      <el-button type="primary" size="large" @click="startConversation">新建制度咨询</el-button>
    </div>
  </section>

  <el-alert v-if="errorMessage" class="page-alert" type="error" :title="errorMessage" show-icon closable @close="errorMessage = ''" />

  <section class="workbench-grid employee-workbench" aria-label="可信制度问答工作台">
    <article class="workspace-card conversation-panel">
      <div class="panel-heading">
        <div><span class="panel-index">01</span><h2>多轮对话</h2></div>
        <el-tag effect="plain">{{ conversations.length }} 个会话</el-tag>
      </div>

      <el-skeleton v-if="loadingConversations" :rows="4" animated />
      <el-scrollbar v-else class="conversation-list" max-height="180px">
        <button v-for="item in conversations" :key="item.id" type="button" class="conversation-item" :class="{ active: currentConversationId === item.id }" @click="openConversation(item.id)">
          <span><strong>{{ item.title || '未命名会话' }}</strong><small>{{ item.message_count }} 条消息</small></span>
          <span class="conversation-actions">
            <span v-if="item.has_stale_answers" class="stale-dot" title="含过期回答">!</span>
            <span class="delete-link" role="button" tabindex="0" @click.stop="deleteConversation(item)">删除</span>
          </span>
        </button>
        <p v-if="!conversations.length" class="muted-copy">还没有历史会话，直接提问即可开始。</p>
      </el-scrollbar>

      <div class="chat-stream" aria-live="polite">
        <el-skeleton v-if="loadingConversation" :rows="5" animated />
        <template v-else-if="currentConversation?.messages.length">
          <div v-for="message in currentConversation.messages" :key="message.id" class="chat-message" :class="message.role">
            <span>{{ message.role === 'user' ? '你' : '制度助手' }}</span><p>{{ message.content }}</p>
          </div>
        </template>
        <el-empty v-else description="输入问题开始咨询" :image-size="56" />
      </div>

      <div class="question-list compact-list">
        <button v-for="item in exampleQuestions" :key="item" type="button" @click="chooseExample(item)">{{ item }}</button>
      </div>
      <div class="question-composer">
        <el-input v-model="question" type="textarea" :rows="3" maxlength="1000" show-word-limit resize="none" placeholder="例如：那试用期员工呢？" @keydown.ctrl.enter.prevent="submitQuestion" />
        <div><small>Ctrl + Enter 发送</small><el-button type="primary" :loading="submitting" @click="submitQuestion">发送问题</el-button></div>
      </div>
    </article>

    <article class="workspace-card featured answer-panel">
      <div class="panel-heading">
        <div><span class="panel-index">02</span><h2>情景判断与办事卡</h2></div>
        <el-tag v-if="statusPresentation" :type="statusPresentation.type" effect="dark">{{ statusPresentation.label }}</el-tag>
      </div>

      <template v-if="selectedAnswer">
        <div v-if="currentConversation && currentConversation.answers.length > 1" class="answer-history" aria-label="回答版本历史">
          <button v-for="(answer, index) in currentConversation.answers" :key="answer.answer_id" type="button" :class="{ active: selectedAnswer.answer_id === answer.answer_id }" @click="chooseAnswer(answer)">
            #{{ index + 1 }} {{ answer.generation_kind === 'replay' ? '情景推演' : answer.generation_kind === 'refresh' ? '保鲜刷新' : '原始回答' }}
          </button>
        </div>
        <el-alert v-if="selectedAnswer.stale" type="warning" title="该回答引用的制度已更新，请勿继续作为当前口径使用" show-icon :closable="false" />
        <div v-if="selectedAnswer.stale" class="stale-refresh"><el-button type="warning" size="small" :loading="refreshing" @click="refreshSelected">按当前制度刷新</el-button></div>
        <el-alert v-if="selectedAnswer.degraded" class="answer-alert" type="warning" :title="selectedAnswer.summary || '当前仅展示本地检索证据'" show-icon :closable="false" />
        <div v-else class="answer-summary"><span>回答摘要</span><p>{{ selectedAnswer.summary }}</p></div>

        <section v-if="selectedAnswer.status === 'clarification' && selectedAnswer.clarification" class="clarification-card">
          <span>回答前先确认一个关键条件</span>
          <h3>{{ selectedAnswer.clarification.question }}</h3>
          <div class="clarification-options">
            <el-button v-for="option in selectedAnswer.clarification.options" :key="String(option.value)" :loading="replaying" @click="applyClarification(option)">{{ option.label }}</el-button>
          </div>
        </section>

        <div v-if="scenarioChanges.length" class="scenario-diff" aria-label="情景变化摘要">
          <strong>本次条件变化</strong>
          <span v-for="item in scenarioChanges" :key="item.field">{{ item.label }}：{{ item.before_label }} → {{ item.after_label }}</span>
        </div>

        <section class="scenario-sandbox">
          <div><strong>情景沙盘</strong><small>只保存非敏感办理条件</small></div>
          <div class="scenario-grid">
            <label>员工状态<select class="native-input" :value="scenarioDraft.employee_status || ''" @change="updateScenarioText('employee_status', $event)"><option value="">未设置</option><option value="probation">试用期</option><option value="regular">正式员工</option><option value="contractor">合作人员</option></select></label>
            <label>办理事项<select class="native-input" :value="scenarioDraft.matter_type || ''" @change="updateScenarioText('matter_type', $event)"><option value="">未设置</option><option value="annual_leave">年假</option><option value="travel">差旅报销</option><option value="resignation">离职</option><option value="attendance">考勤</option><option value="onboarding">入职转正</option></select></label>
            <label>累计工龄（年）<input class="native-input" type="number" min="0" max="60" step="0.5" :value="scenarioDraft.tenure_years ?? ''" @input="updateScenarioNumber('tenure_years', $event)" /></label>
            <label>持续天数<input class="native-input" type="number" min="0" max="365" step="1" :value="scenarioDraft.duration_days ?? ''" @input="updateScenarioNumber('duration_days', $event)" /></label>
          </div>
          <el-button type="primary" plain :loading="replaying" @click="runReplay">按新条件重新推演</el-button>
        </section>

        <div v-if="selectedAnswer.status !== 'clarification'" class="coverage-row"><span>证据覆盖率</span><strong>{{ Math.round(selectedAnswer.evidence_coverage * 100) }}%</strong></div>

        <div v-if="selectedAnswer.claims.length" class="claim-list">
          <article v-for="claim in selectedAnswer.claims" :key="claim.id" class="claim-card">
            <span class="claim-number">结论 {{ claim.position }}</span><p>{{ claim.text }}</p>
            <div class="evidence-links">
              <button v-for="id in claim.evidence_ids" :key="id" type="button" :disabled="!evidenceById(id)" @click="evidenceById(id) && focusEvidence(evidenceById(id)!)">
                {{ evidenceById(id)?.policy_title }} · {{ evidenceById(id)?.clause_number || '相关条款' }}
              </button>
            </div>
          </article>
        </div>
        <el-empty v-else-if="selectedAnswer.status === 'refusal'" description="知识库依据不足，系统没有生成制度结论" :image-size="64" />

        <section v-if="selectedAnswer.status === 'answer' && (selectedAnswer.action_card.applicable_conditions.length || actionSections.length)" class="action-card">
          <div class="action-card-heading"><span>一问一办</span><strong>{{ selectedAnswer.action_card.conclusion || selectedAnswer.summary }}</strong></div>
          <div v-if="selectedAnswer.action_card.applicable_conditions.length" class="condition-chips"><span v-for="item in selectedAnswer.action_card.applicable_conditions" :key="item">{{ item }}</span></div>
          <section v-for="section in actionSections" :key="section.key" class="action-section">
            <h3>{{ section.title }}</h3>
            <article v-for="step in section.items" :key="`${section.key}-${step.title}-${step.description}`">
              <strong>{{ step.title }}</strong><p>{{ step.description }}</p>
              <div class="evidence-links"><button v-for="id in step.evidence_ids" :key="id" type="button" :disabled="!evidenceById(id)" @click="evidenceById(id) && focusEvidence(evidenceById(id)!)">查看制度依据</button></div>
            </article>
          </section>
        </section>

        <section class="feedback-community-card">
          <div class="feedback-community-heading"><div><span>制度共创</span><strong>发现问题，交给 HR 闭环</strong></div><el-button type="primary" plain @click="openFeedbackDialog">提交意见</el-button></div>
          <div v-if="feedbackRecords.length" class="employee-feedback-list">
            <article v-for="item in feedbackRecords.slice(0, 3)" :key="item.id">
              <div><strong>{{ feedbackTypeLabel(item.feedback_type) }}</strong><el-tag size="small" :type="feedbackStatusType(item.status)">{{ feedbackStatusLabel(item.status) }}</el-tag></div>
              <p>{{ item.content }}</p>
              <ol class="feedback-timeline"><li v-for="event in item.events" :key="event.id"><span>{{ event.action }}</span>{{ event.note || '状态已更新' }}</li></ol>
            </article>
          </div>
          <p v-else class="muted-copy">尚未提交意见。反馈会自动携带当前回答和证据快照。</p>
        </section>
      </template>
      <el-empty v-else description="选择会话或发送问题查看可信结论" :image-size="72" />
    </article>

    <article class="workspace-card reader-panel">
      <div class="panel-heading">
        <div><span class="panel-index">03</span><h2>制度证据阅读器</h2></div>
        <el-tag v-if="policyReader" type="success" effect="plain">v{{ policyReader.policy_version }}</el-tag>
      </div>
      <el-skeleton v-if="readerLoading" :rows="8" animated />
      <template v-else-if="policyReader">
        <div class="reader-meta"><strong>{{ policyReader.policy_title }}</strong><span>{{ policyReader.policy_code }} · 生效于 {{ policyReader.effective_date }}</span></div>
        <el-scrollbar class="policy-clauses" max-height="620px">
          <article v-for="clause in policyReader.clauses" :key="clause.stable_anchor" class="policy-clause" :class="{ highlighted: selectedEvidence?.stable_anchor === clause.stable_anchor }" :data-anchor="clause.stable_anchor">
            <div><span>{{ clause.section_path || '制度正文' }}</span><strong>{{ clause.clause_number || '条款' }}</strong></div><p>{{ clause.text }}</p>
          </article>
        </el-scrollbar>
      </template>
      <el-empty v-else description="点击结论下方的制度依据，在这里核对原文" :image-size="72" />
    </article>
  </section>

  <el-dialog v-model="feedbackDialogVisible" title="提交制度共创意见" width="min(540px, 92vw)" destroy-on-close>
    <el-form label-position="top">
      <el-form-item label="意见类型"><el-select v-model="feedbackForm.feedback_type"><el-option label="回答错误" value="wrong_answer" /><el-option label="制度缺失" value="missing_policy" /><el-option label="制度过期" value="outdated_policy" /><el-option label="表述不清" value="unclear" /><el-option label="改进建议" value="suggestion" /></el-select></el-form-item>
      <el-form-item label="意见内容"><el-input v-model="feedbackForm.content" type="textarea" :rows="4" maxlength="1000" show-word-limit placeholder="请说明哪里不准确、缺少什么，或你希望如何改进" /></el-form-item>
      <el-checkbox v-model="feedbackForm.is_anonymous">匿名提交（系统不会保存姓名）</el-checkbox>
      <el-form-item v-if="!feedbackForm.is_anonymous" class="feedback-name-field" label="姓名"><el-input v-model="feedbackForm.submitter_name" maxlength="80" placeholder="请输入姓名" /></el-form-item>
    </el-form>
    <template #footer><el-button @click="feedbackDialogVisible = false">取消</el-button><el-button type="primary" :loading="feedbackSubmitting" @click="sendFeedback">提交并保存快照</el-button></template>
  </el-dialog>
</template>
