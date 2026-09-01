<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter, type LocationQueryRaw } from 'vue-router'
import {
  ElAlert, ElButton, ElDialog, ElDrawer, ElEmpty, ElForm, ElFormItem, ElInput, ElMessage, ElMessageBox,
  ElOption, ElSelect, ElSkeleton, ElTable, ElTableColumn, ElTag,
} from 'element-plus'
import 'element-plus/es/components/alert/style/css'
import 'element-plus/es/components/button/style/css'
import 'element-plus/es/components/dialog/style/css'
import 'element-plus/theme-chalk/el-drawer.css'
import 'element-plus/es/components/empty/style/css'
import 'element-plus/es/components/form/style/css'
import 'element-plus/es/components/input/style/css'
import 'element-plus/es/components/message/style/css'
import 'element-plus/es/components/message-box/style/css'
import 'element-plus/es/components/option/style/css'
import 'element-plus/es/components/select/style/css'
import 'element-plus/es/components/skeleton/style/css'
import 'element-plus/es/components/table/style/css'
import 'element-plus/es/components/tag/style/css'

import {
  createPolicyIssueFromInsight, createRegressionCase, deletePolicyVersion, fetchAdminFeedback, fetchAdminPolicyReader, fetchAdminSession, fetchClauseReferences,
  fetchIndexStatus, fetchLatestPolicyGapScan, fetchPolicies, fetchPolicyBriefing, fetchPolicyInsights, fetchPolicyIssues, fetchPolicySummary, fetchRegressionCases, loginAdmin, logoutAdmin, rebuildIndex,
  retestFeedback, retestPolicyIssue, runPolicyGapScan, testSearch, updateFeedbackStatus, updatePolicyIssue, updatePolicyVersion, uploadPolicy,
  type AdminFeedbackFilters, type SearchTestResponse,
} from '../services/admin'
import { fetchHumanChallenge } from '../services/auth'
import AnalyticsTrendChart from '../components/AnalyticsTrendChart.vue'
import SliderPuzzleCaptcha from '../components/SliderPuzzleCaptcha.vue'
import type { AdminSession, AnalyticsQuestion, ClauseReferences, FeedbackRecord, FeedbackType, HumanChallenge, IndexStatus, PolicyBriefing, PolicyClause, PolicyGapIssue, PolicyGapScan, PolicyInsights, PolicyIssue, PolicyIssueSource, PolicyIssueStatus, PolicyReader, PolicySummary, PolicySummaryStats, PolicyVersionSummary, RegressionCase } from '../types/api'

const route = useRoute()
const router = useRouter()

const session = ref<AdminSession>({ authenticated: false, admin: null })
const checkingSession = ref(true)
const dashboardLoading = ref(false)
const policies = ref<PolicySummary[]>([])
const index = ref<IndexStatus | null>(null)
const loginLoading = ref(false)
const uploadLoading = ref(false)
const rebuilding = ref(false)
const searchLoading = ref(false)
const uploadDialogVisible = ref(false)
const previewVisible = ref(false)
const previewReader = ref<PolicyReader | null>(null)
const managementDrawerVisible = ref(false)
const managementDrawerMode = ref<'versions' | 'index' | 'health' | 'policy'>('policy')
const policyDetailTab = ref<'overview' | 'versions' | 'clauses'>('overview')
const policyCategoryFilter = ref('')
const selectedPolicy = ref<PolicySummary | null>(null)
const selectedPolicyVersion = ref<PolicyVersionSummary | null>(null)
const drilldownReader = ref<PolicyReader | null>(null)
const drilldownLoading = ref(false)
const selectedClause = ref<PolicyClause | null>(null)
const clauseReferences = ref<ClauseReferences | null>(null)
const referenceLoading = ref(false)
const searchQuestion = ref('年假如何计算？')
const searchResponse = ref<SearchTestResponse | null>(null)
const searchStatusMessage = ref('')
const searchDetailsVisible = ref(false)
const feedbackRecords = ref<FeedbackRecord[]>([])
const regressionCases = ref<RegressionCase[]>([])
const policyInsights = ref<PolicyInsights | null>(null)
const insightsLoading = ref(false)
const insightsError = ref(false)
const insightsDays = ref<7 | 30>(7)
const attentionDrawerVisible = ref(false)
const selectedAttention = ref<PolicyInsights['attention_changes'][number] | null>(null)
const governanceLoading = ref(false)
const gapScan = ref<PolicyGapScan | null>(null)
const gapScanning = ref(false)
const gapScanError = ref('')
const policyIssues = ref<PolicyIssue[]>([])
const policySummary = ref<PolicySummaryStats | null>(null)
const summaryLoading = ref(false)
const summaryError = ref(false)
const briefing = ref<PolicyBriefing | null>(null)
const briefingLoading = ref(false)
const briefingError = ref(false)
const briefingRange = ref<'today' | 'week'>('today')
const briefingDialogVisible = ref(false)
const issueIdFilter = ref<number[] | null>(null)
const policyIdFilter = ref<number[] | null>(null)
const policyIssueLoading = ref(false)
const questionDrawerVisible = ref(false)
const issueDrawerVisible = ref(false)
const selectedQuestion = ref<AnalyticsQuestion | null>(null)
const selectedPolicyIssue = ref<PolicyIssue | null>(null)
const policyIssueNote = ref('')
const issueFilters = reactive<{
  source: PolicyIssueSource | ''; severity: PolicyIssue['severity'] | ''; status: PolicyIssueStatus | 'open' | ''
  category: PolicyIssue['category'] | ''; policyId: number | ''; policyCategory: string
}>({ source: '', severity: '', status: '', category: '', policyId: '', policyCategory: '' })
const priorityActionLoading = ref<number | null>(null)
const insightsCategoryFilter = ref('')
const feedbackNotes = reactive<Record<string, string>>({})
const feedbackFilters = reactive<AdminFeedbackFilters>({ status: '', feedback_type: '', policy_id: '', date_from: '', date_to: '' })
const loginForm = reactive({ username: 'admin', password: '88888888', slider_position: null as number | null })
const humanChallenge = ref<HumanChallenge | null>(null)
const uploadForm = reactive({ code: '', title: '', category: '', version: '1.0', effective_date: '', file: null as File | null })
const activeAdminView = ref<'dashboard' | 'feedback'>('dashboard')
const activeModule = ref('')
let moduleObserver: IntersectionObserver | null = null
let workflowNavigationInProgress = false
const visibleModuleRatios = new Map<string, number>()
const moduleNavigation = [
  { id: 'management', icon: '▤', label: '制度管理' },
  { id: 'analytics', icon: '◒', label: '数据洞察' },
  { id: 'gaps', icon: '◇', label: '问题中心' },
]
const policyDetailTabs: Array<{ id: 'overview' | 'versions' | 'clauses'; label: string }> = [
  { id: 'overview', label: '制度详情' }, { id: 'versions', label: '版本历史' }, { id: 'clauses', label: '条款目录' },
]

const activeVersionCount = computed(() => policies.value.filter((item) => item.active_version_id !== null).length)
const policyCategories = computed(() => [...new Set(policies.value.map((item) => item.category))].sort())
const visiblePolicies = computed(() => policies.value.filter((item) => (
  (!policyCategoryFilter.value || item.category === policyCategoryFilter.value)
  && (!policyIdFilter.value || policyIdFilter.value.includes(item.id))
)))
const managementDrawerTitle = computed(() => ({
  versions: '全部制度版本', index: '当前索引详情', health: '索引健康状态', policy: selectedPolicy.value?.title || '制度详情',
}[managementDrawerMode.value]))
const indexTagType = computed(() => index.value?.status === 'ready' ? 'success' : index.value?.status === 'stale' ? 'warning' : 'info')
const pendingFeedbackCount = computed(() => feedbackRecords.value.filter((item) => item.status === 'open' || item.status === 'processing').length)
const searchVerdict = computed(() => {
  const results = searchResponse.value?.results ?? []
  const top = results[0]
  const passed = Boolean(top && top.rrf_score > 0 && (top.vector_score >= 0.45 || top.bm25_score > 0))
  return {
    passed,
    label: passed ? '合格' : '不合格',
    description: passed
      ? 'Top 1 返回有效制度条款，且语义或关键词通道达到有效命中条件。'
      : '未返回有效 Top 1 条款，或语义与关键词通道均未达到有效命中条件。',
    top,
  }
})
const sourceLabels: Record<PolicyIssueSource, string> = { ai_scan: 'AI 扫描', qa_insight: '问答发现', employee_feedback: '员工反馈', manual: '人工录入' }
const issueStatusLabels: Record<PolicyIssueStatus, string> = { pending: '待核验', processing: '处理中', resolved: '已解决' }
const issueSourceCounts = computed(() => {
  const counts: Record<string, number> = { all: policyIssues.value.length, ai_scan: 0, qa_insight: 0, employee_feedback: 0, manual: 0 }
  for (const issue of policyIssues.value) for (const source of issue.sources) counts[source] = (counts[source] || 0) + 1
  return counts
})
const pendingIssueOverview = computed(() => {
  const pending = policyIssues.value.filter((issue) => issue.status !== 'resolved')
  return {
    total: pending.length,
    high: pending.filter((issue) => issue.severity === 'high').length,
    medium: pending.filter((issue) => issue.severity === 'medium').length,
    low: pending.filter((issue) => issue.severity === 'low').length,
  }
})
const issueCategories = computed(() => [...new Set(policyIssues.value.map((issue) => issue.category))])
const issuePolicies = computed(() => {
  const values = new Map<number, string>()
  for (const issue of policyIssues.value) for (const policy of issue.policies || []) values.set(policy.policy_id, policy.policy_title)
  return [...values.entries()].map(([policy_id, policy_title]) => ({ policy_id, policy_title })).sort((a, b) => a.policy_title.localeCompare(b.policy_title, 'zh-CN'))
})
const visiblePolicyIssues = computed(() => policyIssues.value.filter((issue) => (
  (!issueFilters.source || issue.sources.includes(issueFilters.source))
  && (!issueFilters.severity || issue.severity === issueFilters.severity)
  && (!issueFilters.status || (issueFilters.status === 'open' ? issue.status !== 'resolved' : issue.status === issueFilters.status))
  && (!issueFilters.category || issue.category === issueFilters.category)
  && (!issueFilters.policyId || (issue.policies || []).some((policy) => policy.policy_id === issueFilters.policyId))
  && (!issueFilters.policyCategory || (issue.policies || []).some((policy) => findPolicy(policy.policy_id)?.category === issueFilters.policyCategory))
  && (!issueIdFilter.value || issueIdFilter.value.includes(issue.id))
)).sort((a, b) => (b.priority_score || 0) - (a.priority_score || 0) || new Date(b.last_seen_at).getTime() - new Date(a.last_seen_at).getTime()))
const highestPriorityIssue = computed(() => visiblePolicyIssues.value.find((issue) => issue.status !== 'resolved') || null)
const remainingPolicyIssues = computed(() => visiblePolicyIssues.value.filter((issue) => issue.id !== highestPriorityIssue.value?.id))
const visibleAttentionChanges = computed(() => policyInsights.value?.attention_changes.filter(
  (item) => !insightsCategoryFilter.value || item.category === insightsCategoryFilter.value,
) ?? [])
const visibleWeakPolicies = computed(() => policyInsights.value?.weak_policies.filter(
  (item) => !insightsCategoryFilter.value || item.category === insightsCategoryFilter.value,
) ?? [])
const insightSummaryText = computed(() => {
  const data = policyInsights.value
  if (!data) return ''
  const trend = data.week.consultation_change_rate === null
    ? '上周同期暂无可比数据'
    : `较上周同期${data.week.consultation_change_rate >= 0 ? '增长' : '下降'} ${Math.abs(data.week.consultation_change_rate * 100).toFixed(1)}%`
  const categories = data.attention_changes.filter((item) => item.current > 0).slice(0, 3).map((item) => item.category)
  const categoryText = categories.length ? `咨询主要集中在${categories.join('、')}` : '当前尚无可归类的咨询'
  const riskText = `目前有 ${data.week.pending_issues} 个待处理制度问题，其中 ${data.week.severity_counts.high} 个为高风险`
  const weak = data.weak_policies.slice(0, 2).map((item) => `《${item.policy_title}》`)
  return `本周员工共咨询 ${data.week.consultations} 次，${trend}。${categoryText}。${riskText}${weak.length ? `，建议优先关注${weak.join('和')}` : ''}。`
})

async function focusPolicyList(): Promise<void> {
  activeModule.value = 'management'
  await nextTick()
  document.getElementById('admin-policy-list')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

type WorkflowModule = 'policies' | 'insights' | 'issues'
const workflowQueryKeys = ['module', 'issue', 'issues', 'risk', 'status', 'type', 'source', 'policy', 'policyCategory', 'category', 'days']

function queryText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

async function navigateWorkflow(module: WorkflowModule, filters: LocationQueryRaw = {}): Promise<void> {
  const query: LocationQueryRaw = { ...route.query }
  for (const key of workflowQueryKeys) delete query[key]
  query.module = module
  Object.assign(query, filters)
  workflowNavigationInProgress = true
  try {
    await router.replace({ name: 'admin-dashboard', query })
    await applyRouteState()
  } finally {
    workflowNavigationInProgress = false
  }
}

async function openIssueCenter(options: {
  severity?: PolicyIssue['severity']; ids?: number[]; issueId?: number; policyId?: number
  policyCategory?: string; category?: PolicyIssue['category']; status?: PolicyIssueStatus | 'open'
} = {}): Promise<void> {
  issueFilters.source = ''
  issueFilters.status = options.status || (options.severity ? 'open' : '')
  issueFilters.severity = options.severity || ''
  issueFilters.category = options.category || ''
  issueFilters.policyId = options.policyId || ''
  issueFilters.policyCategory = options.policyCategory || ''
  issueIdFilter.value = options.issueId ? [options.issueId] : options.ids ?? null
  const policy = options.policyId ? findPolicy(options.policyId) : undefined
  await navigateWorkflow('issues', {
    ...(options.issueId ? { issue: String(options.issueId) } : {}),
    ...(options.ids?.length ? { issues: options.ids.join(',') } : {}),
    ...(options.severity ? { risk: options.severity } : {}),
    ...(issueFilters.status ? { status: issueFilters.status } : {}),
    ...(options.category ? { type: options.category } : {}),
    ...(policy ? { policy: policy.code } : {}),
    ...(options.policyCategory ? { policyCategory: options.policyCategory } : {}),
  })
}

function selectIssueRisk(severity: PolicyIssue['severity'] | ''): void {
  issueFilters.severity = severity
  issueFilters.status = 'open'
  issueFilters.source = ''
  issueFilters.category = ''
  issueFilters.policyId = ''
  issueFilters.policyCategory = ''
  issueIdFilter.value = null
  void syncIssueFiltersToRoute()
}

function issuePolicyText(issue: PolicyIssue): string {
  return issue.policies?.length ? issue.policies.map((item) => `《${item.policy_title}》`).join('、') : '暂未关联具体制度'
}

async function openIssuePolicy(policyId: number): Promise<void> {
  const policy = findPolicy(policyId)
  if (!policy) return
  issueDrawerVisible.value = false
  await navigateWorkflow('policies', { policy: policy.code })
}

async function focusWeakPolicies(): Promise<void> {
  policyCategoryFilter.value = ''
  policyIdFilter.value = policySummary.value?.weak_policy_ids ?? []
  await focusPolicyList()
}

function clearPolicyScope(): void {
  policyIdFilter.value = null
}

function findPolicy(policyId: number): PolicySummary | undefined {
  return policies.value.find((item) => item.id === policyId)
}

async function openBriefingPolicy(policyId: number): Promise<void> {
  const policy = findPolicy(policyId)
  if (policy) await navigateWorkflow('policies', { policy: policy.code })
}

async function openBriefingIssue(issueId: number): Promise<void> {
  briefingDialogVisible.value = false
  await openIssueCenter({ issueId })
}

async function openIssuesForPolicy(policyId: number): Promise<void> {
  briefingDialogVisible.value = false
  await openIssueCenter({ policyId, status: 'open' })
}

async function openInsightsCategory(category: string): Promise<void> {
  briefingDialogVisible.value = false
  await navigateWorkflow('insights', { ...(category ? { category } : {}), days: String(insightsDays.value) })
}

function changeText(value: number): string {
  if (value === 0) return '与上周持平'
  return `较上周${value > 0 ? '增加' : '减少'} ${Math.abs(value)} 个`
}

function openManagementSummary(mode: 'versions' | 'index' | 'health'): void {
  managementDrawerMode.value = mode
  selectedPolicy.value = null
  selectedPolicyVersion.value = null
  drilldownReader.value = null
  selectedClause.value = null
  clauseReferences.value = null
  managementDrawerVisible.value = true
}

async function loadDrilldownReader(version: PolicyVersionSummary): Promise<void> {
  drilldownLoading.value = true
  selectedClause.value = null
  clauseReferences.value = null
  try {
    drilldownReader.value = await fetchAdminPolicyReader(version.id)
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    drilldownLoading.value = false
  }
}

async function openPolicyDetails(
  policy: PolicySummary,
  tab: 'overview' | 'versions' | 'clauses' = 'overview',
  version?: PolicyVersionSummary,
): Promise<void> {
  managementDrawerMode.value = 'policy'
  selectedPolicy.value = policy
  policyDetailTab.value = tab
  selectedPolicyVersion.value = version
    ?? policy.versions?.find((item) => item.id === policy.active_version_id)
    ?? policy.versions?.[0]
    ?? null
  drilldownReader.value = null
  selectedClause.value = null
  clauseReferences.value = null
  managementDrawerVisible.value = true
  if (tab === 'clauses' && selectedPolicyVersion.value) await loadDrilldownReader(selectedPolicyVersion.value)
}

async function selectPolicyVersion(version: PolicyVersionSummary, tab: 'versions' | 'clauses' = 'versions'): Promise<void> {
  selectedPolicyVersion.value = version
  policyDetailTab.value = tab
  selectedClause.value = null
  clauseReferences.value = null
  if (tab === 'clauses') await loadDrilldownReader(version)
}

async function selectPolicyDetailTab(tab: 'overview' | 'versions' | 'clauses'): Promise<void> {
  policyDetailTab.value = tab
  if (tab === 'clauses' && selectedPolicyVersion.value) await loadDrilldownReader(selectedPolicyVersion.value)
}

function openClauseDetail(clause: PolicyClause): void {
  selectedClause.value = clause
  clauseReferences.value = null
}

async function loadClauseReferenceDetails(): Promise<void> {
  if (!selectedClause.value) return
  referenceLoading.value = true
  try {
    clauseReferences.value = await fetchClauseReferences(selectedClause.value.clause_id)
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    referenceLoading.value = false
  }
}

function prepareNewVersion(policy: PolicySummary): void {
  Object.assign(uploadForm, { code: policy.code, title: policy.title, category: policy.category, version: '', effective_date: '', file: null })
  uploadDialogVisible.value = true
}
const adminPuzzleAligned = computed(() => (
  humanChallenge.value !== null && loginForm.slider_position !== null
  && Math.abs(loginForm.slider_position - humanChallenge.value.target_position) <= 3
))

function readableError(error: unknown): string {
  return error instanceof Error ? error.message : '操作失败，请稍后重试'
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`
}

function statusLabel(status: PolicyVersionSummary['status']): string {
  return { active: '已启用', inactive: '已停用', draft: '草稿' }[status]
}

function statusTag(status: PolicyVersionSummary['status']): 'success' | 'info' | 'warning' {
  return status === 'active' ? 'success' : status === 'draft' ? 'warning' : 'info'
}

function feedbackTypeLabel(type: FeedbackType): string {
  return { helpful: '回答有帮助', wrong_answer: '回答错误', missing_policy: '制度缺失', outdated_policy: '制度过期', unclear: '表述不清', missing_process: '缺少办理信息', suggestion: '改进建议' }[type]
}

function feedbackStatusLabel(status: FeedbackRecord['status']): string {
  return { open: '待处理', processing: '处理中', resolved: '已解决', rejected: '已驳回' }[status]
}

function feedbackStatusType(status: FeedbackRecord['status']): 'warning' | 'primary' | 'success' | 'info' {
  return status === 'open' ? 'warning' : status === 'processing' ? 'primary' : status === 'resolved' ? 'success' : 'info'
}

function percent(value: number): string {
  return `${Math.round(value * 100)}%`
}

function gapCategoryLabel(category: PolicyGapIssue['category']): string {
  return { missing_policy: '制度缺失', unclear_rule: '规则不清', conflict: '制度冲突', outdated: '疑似过期', unanswered: '高频未答', accuracy: '回答准确性问题' }[category]
}

function gapSeverityLabel(severity: PolicyGapIssue['severity']): string {
  return { high: '高', medium: '中', low: '低' }[severity]
}

function gapSeverityType(severity: PolicyGapIssue['severity']): 'danger' | 'warning' | 'info' {
  return severity === 'high' ? 'danger' : severity === 'medium' ? 'warning' : 'info'
}

function evidenceTitle(item: Record<string, unknown>): string {
  if (typeof item.question === 'string') return `问答记录：${item.question}`
  if (typeof item.title === 'string') return `制度版本：${item.title}`
  if (typeof item.content === 'string') return '员工意见记录'
  return '扫描数据记录'
}

function evidenceFields(item: Record<string, unknown>): Array<{ label: string; value: string }> {
  const labels: Record<string, string> = {
    ref: '数据标识', status: '处理结果', count: '出现次数', category: '制度分类', version: '制度版本',
    effective_date: '生效日期', type: '意见类型', content: '意见内容', question: '员工问题', title: '制度名称',
  }
  const valueLabels: Record<string, string> = {
    refusal: '拒答', clarification: '需要补充条件', answer: '已回答', degraded: '降级回答',
    wrong_answer: '回答错误', missing_policy: '制度缺失', outdated_policy: '制度过期', unclear: '表述不清', suggestion: '改进建议',
    open: '待处理', processing: '处理中', resolved: '已解决', rejected: '已驳回',
  }
  return Object.entries(item)
    .filter(([key, value]) => key !== 'clauses' && value !== null && value !== undefined && value !== '')
    .map(([key, value]) => ({ label: labels[key] || key, value: valueLabels[String(value)] || String(value) }))
}

function evidenceClauses(item: Record<string, unknown>): string[] {
  return Array.isArray(item.clauses) ? item.clauses.map((value) => String(value)) : []
}

async function jumpToModule(id: string, syncRoute = true): Promise<void> {
  if (syncRoute) {
    const target: Record<string, WorkflowModule> = { management: 'policies', analytics: 'insights', gaps: 'issues' }
    if (target[id]) {
      await navigateWorkflow(target[id])
      return
    }
  }
  activeModule.value = id
  await nextTick()
  document.getElementById(`admin-module-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function syncIssueFiltersToRoute(): Promise<void> {
  const policy = issueFilters.policyId ? findPolicy(issueFilters.policyId) : undefined
  await navigateWorkflow('issues', {
    ...(issueFilters.severity ? { risk: issueFilters.severity } : {}),
    ...(issueFilters.status ? { status: issueFilters.status } : {}),
    ...(issueFilters.category ? { type: issueFilters.category } : {}),
    ...(issueFilters.source ? { source: issueFilters.source } : {}),
    ...(policy ? { policy: policy.code } : {}),
    ...(issueFilters.policyCategory ? { policyCategory: issueFilters.policyCategory } : {}),
  })
}

async function applyRouteState(): Promise<void> {
  if (!session.value.authenticated) return
  const moduleName = queryText(route.query.module)
  if (moduleName === 'issues') {
    const risk = queryText(route.query.risk)
    const status = queryText(route.query.status)
    const category = queryText(route.query.type)
    const source = queryText(route.query.source)
    issueFilters.severity = ['high', 'medium', 'low'].includes(risk) ? risk as PolicyIssue['severity'] : ''
    issueFilters.status = ['open', 'pending', 'processing', 'resolved'].includes(status) ? status as PolicyIssueStatus | 'open' : ''
    issueFilters.category = ['missing_policy', 'unclear_rule', 'conflict', 'outdated', 'unanswered', 'accuracy'].includes(category)
      ? category as PolicyIssue['category'] : ''
    issueFilters.source = ['ai_scan', 'qa_insight', 'employee_feedback', 'manual'].includes(source) ? source as PolicyIssueSource : ''
    issueFilters.policyCategory = queryText(route.query.policyCategory)
    const policyCode = queryText(route.query.policy)
    issueFilters.policyId = policies.value.find((item) => item.code === policyCode)?.id ?? ''
    const explicitIssue = Number(queryText(route.query.issue))
    const issueIds = queryText(route.query.issues).split(',').map(Number).filter((value) => Number.isInteger(value) && value > 0)
    issueIdFilter.value = explicitIssue > 0 ? [explicitIssue] : issueIds.length ? issueIds : null
    await jumpToModule('gaps', false)
    if (explicitIssue > 0) {
      const issue = policyIssues.value.find((item) => item.id === explicitIssue)
      if (issue) openPolicyIssue(issue)
    }
    return
  }
  if (moduleName === 'insights') {
    insightsCategoryFilter.value = queryText(route.query.category)
    const days = Number(queryText(route.query.days))
    if ((days === 7 || days === 30) && days !== insightsDays.value) await loadPolicyInsights(days)
    await jumpToModule('analytics', false)
    return
  }
  if (moduleName === 'policies') {
    const policyCode = queryText(route.query.policy)
    const policy = policies.value.find((item) => item.code === policyCode)
    policyIdFilter.value = policy ? [policy.id] : null
    await jumpToModule('management', false)
    if (policy) await openPolicyDetails(policy, 'overview')
  }
}

function setupModuleObserver(): void {
  moduleObserver?.disconnect()
  visibleModuleRatios.clear()
  if (typeof IntersectionObserver === 'undefined' || activeAdminView.value !== 'dashboard') return
  moduleObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      const id = (entry.target as HTMLElement).id.replace('admin-module-', '')
      if (entry.isIntersecting) visibleModuleRatios.set(id, entry.intersectionRatio)
      else visibleModuleRatios.delete(id)
    }
    const current = [...visibleModuleRatios.entries()].sort((left, right) => right[1] - left[1])[0]
    if (current) activeModule.value = current[0]
  }, { rootMargin: '-140px 0px -48% 0px', threshold: [0.05, 0.2, 0.4, 0.65] })
  for (const item of moduleNavigation) {
    const element = document.getElementById(`admin-module-${item.id}`)
    if (element) moduleObserver.observe(element)
  }
}

function hasRegressionCase(feedbackId: string): boolean {
  return regressionCases.value.some((item) => item.feedback_id === feedbackId)
}

async function loadGovernance(): Promise<void> {
  governanceLoading.value = true
  policyIssueLoading.value = true
  const [feedbackResult, casesResult, gapResult, issueResult] = await Promise.allSettled([
    fetchAdminFeedback(feedbackFilters), fetchRegressionCases(), fetchLatestPolicyGapScan(), fetchPolicyIssues(),
  ])
  if (feedbackResult.status === 'fulfilled') feedbackRecords.value = feedbackResult.value
  if (casesResult.status === 'fulfilled') regressionCases.value = casesResult.value
  if (gapResult.status === 'fulfilled') {
    gapScan.value = gapResult.value
    gapScanError.value = ''
  } else gapScanError.value = readableError(gapResult.reason)
  if (issueResult.status === 'fulfilled') policyIssues.value = issueResult.value
  else ElMessage.error(`制度问题加载失败：${readableError(issueResult.reason)}`)
  governanceLoading.value = false
  policyIssueLoading.value = false
}

async function loadPolicySummary(): Promise<void> {
  summaryLoading.value = true
  summaryError.value = false
  try {
    policySummary.value = await fetchPolicySummary()
  } catch (error) {
    policySummary.value = null
    summaryError.value = true
    console.error('制度管理统计加载失败', error)
  } finally {
    summaryLoading.value = false
  }
}

async function loadBriefing(range: 'today' | 'week' = briefingRange.value): Promise<void> {
  briefingRange.value = range
  briefingLoading.value = true
  briefingError.value = false
  try {
    briefing.value = await fetchPolicyBriefing(range)
  } catch (error) {
    briefing.value = null
    briefingError.value = true
    console.error('HR 制度工作简报加载失败', error)
  } finally {
    briefingLoading.value = false
  }
}

async function switchBriefingRange(range: 'today' | 'week'): Promise<void> {
  if (range === briefingRange.value && briefing.value?.range === range) return
  await loadBriefing(range)
}

async function loadPolicyInsights(days: 7 | 30 = insightsDays.value): Promise<void> {
  insightsDays.value = days
  insightsLoading.value = true
  insightsError.value = false
  try {
    policyInsights.value = await fetchPolicyInsights(days)
  } catch (error) {
    policyInsights.value = null
    insightsError.value = true
    console.error('HR 数据洞察加载失败', error)
  } finally {
    insightsLoading.value = false
  }
}

async function changeInsightsDays(days: 7 | 30): Promise<void> {
  await loadPolicyInsights(days)
  await navigateWorkflow('insights', { ...(insightsCategoryFilter.value ? { category: insightsCategoryFilter.value } : {}), days: String(days) })
}

function weekChangeLabel(value: number | null): string {
  if (value === null) return '上周同期暂无可比数据'
  if (value === 0) return '与上周同期持平'
  return `较上周同期${value > 0 ? '增长' : '下降'} ${Math.abs(value * 100).toFixed(1)}%`
}

function attentionChangeLabel(item: PolicyInsights['attention_changes'][number]): string {
  if (item.previous === 0) return item.current > 0 ? '本周新增' : '—'
  const value = item.change_rate || 0
  return `${value > 0 ? '+' : ''}${(value * 100).toFixed(1)}%`
}

function resolutionTimeLabel(hours: number | null): string {
  if (hours === null) return '暂无处理时长数据'
  return hours < 24 ? `平均 ${hours.toFixed(1)} 小时` : `平均 ${(hours / 24).toFixed(1)} 天`
}

async function scrollToInsightSection(id: string): Promise<void> {
  await nextTick()
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function openAttentionCategory(item: PolicyInsights['attention_changes'][number]): Promise<void> {
  await openIssueCenter({ policyCategory: item.category, status: 'open' })
}

function openAttentionQuestion(question: string, count: number): void {
  const policyIds = selectedAttention.value?.policy_ids ?? []
  openQuestionDiagnostic({
    question, count, status_counts: {}, latest_status: null, last_seen_at: null,
    average_top_score: null, average_retrieval_latency_ms: null, average_total_latency_ms: null,
    policies: policyIds.map((policyId) => ({ policy_id: policyId, policy_title: findPolicy(policyId)?.title || `制度 #${policyId}` })),
    feedback_count: 0, latest_answer: null, ever_missed: false, reason: null, issue_category: null,
  })
}

async function openWeakPolicyIssues(item: PolicyInsights['weak_policies'][number]): Promise<void> {
  await openIssueCenter({ policyId: item.policy_id, status: 'open' })
}

async function scanPolicyGaps(): Promise<void> {
  gapScanning.value = true
  try {
    gapScan.value = await runPolicyGapScan()
    const refreshes = await Promise.allSettled([fetchPolicyIssues(), loadPolicySummary(), loadBriefing(), loadPolicyInsights()])
    if (refreshes[0].status === 'fulfilled') policyIssues.value = refreshes[0].value
    gapScanError.value = ''
    ElMessage.success(`扫描完成，发现 ${gapScan.value.issues.length} 项待核验线索`)
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    gapScanning.value = false
  }
}

async function loadDashboard(): Promise<void> {
  dashboardLoading.value = true
  const [policyResult, indexResult] = await Promise.allSettled([
    fetchPolicies(), fetchIndexStatus(), loadGovernance(), loadPolicySummary(), loadBriefing('today'), loadPolicyInsights(7),
  ])
  if (policyResult.status === 'fulfilled') policies.value = policyResult.value.items
  else ElMessage.error(`制度版本加载失败：${readableError(policyResult.reason)}`)
  if (indexResult.status === 'fulfilled') index.value = indexResult.value
  else ElMessage.error(`索引状态加载失败：${readableError(indexResult.reason)}`)
  dashboardLoading.value = false
}

async function applyFeedbackFilters(): Promise<void> {
  try {
    await loadGovernance()
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

function openQuestionDiagnostic(item: AnalyticsQuestion): void {
  selectedQuestion.value = item
  questionDrawerVisible.value = true
}

async function createIssueFromQuestion(item: AnalyticsQuestion): Promise<void> {
  try {
    const result = await createPolicyIssueFromInsight({
      question: item.question, category: item.issue_category || 'unanswered', occurrences: item.count,
    })
    policyIssues.value = await fetchPolicyIssues()
    await Promise.allSettled([loadPolicySummary(), loadBriefing(), loadPolicyInsights()])
    ElMessage[result.created ? 'success' : 'info'](result.created ? '已创建制度问题，并保留“问答发现”来源' : '该问题已存在，已合并问答来源与信号')
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function applyIssueFilters(): Promise<void> {
  issueIdFilter.value = null
  await syncIssueFiltersToRoute()
}

async function refreshPolicyIssues(): Promise<void> {
  policyIssueLoading.value = true
  try {
    policyIssues.value = await fetchPolicyIssues()
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    policyIssueLoading.value = false
  }
}

function openPolicyIssue(item: PolicyIssue): void {
  selectedPolicyIssue.value = item
  policyIssueNote.value = item.processing_note || ''
  issueDrawerVisible.value = true
}

async function handlePriorityIssue(item: PolicyIssue): Promise<void> {
  if (item.status === 'processing') {
    openPolicyIssue(item)
    return
  }
  if (item.status !== 'pending') return
  priorityActionLoading.value = item.id
  try {
    await updatePolicyIssue(item.id, 'start_processing')
    await refreshPolicyIssues()
    await Promise.allSettled([loadPolicySummary(), loadBriefing(), loadPolicyInsights()])
    const refreshed = policyIssues.value.find((issue) => issue.id === item.id)
    if (refreshed) openPolicyIssue(refreshed)
    ElMessage.success('已进入处理状态，概览与优先级已同步更新')
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    priorityActionLoading.value = null
  }
}

async function handlePolicyIssue(action: 'start_processing' | 'add_note' | 'resolve' | 'reopen'): Promise<void> {
  if (!selectedPolicyIssue.value) return
  try {
    selectedPolicyIssue.value = await updatePolicyIssue(selectedPolicyIssue.value.id, action, policyIssueNote.value.trim() || undefined)
    await refreshPolicyIssues()
    await Promise.allSettled([loadPolicySummary(), loadBriefing(), loadPolicyInsights()])
    if (action === 'resolve') {
      issueDrawerVisible.value = false
      await navigateWorkflow('issues', { status: 'open' })
    }
    ElMessage.success('制度问题状态已更新')
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function runPolicyIssueRetest(): Promise<void> {
  if (!selectedPolicyIssue.value) return
  try {
    await retestPolicyIssue(selectedPolicyIssue.value.id)
    const refreshed = await fetchPolicyIssues()
    policyIssues.value = refreshed
    selectedPolicyIssue.value = refreshed.find((item) => item.id === selectedPolicyIssue.value?.id) ?? selectedPolicyIssue.value
    ElMessage[selectedPolicyIssue.value.last_retest?.passed ? 'success' : 'warning'](
      selectedPolicyIssue.value.last_retest?.passed ? '原问题现在已能找到可信制度依据' : '重新验证仍未通过，请继续完善并同步制度知识',
    )
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function handleFeedback(item: FeedbackRecord, action: 'start_processing' | 'return_open' | 'resolve' | 'reject'): Promise<void> {
  try {
    await updateFeedbackStatus(item.id, action, feedbackNotes[item.id]?.trim() || undefined)
    feedbackNotes[item.id] = ''
    await loadGovernance()
    ElMessage.success('反馈状态与处理事件已更新')
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function runFeedbackRetest(item: FeedbackRecord): Promise<void> {
  try {
    const result = await retestFeedback(item.id)
    await loadGovernance()
    ElMessage[result.passed ? 'success' : 'warning'](result.passed ? '当前制度依据已覆盖原问题，复测通过' : '当前制度依据尚未完整覆盖原问题')
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function solidifyRegression(item: FeedbackRecord): Promise<void> {
  try {
    await createRegressionCase(item.id)
    await loadGovernance()
    ElMessage.success('已固化为回归用例')
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function submitLogin(): Promise<void> {
  if (!loginForm.username.trim() || !loginForm.password || !adminPuzzleAligned.value || !humanChallenge.value) {
    ElMessage.warning('请完整填写账号、密码并完成滑动拼图')
    return
  }
  loginLoading.value = true
  try {
    session.value = await loginAdmin(
      loginForm.username.trim(), loginForm.password, humanChallenge.value.challenge_id, Number(loginForm.slider_position),
    )
    loginForm.password = ''
    loginForm.slider_position = null
    await loadDashboard()
    await applyRouteState()
    await nextTick()
    setupModuleObserver()
    ElMessage.success('登录成功')
  } catch (error) {
    ElMessage.error(readableError(error))
    await loadHumanChallenge()
  } finally {
    loginLoading.value = false
  }
}

async function loadHumanChallenge(): Promise<void> {
  try {
    humanChallenge.value = await fetchHumanChallenge()
    loginForm.slider_position = null
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function signOut(): Promise<void> {
  try {
    await logoutAdmin()
    session.value = { authenticated: false, admin: null }
    policies.value = []
    index.value = null
    searchResponse.value = null
    feedbackRecords.value = []
    regressionCases.value = []
    gapScan.value = null
    policyIssues.value = []
    gapScanError.value = ''
    loginForm.password = '88888888'
    await loadHumanChallenge()
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

function selectFile(event: Event): void {
  uploadForm.file = (event.target as HTMLInputElement).files?.[0] ?? null
}

function resetUploadForm(): void {
  Object.assign(uploadForm, { code: '', title: '', category: '', version: '1.0', effective_date: '', file: null })
}

async function submitUpload(): Promise<void> {
  if (!uploadForm.code.trim() || !uploadForm.title.trim() || !uploadForm.category.trim() || !uploadForm.version.trim() || !uploadForm.effective_date || !uploadForm.file) {
    ElMessage.warning('请完整填写制度元数据并选择文件')
    return
  }
  const body = new FormData()
  body.set('code', uploadForm.code.trim().toUpperCase())
  body.set('title', uploadForm.title.trim())
  body.set('category', uploadForm.category.trim())
  body.set('version', uploadForm.version.trim())
  body.set('effective_date', uploadForm.effective_date)
  body.set('file', uploadForm.file)
  uploadLoading.value = true
  try {
    await uploadPolicy(body)
    uploadDialogVisible.value = false
    resetUploadForm()
    await loadDashboard()
    ElMessage.success('制度解析并保存成功，启用后请同步员工问答知识')
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    uploadLoading.value = false
  }
}

async function changeStatus(version: PolicyVersionSummary, status: PolicyVersionSummary['status']): Promise<void> {
  try {
    if (status === 'active') {
      await ElMessageBox.confirm('启用该版本会在同一事务中停用此制度的其他版本，是否继续？', '启用制度版本', { type: 'warning' })
    }
    await updatePolicyVersion(version.id, { status })
    await loadDashboard()
    ElMessage.success(status === 'active' ? '版本已启用，请确认员工问答已同步最新制度依据' : '版本已停用')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(readableError(error))
  }
}

async function deleteVersion(version: PolicyVersionSummary): Promise<void> {
  try {
    await ElMessageBox.confirm(`确定删除版本 ${version.version}？该操作只允许未启用且未被回答引用的版本。`, '删除版本', { type: 'warning' })
    await deletePolicyVersion(version.id)
    await loadDashboard()
    ElMessage.success('版本已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error(readableError(error))
  }
}

async function previewVersion(version: PolicyVersionSummary): Promise<void> {
  try {
    previewReader.value = await fetchAdminPolicyReader(version.id)
    previewVisible.value = true
  } catch (error) {
    ElMessage.error(readableError(error))
  }
}

async function rebuild(): Promise<void> {
  rebuilding.value = true
  ElMessage.info('正在更新员工问答使用的制度知识，首次运行可能需要 1–3 分钟，请勿关闭页面')
  try {
    index.value = await rebuildIndex()
    ElMessage.success(`制度知识更新成功，共同步 ${index.value.clause_count} 条制度依据`)
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    rebuilding.value = false
  }
}

async function runSearchTest(): Promise<void> {
  if (!searchQuestion.value.trim()) {
    ElMessage.warning('请输入测试问题')
    return
  }
  searchLoading.value = true
  searchStatusMessage.value = '正在检索启用制度，请稍候…'
  try {
    searchResponse.value = await testSearch(searchQuestion.value.trim())
    const count = searchResponse.value.results.length
    searchStatusMessage.value = count ? `检索完成，找到 ${count} 条相关制度依据。` : '检索完成，但没有找到相关制度依据。'
    ElMessage[count ? 'success' : 'warning'](searchStatusMessage.value)
    activeModule.value = 'management'
  } catch (error) {
    searchStatusMessage.value = `检索失败：${readableError(error)}`
    ElMessage.error(searchStatusMessage.value)
  } finally {
    searchLoading.value = false
  }
}

onMounted(async () => {
  try {
    session.value = await fetchAdminSession()
    if (session.value.authenticated) {
      await loadDashboard()
      await applyRouteState()
    }
    else await loadHumanChallenge()
  } catch (error) {
    ElMessage.error(readableError(error))
  } finally {
    checkingSession.value = false
    await nextTick()
    setupModuleObserver()
  }
})

watch(activeAdminView, async (value) => {
  if (value === 'dashboard') {
    await nextTick()
    setupModuleObserver()
  } else {
    moduleObserver?.disconnect()
    visibleModuleRatios.clear()
  }
})

watch(() => route.fullPath, async () => {
  if (session.value.authenticated && !workflowNavigationInProgress) await applyRouteState()
})

onBeforeUnmount(() => moduleObserver?.disconnect())
</script>

<template>
  <el-skeleton v-if="checkingSession" :rows="8" animated />

  <section v-else-if="!session.authenticated" class="admin-login-shell">
    <div class="login-story">
      <p class="eyebrow">实训模拟企业 HR 制度知识库</p>
      <h1>先把制度管可信，再让员工放心问</h1>
      <p>管理员会话受密码哈希、Cookie Session 与 CSRF 三重保护。系统不保存任何真实员工档案。</p>
      <div class="login-feature-grid">
        <span>现行版本唯一</span><span>制度更新不中断服务</span><span>回答依据可追溯</span>
      </div>
      <div class="login-assurance" aria-label="治理流程">
        <span><b>01</b>上传与解析</span>
        <span><b>02</b>审核并启用</span>
        <span><b>03</b>发布最新制度依据</span>
      </div>
    </div>
    <el-form class="login-card" label-position="top" @submit.prevent="submitLogin">
      <div class="login-card-heading"><span class="panel-index">管理员认证</span><h2>登录 HR 控制台</h2><p>演示账号：admin　密码：88888888</p></div>
      <el-form-item label="用户名"><el-input v-model="loginForm.username" autocomplete="username" placeholder="请输入管理员用户名" /></el-form-item>
      <el-form-item label="密码"><el-input v-model="loginForm.password" type="password" show-password autocomplete="current-password" placeholder="至少 8 位密码" @keyup.enter="submitLogin" /></el-form-item>
      <el-form-item label="人机验证">
        <slider-puzzle-captcha v-if="humanChallenge" v-model="loginForm.slider_position" :challenge="humanChallenge" @refresh="loadHumanChallenge" />
        <el-skeleton v-else :rows="2" animated />
      </el-form-item>
      <el-button native-type="submit" type="primary" size="large" :loading="loginLoading" :disabled="!adminPuzzleAligned">登录</el-button>
    </el-form>
  </section>

  <template v-else>
    <section class="hero-panel compact admin-hero">
      <div class="hero-copy"><p class="eyebrow">实训模拟企业 HR 制度知识库</p><h1>制度运营工作台</h1><p>你好，{{ session.admin?.display_name }}。发现员工关注，处理制度问题，并持续完善制度依据。</p></div>
      <div class="admin-hero-side"><span>当前工作区 · HR 管理端</span><div class="hero-actions"><el-button class="feedback-entry-button" type="primary" plain @click="activeAdminView = activeAdminView === 'feedback' ? 'dashboard' : 'feedback'">{{ activeAdminView === 'feedback' ? '返回治理首页' : '意见处理' }}<span v-if="pendingFeedbackCount" class="button-count">{{ pendingFeedbackCount }}</span></el-button><el-button @click="signOut">退出登录</el-button></div></div>
    </section>

    <div v-if="activeAdminView === 'dashboard'" class="admin-dashboard-view">
    <nav class="admin-module-nav" aria-label="HR 功能模块快捷导航">
      <button v-for="item in moduleNavigation" :key="item.id" type="button" :class="{ active: activeModule === item.id }" :aria-label="`跳转到${item.label}`" :title="item.label" @click="jumpToModule(item.id)">
        <span aria-hidden="true">{{ item.icon }}</span><strong v-if="activeModule === item.id">{{ item.label }}</strong>
      </button>
    </nav>

    <section class="metric-grid admin-metrics" aria-label="制度管理概览">
      <article class="metric-card management-metric-card" role="button" tabindex="0" aria-label="查看待处理制度问题" @click="policySummary && openIssueCenter({ ids: policyIssues.filter((item) => item.status !== 'resolved').map((item) => item.id) })" @keydown.enter="policySummary && openIssueCenter({ ids: policyIssues.filter((item) => item.status !== 'resolved').map((item) => item.id) })"><span>待处理制度问题</span><el-skeleton v-if="summaryLoading" :rows="1" animated /><template v-else-if="policySummary"><strong>{{ policySummary.pending_issues }}</strong><small>高 {{ policySummary.severity_counts.high }} · 中 {{ policySummary.severity_counts.medium }} · 低 {{ policySummary.severity_counts.low }}　点击处理</small></template><div v-else class="metric-load-error"><span>加载失败</span><button type="button" @click.stop="loadPolicySummary">重试</button></div></article>
      <article class="metric-card management-metric-card risk-metric-card" role="button" tabindex="0" aria-label="查看高风险制度问题" @click="policySummary && openIssueCenter({ severity: 'high', ids: policyIssues.filter((item) => item.status !== 'resolved' && item.severity === 'high').map((item) => item.id) })" @keydown.enter="policySummary && openIssueCenter({ severity: 'high', ids: policyIssues.filter((item) => item.status !== 'resolved' && item.severity === 'high').map((item) => item.id) })"><span>高风险问题</span><el-skeleton v-if="summaryLoading" :rows="1" animated /><template v-else-if="policySummary"><strong>{{ policySummary.severity_counts.high }}</strong><small>{{ policySummary.high_week_change == null ? '暂无可比历史数据' : changeText(policySummary.high_week_change) }}　点击查看</small></template><div v-else class="metric-load-error"><span>加载失败</span><button type="button" @click.stop="loadPolicySummary">重试</button></div></article>
      <article class="metric-card management-metric-card" role="button" tabindex="0" aria-label="查看本周新增制度问题" @click="policySummary && openIssueCenter({ ids: policySummary.new_issue_ids })" @keydown.enter="policySummary && openIssueCenter({ ids: policySummary.new_issue_ids })"><span>本周新增问题</span><el-skeleton v-if="summaryLoading" :rows="1" animated /><template v-else-if="policySummary"><strong>{{ policySummary.new_this_week }}</strong><small>按本周首次发现时间统计 · 点击查看</small></template><div v-else class="metric-load-error"><span>加载失败</span><button type="button" @click.stop="loadPolicySummary">重试</button></div></article>
      <article class="metric-card management-metric-card" role="button" tabindex="0" aria-label="定位待完善制度" @click="policySummary && focusWeakPolicies()" @keydown.enter="policySummary && focusWeakPolicies()"><span>待完善制度</span><el-skeleton v-if="summaryLoading" :rows="1" animated /><template v-else-if="policySummary"><strong>{{ policySummary.weak_policy_count }}</strong><small>存在待处理制度问题 · 点击定位</small></template><div v-else class="metric-load-error"><span>加载失败</span><button type="button" @click.stop="loadPolicySummary">重试</button></div></article>
    </section>

    <el-alert v-if="index?.stale" class="page-alert" type="warning" title="制度内容已更新，但员工问答尚未同步最新制度依据，请立即更新制度知识。" show-icon :closable="false" />

    <section id="admin-module-management" class="admin-grid admin-module-anchor">
      <article id="admin-policy-list" class="admin-card policy-management-card">
        <div class="card-heading"><div><span class="panel-index">A</span><h2>制度与版本</h2></div><div class="policy-heading-actions"><select v-model="policyCategoryFilter" class="native-input policy-category-filter" aria-label="筛选制度分类"><option value="">全部分类</option><option v-for="category in policyCategories" :key="category" :value="category">{{ category }}</option></select><el-button type="primary" plain @click="uploadDialogVisible = true">新增版本</el-button></div></div>
        <div v-if="policyIdFilter" class="policy-scope-notice"><span>当前仅显示存在待处理问题的制度</span><button type="button" @click="clearPolicyScope">查看全部制度</button></div>
        <el-skeleton v-if="dashboardLoading" :rows="8" animated />
        <el-empty v-else-if="!policies.length" description="尚未上传制度" />
        <el-empty v-else-if="!visiblePolicies.length" description="当前分类暂无制度" :image-size="58" />
        <div v-else class="policy-list">
          <article v-for="policy in visiblePolicies" :key="policy.id" class="policy-item">
            <header><div><span>{{ policy.category }}</span><button type="button" class="policy-data-link policy-title-link" @click="openPolicyDetails(policy)">{{ policy.title }}</button><small>{{ policy.code }}</small></div><button type="button" class="policy-status-link" @click="openPolicyDetails(policy, 'overview')"><el-tag :type="policy.active_version_id ? 'success' : 'info'" effect="plain">{{ policy.active_version_id ? '已有启用版本' : '暂无启用版本' }}</el-tag></button></header>
            <div class="version-list">
              <div v-for="version in policy.versions" :key="version.id" class="version-row">
                <div><button type="button" class="policy-data-link version-link" @click="openPolicyDetails(policy, 'versions', version)">v{{ version.version }}</button><button type="button" class="policy-status-link" @click="openPolicyDetails(policy, 'overview', version)"><el-tag size="small" :type="statusTag(version.status)">{{ statusLabel(version.status) }}</el-tag></button></div>
                <span>生效 {{ version.effective_date }}</span><button type="button" class="policy-data-link clause-count-link" @click="openPolicyDetails(policy, 'clauses', version)">{{ version.clause_count }} 条</button><span>{{ formatBytes(version.size_bytes) }}</span>
                <div class="row-actions">
                  <el-button size="small" @click="previewVersion(version)">预览</el-button>
                  <details class="policy-manage-menu"><summary>管理 <span aria-hidden="true">⌄</span></summary><div class="policy-manage-popover"><button type="button" @click="openPolicyDetails(policy, 'clauses', version)">查看条款</button><button type="button" @click="openPolicyDetails(policy, 'versions', version)">查看版本历史</button><button type="button" @click="prepareNewVersion(policy)">新增版本</button><button type="button" @click="openPolicyDetails(policy, 'clauses', version)">查看引用情况</button><hr /><button v-if="version.status !== 'active'" type="button" @click="changeStatus(version, 'active')">启用制度</button><button v-else type="button" class="warning" @click="changeStatus(version, 'inactive')">停用制度</button><button type="button" class="danger" :disabled="version.status === 'active'" @click="deleteVersion(version)">删除制度</button></div></details>
                </div>
              </div>
            </div>
          </article>
        </div>
      </article>

      <div class="admin-side-stack">
        <article class="admin-card hr-briefing-card">
          <div class="card-heading briefing-card-heading"><div><span class="panel-index">B · {{ briefingRange === 'today' ? '今日建议' : '本周建议' }}</span><h2>HR 制度工作简报</h2></div><div class="briefing-range-switch" aria-label="简报时间范围"><button type="button" :class="{ active: briefingRange === 'today' }" @click="switchBriefingRange('today')">今日</button><button type="button" :class="{ active: briefingRange === 'week' }" @click="switchBriefingRange('week')">本周</button></div></div>
          <el-skeleton v-if="briefingLoading && !briefing" :rows="5" animated />
          <div v-else-if="briefingError" class="briefing-load-error"><strong>工作简报暂时无法加载</strong><el-button size="small" plain @click="loadBriefing()">重新加载</el-button></div>
          <div v-else-if="briefing" class="briefing-recommendations">
            <template v-if="briefing.range === 'today'"><p><strong>{{ briefing.overview.pending_issues }} 个制度问题待处理</strong><button type="button" class="briefing-inline-link" @click="openIssueCenter({ severity: 'high', status: 'open' })">其中 {{ briefing.overview.high_pending_issues }} 个为高风险</button></p><p><strong>员工今日主要关注</strong><button v-if="briefing.concern_categories[0]" type="button" class="briefing-inline-link" @click="openInsightsCategory(briefing.concern_categories[0].category)">{{ briefing.concern_categories.slice(0, 2).map((item) => item.category).join('、') }}</button><span v-else>今日暂无咨询</span></p><p v-if="briefing.priority_issues[0]"><strong>建议优先处理</strong><button type="button" class="briefing-inline-link" @click="openBriefingIssue(briefing.priority_issues[0].id)">“{{ briefing.priority_issues[0].title }}”</button></p></template>
            <template v-else><p><strong>本周新增 {{ briefing.overview.new_issues }} 个制度问题</strong><button type="button" class="briefing-inline-link" @click="openIssueCenter({ severity: 'high', status: 'open' })">当前 {{ briefing.overview.high_pending_issues }} 个高风险问题待处理</button></p><p><strong>员工最关注</strong><button v-if="briefing.concern_categories[0]" type="button" class="briefing-inline-link" @click="openInsightsCategory(briefing.concern_categories[0].category)">{{ briefing.concern_categories.slice(0, 3).map((item) => item.category).join('、') }}</button><span v-else>本周暂无咨询</span></p><p v-if="briefing.weak_policies[0]"><strong>建议优先完善</strong><button type="button" class="briefing-inline-link" @click="openIssuesForPolicy(briefing.weak_policies[0].policy_id)">《{{ briefing.weak_policies[0].policy_title }}》</button></p></template>
          </div>
          <el-button type="primary" plain class="briefing-open-button" :disabled="!briefing" @click="briefingDialogVisible = true">查看完整简报</el-button>
          <details class="advanced-policy-tools">
            <summary>高级信息与发布工具</summary>
            <div class="advanced-tool-block"><header><strong>制度知识发布</strong><el-tag :type="indexTagType">{{ index?.status || 'unknown' }}</el-tag></header><p>{{ index?.stale ? '制度内容已变化，需要更新员工问答知识。' : '员工问答知识与当前启用制度一致。' }}</p><el-button size="small" type="primary" :loading="rebuilding" @click="rebuild">更新制度知识</el-button><el-button size="small" plain @click="openManagementSummary('health')">查看技术状态</el-button></div>
            <div class="advanced-tool-block search-test-card"><strong>检索质量抽查</strong><el-input v-model="searchQuestion" type="textarea" :rows="2" maxlength="1000" placeholder="输入员工可能提出的问题" /><el-button size="small" plain :loading="searchLoading" @click="runSearchTest">运行抽查</el-button><p v-if="searchStatusMessage" class="search-operation-status" aria-live="polite">{{ searchStatusMessage }}</p></div>
          </details>
        </article>

        <article v-if="searchResponse" id="admin-search-results" class="admin-card search-verdict-card" :class="{ passed: searchVerdict.passed, failed: !searchVerdict.passed }">
          <div class="search-verdict-heading"><div><span class="panel-index">验证结论</span><h3>本次 Top 5 检索{{ searchVerdict.label }}</h3></div><el-tag :type="searchVerdict.passed ? 'success' : 'danger'" effect="dark">{{ searchVerdict.label }}</el-tag></div>
          <p>{{ searchVerdict.description }}</p>
          <dl><div><dt>测试问题</dt><dd>{{ searchResponse.question }}</dd></div><div><dt>返回依据</dt><dd>{{ searchResponse.results.length }} 条</dd></div><div v-if="searchVerdict.top"><dt>首条命中</dt><dd>{{ searchVerdict.top.policy_title }} · {{ searchVerdict.top.clause_number || searchVerdict.top.section_path }}</dd></div></dl>
          <el-button type="primary" plain @click="searchDetailsVisible = true">查看诊断详情</el-button>
        </article>
      </div>
    </section>

    <section id="admin-module-analytics" class="governance-section admin-module-anchor">
      <div class="section-heading"><div><span class="panel-index">E</span><h2>数据洞察</h2><p>看清员工关注变化，定位暴露出的制度问题，并找到最值得优先完善的制度。</p></div><el-button plain :loading="insightsLoading" @click="loadPolicyInsights()">刷新数据</el-button></div>
      <el-skeleton v-if="insightsLoading && !policyInsights" :rows="8" animated />
      <div v-else-if="insightsError" class="insight-load-error"><strong>数据洞察暂时无法加载</strong><p>制度管理和问题中心不受影响。</p><el-button size="small" plain @click="loadPolicyInsights()">重新加载</el-button></div>
      <template v-else-if="policyInsights">
        <section class="metric-grid insight-metrics hr-insight-metrics">
          <article class="metric-card" role="button" tabindex="0" @click="scrollToInsightSection('employee-policy-trend')" @keydown.enter="scrollToInsightSection('employee-policy-trend')"><span>本周员工咨询</span><strong>{{ policyInsights.week.consultations }}</strong><small>{{ weekChangeLabel(policyInsights.week.consultation_change_rate) }}</small></article>
          <article class="metric-card" role="button" tabindex="0" @click="openIssueCenter({ status: 'open' })" @keydown.enter="openIssueCenter({ status: 'open' })"><span>待处理制度问题</span><strong>{{ policyInsights.week.pending_issues }}</strong><small><button type="button" @click.stop="openIssueCenter({ severity: 'high', status: 'open' })">高 {{ policyInsights.week.severity_counts.high }}</button> · 中 {{ policyInsights.week.severity_counts.medium }} · 低 {{ policyInsights.week.severity_counts.low }}</small></article>
          <article class="metric-card" role="button" tabindex="0" @click="openIssueCenter({ ids: policyInsights.week.new_issue_ids })" @keydown.enter="openIssueCenter({ ids: policyInsights.week.new_issue_ids })"><span>本周新增制度问题</span><strong>{{ policyInsights.week.new_issues }}</strong><small>{{ policyInsights.week.new_issue_categories.length ? `主要集中：${policyInsights.week.new_issue_categories.slice(0, 2).map((item) => item.category).join('、')}` : '本周暂无新增问题' }}</small></article>
          <article class="metric-card" role="button" tabindex="0" @click="openIssueCenter({ ids: policyInsights.week.resolved_issue_ids })" @keydown.enter="openIssueCenter({ ids: policyInsights.week.resolved_issue_ids })"><span>本周已解决</span><strong>{{ policyInsights.week.resolved_issues }}</strong><small>{{ resolutionTimeLabel(policyInsights.week.average_resolution_hours) }}</small></article>
        </section>

        <article class="admin-card weekly-insight-summary"><span class="panel-index">本周数据摘要</span><p>{{ insightSummaryText }}</p><el-button size="small" type="primary" plain @click="openIssueCenter({ severity: 'high', status: 'open' })">查看高风险问题</el-button></article>
        <div v-if="insightsCategoryFilter" class="active-cross-filter"><span>当前员工关注：{{ insightsCategoryFilter }}</span><button type="button" @click="openInsightsCategory('')">清除筛选</button></div>

        <article id="employee-policy-trend" class="admin-card insight-trend-card insight-scroll-target"><div class="card-heading"><div><span class="panel-index">趋势</span><h3>员工咨询与制度问题趋势</h3><p>每日咨询量与首次发现的制度问题数量。</p></div><div class="range-switch"><button type="button" :class="{ active: insightsDays === 7 }" @click="changeInsightsDays(7)">最近 7 天</button><button type="button" :class="{ active: insightsDays === 30 }" @click="changeInsightsDays(30)">最近 30 天</button></div></div><analytics-trend-chart v-if="policyInsights.daily_trend.some((item) => item.consultations || item.new_issues)" :data="policyInsights.daily_trend" /><div v-else class="insight-empty-state">最近 {{ insightsDays }} 天暂无咨询和新增制度问题</div></article>

        <section class="hr-insight-detail-grid">
          <article id="employee-attention-changes" class="admin-card attention-change-card insight-scroll-target"><div class="card-heading"><div><span class="panel-index">员工关注变化</span><h3>本周与上周同期对比</h3><p>点击类别进入对应制度问题。</p></div></div><div v-if="visibleAttentionChanges.length" class="attention-change-table"><div class="attention-table-head"><span>员工关注</span><span>本周</span><span>上周</span><span>变化</span></div><button v-for="item in visibleAttentionChanges" :key="item.category" type="button" :class="{ growing: item.change_rate !== null && item.change_rate >= 0.2 }" @click="openAttentionCategory(item)"><strong>{{ item.category }}</strong><span>{{ item.current }}</span><span>{{ item.previous }}</span><em>{{ attentionChangeLabel(item) }}</em></button></div><div v-else class="insight-empty-state">当前类别暂无可比较咨询</div></article>

          <article class="admin-card weak-policy-ranking-card"><div class="card-heading"><div><span class="panel-index">待完善制度排行</span><h3>建议优先完善</h3><p>按风险、待处理问题数和员工咨询量排序。</p></div></div><ol v-if="visibleWeakPolicies.length" class="weak-policy-ranking"><li v-for="(item, index) in visibleWeakPolicies" :key="item.policy_id"><b>{{ index + 1 }}</b><div><button type="button" @click="openWeakPolicyIssues(item)">{{ item.policy_title }}</button><p>{{ item.pending_count }} 个待处理问题 · 本周咨询 {{ item.consultations }} 次</p><small>高 {{ item.severity_counts.high }} · 中 {{ item.severity_counts.medium }} · 低 {{ item.severity_counts.low }}</small></div><el-button size="small" plain @click="openWeakPolicyIssues(item)">查看问题</el-button></li></ol><div v-else class="insight-empty-state">当前类别暂无待完善制度</div></article>
        </section>
      </template>
    </section>

    <section id="admin-module-gaps" class="governance-section policy-gap-governance policy-issue-center admin-module-anchor">
      <div class="section-heading">
        <div><span class="panel-index">F</span><h2>制度问题中心</h2><p>统一汇总 AI 扫描、问答发现、员工反馈与人工录入的问题，去重后持续跟踪处理和复测。</p></div>
        <div class="gap-scan-actions"><el-tag v-if="gapScan" effect="plain">{{ gapScan.model_name ? 'AI 语义审计' : '规则降级审计' }}</el-tag><el-button type="primary" :loading="gapScanning" @click="scanPolicyGaps">立即扫描</el-button></div>
      </div>
      <el-alert v-if="gapScanError" class="page-alert" type="warning" title="制度扫描暂不可用，问题中心其他数据不受影响" :description="gapScanError" show-icon :closable="false" />
      <div v-if="gapScanning" class="scan-progress-panel" aria-live="polite">
        <strong>正在执行制度扫描</strong>
        <ol><li v-for="step in ['读取启用制度', '汇总问答异常', '汇总员工反馈', '识别缺失与冲突', '合并重复问题', '生成治理建议']" :key="step"><span>✓</span>{{ step }}</li></ol>
      </div>
      <div v-if="gapScan" class="gap-scan-summary compact-scan-summary">
        <div><strong>{{ gapScan.issues.length }}</strong><span>项本轮线索</span></div>
        <p>{{ gapScan.summary }}</p>
        <small>{{ gapScan.trigger_type === 'scheduled' ? '定期扫描' : '手动扫描' }} · {{ new Date(gapScan.completed_at || gapScan.started_at).toLocaleString() }} · {{ gapScan.policy_count }} 个制度 / {{ gapScan.query_count }} 条问答</small>
      </div>
      <section class="issue-overview" aria-label="待处理问题概览">
        <button type="button" :class="{ active: issueFilters.severity === '' && issueFilters.status === 'open' }" @click="selectIssueRisk('')"><span>待处理问题</span><strong>{{ pendingIssueOverview.total }}</strong><small>查看全部待处理</small></button>
        <button type="button" class="high" :class="{ active: issueFilters.severity === 'high' && issueFilters.status === 'open' }" @click="selectIssueRisk('high')"><span>高风险</span><strong>{{ pendingIssueOverview.high }}</strong><small>优先核验与处理</small></button>
        <button type="button" class="medium" :class="{ active: issueFilters.severity === 'medium' && issueFilters.status === 'open' }" @click="selectIssueRisk('medium')"><span>中风险</span><strong>{{ pendingIssueOverview.medium }}</strong><small>关注持续影响</small></button>
        <button type="button" class="low" :class="{ active: issueFilters.severity === 'low' && issueFilters.status === 'open' }" @click="selectIssueRisk('low')"><span>低风险</span><strong>{{ pendingIssueOverview.low }}</strong><small>纳入制度完善</small></button>
      </section>
      <div class="issue-filter-toolbar">
        <div class="issue-source-tabs" aria-label="问题来源筛选">
          <button v-for="source in [{ value: '', label: '全部', count: issueSourceCounts.all }, { value: 'ai_scan', label: 'AI 扫描', count: issueSourceCounts.ai_scan }, { value: 'qa_insight', label: '问答发现', count: issueSourceCounts.qa_insight }, { value: 'employee_feedback', label: '员工反馈', count: issueSourceCounts.employee_feedback }, { value: 'manual', label: '人工录入', count: issueSourceCounts.manual }]" :key="source.value" type="button" :class="{ active: issueFilters.source === source.value }" @click="issueFilters.source = source.value as PolicyIssueSource | ''; applyIssueFilters()"><span>{{ source.label }}</span><b>{{ source.count }}</b></button>
        </div>
        <select v-model="issueFilters.severity" class="native-input" @change="applyIssueFilters"><option value="">全部风险</option><option value="high">高风险</option><option value="medium">中风险</option><option value="low">低风险</option></select>
        <select v-model="issueFilters.category" class="native-input" aria-label="问题类型" @change="applyIssueFilters"><option value="">全部类型</option><option v-for="category in issueCategories" :key="category" :value="category">{{ gapCategoryLabel(category) }}</option></select>
        <select v-model="issueFilters.policyId" class="native-input" aria-label="涉及制度" @change="applyIssueFilters"><option value="">全部制度</option><option v-for="policy in issuePolicies" :key="policy.policy_id" :value="policy.policy_id">{{ policy.policy_title }}</option></select>
        <select v-model="issueFilters.status" class="native-input" @change="applyIssueFilters"><option value="">全部状态</option><option value="open">待处理</option><option value="pending">待核验</option><option value="processing">处理中</option><option value="resolved">已解决</option></select>
      </div>
      <div v-if="issueFilters.policyCategory" class="active-cross-filter"><span>当前员工关注类别：{{ issueFilters.policyCategory }}</span><button type="button" @click="issueFilters.policyCategory = ''; applyIssueFilters()">清除筛选</button></div>
      <el-skeleton v-if="policyIssueLoading" :rows="6" animated />
      <template v-else>
        <section class="highest-priority-section">
          <div class="priority-section-heading"><div><span>当前最优先处理</span><h3>先处理最影响员工办理的问题</h3></div><small>按风险、近期咨询、持续出现与问题时长综合排序</small></div>
          <article v-if="highestPriorityIssue" class="highest-priority-card">
            <header><div><el-tag :type="gapSeverityType(highestPriorityIssue.severity)">{{ gapSeverityLabel(highestPriorityIssue.severity) }}风险</el-tag><el-tag effect="plain">{{ gapCategoryLabel(highestPriorityIssue.category) }}</el-tag><el-tag :type="highestPriorityIssue.status === 'processing' ? 'primary' : 'warning'">{{ issueStatusLabels[highestPriorityIssue.status] }}</el-tag></div><span>优先处理 #1</span></header>
            <div class="priority-card-body"><div><h3>{{ highestPriorityIssue.title }}</h3><p>{{ highestPriorityIssue.description }}</p><dl><div><dt>涉及制度</dt><dd><template v-if="highestPriorityIssue.policies.length"><button v-for="policy in highestPriorityIssue.policies" :key="policy.policy_id" type="button" @click="openIssuePolicy(policy.policy_id)">《{{ policy.policy_title }}》</button></template><span v-else>暂未关联具体制度</span></dd></div><div><dt>相关咨询</dt><dd>{{ highestPriorityIssue.recent_consultations ? `近 7 天 ${highestPriorityIssue.recent_consultations} 次` : '近 7 天暂无关联咨询' }}<span v-if="highestPriorityIssue.is_recurring"> · 近期持续出现</span></dd></div><div><dt>持续时间</dt><dd>{{ highestPriorityIssue.open_days === 0 ? '今日发现' : `已持续 ${highestPriorityIssue.open_days} 天` }}</dd></div></dl></div><aside><strong>建议动作</strong><p>{{ highestPriorityIssue.suggested_action }}</p></aside></div>
            <footer><el-button plain @click="openPolicyIssue(highestPriorityIssue)">查看详情</el-button><el-button type="primary" :loading="priorityActionLoading === highestPriorityIssue.id" @click="handlePriorityIssue(highestPriorityIssue)">{{ highestPriorityIssue.status === 'processing' ? '继续处理' : '立即处理' }}</el-button></footer>
          </article>
          <div v-else class="priority-empty-state"><strong>{{ pendingIssueOverview.total ? '当前筛选条件下没有待处理问题' : '待处理问题已全部完成' }}</strong><p>{{ pendingIssueOverview.total ? '可以调整风险、类型、制度或状态筛选查看其他问题。' : '新的制度问题出现后，将自动按优先级显示在这里。' }}</p></div>
        </section>

        <section class="remaining-issues-section">
          <div class="priority-section-heading"><div><span>其他问题</span><h3>已按处理优先级排序</h3></div><small>{{ remainingPolicyIssues.length }} 项</small></div>
          <div v-if="remainingPolicyIssues.length" class="compact-policy-issue-list">
            <article v-for="issue in remainingPolicyIssues" :key="issue.id" tabindex="0" @click="openPolicyIssue(issue)" @keydown.enter="openPolicyIssue(issue)">
              <div class="compact-issue-risk"><el-tag size="small" :type="gapSeverityType(issue.severity)">{{ gapSeverityLabel(issue.severity) }}风险</el-tag><span>{{ gapCategoryLabel(issue.category) }}</span></div>
              <div class="compact-issue-main"><h4>{{ issue.title }}</h4><p>{{ issuePolicyText(issue) }}</p><small>{{ issue.recent_consultations ? `近 7 天 ${issue.recent_consultations} 次相关咨询` : `${issue.occurrences} 次累计信号` }}<span v-if="issue.is_recurring"> · 持续出现</span></small></div>
              <el-tag size="small" :type="issue.status === 'resolved' ? 'success' : issue.status === 'processing' ? 'primary' : 'warning'">{{ issueStatusLabels[issue.status] }}</el-tag><b>查看 →</b>
            </article>
          </div>
          <div v-else class="compact-empty-state">当前没有其他符合条件的问题</div>
        </section>
      </template>
    </section>

    </div>

    <section v-else class="governance-section feedback-governance standalone-admin-view">
      <div class="section-heading"><div><span class="panel-index">G</span><h2>反馈闭环与回归</h2><p>状态变化、复测和固化操作全部追加到不可覆盖的处理时间线。</p></div><el-tag effect="plain">{{ feedbackRecords.length }} 条意见 / {{ regressionCases.length }} 个用例</el-tag></div>
      <div class="feedback-filter-bar">
        <select v-model="feedbackFilters.status" class="native-input"><option value="">全部状态</option><option value="open">待处理</option><option value="processing">处理中</option><option value="resolved">已解决</option><option value="rejected">已驳回</option></select>
        <select v-model="feedbackFilters.feedback_type" class="native-input"><option value="">全部类型</option><option value="helpful">回答有帮助</option><option value="wrong_answer">回答错误</option><option value="missing_policy">制度缺失</option><option value="outdated_policy">制度过期</option><option value="unclear">表述不清</option><option value="missing_process">缺少办理信息</option><option value="suggestion">改进建议</option></select>
        <select v-model="feedbackFilters.policy_id" class="native-input"><option value="">全部制度</option><option v-for="policy in policies" :key="policy.id" :value="policy.id">{{ policy.title }}</option></select>
        <input v-model="feedbackFilters.date_from" class="native-input" type="date" aria-label="反馈起始日期" />
        <input v-model="feedbackFilters.date_to" class="native-input" type="date" aria-label="反馈结束日期" />
        <el-button type="primary" :loading="governanceLoading" @click="applyFeedbackFilters">应用筛选</el-button>
      </div>
      <el-skeleton v-if="governanceLoading" :rows="6" animated />
      <el-empty v-else-if="!feedbackRecords.length" description="当前筛选条件下暂无意见" />
      <div v-else class="admin-feedback-list">
        <article v-for="item in feedbackRecords" :key="item.id" class="admin-feedback-item">
          <header><div><el-tag size="small" :type="feedbackStatusType(item.status)">{{ feedbackStatusLabel(item.status) }}</el-tag><strong>{{ feedbackTypeLabel(item.feedback_type) }}</strong><span>{{ item.is_anonymous ? '匿名员工' : item.submitter_name }}</span></div><small>{{ new Date(item.created_at).toLocaleString() }}</small></header>
          <p class="feedback-question">原问题：{{ item.answer_snapshot?.question || '回答已删除，快照仍保留' }}</p>
          <p>{{ item.content }}</p>
          <el-input v-if="item.status === 'open' || item.status === 'processing'" v-model="feedbackNotes[item.id]" type="textarea" :rows="2" maxlength="1000" placeholder="填写处理说明（可选）" />
          <div class="feedback-actions">
            <el-button v-if="item.status === 'open'" size="small" type="primary" @click="handleFeedback(item, 'start_processing')">开始处理</el-button>
            <el-button v-if="item.status === 'processing'" size="small" @click="handleFeedback(item, 'return_open')">退回待处理</el-button>
            <el-button v-if="item.status === 'processing'" size="small" type="success" @click="handleFeedback(item, 'resolve')">标记解决</el-button>
            <el-button v-if="item.status === 'open' || item.status === 'processing'" size="small" type="danger" plain @click="handleFeedback(item, 'reject')">驳回</el-button>
            <el-button size="small" type="warning" plain @click="runFeedbackRetest(item)">复测原问题</el-button>
            <el-button v-if="item.status === 'resolved' && item.last_retest?.passed && !hasRegressionCase(item.id)" size="small" type="success" plain @click="solidifyRegression(item)">固化回归用例</el-button>
          </div>
          <ol class="admin-feedback-timeline"><li v-for="event in item.events" :key="event.id"><span>{{ event.action }}</span><p>{{ event.note || '状态已更新' }}</p><small>{{ new Date(event.created_at).toLocaleString() }}</small></li></ol>
        </article>
      </div>
    </section>
  </template>

  <el-dialog v-model="briefingDialogVisible" :title="briefingRange === 'today' ? 'HR 制度日报' : 'HR 制度周报'" width="min(1040px, 96vw)" class="policy-briefing-dialog">
    <div v-if="briefing" class="full-policy-briefing">
      <section class="briefing-section">
        <div class="briefing-section-heading"><div><span>{{ briefing.range_label }}概览</span><h3>{{ briefing.range === 'today' ? '今日制度运营' : '本周制度运营关键进展' }}</h3></div><small>更新于 {{ new Date(briefing.generated_at).toLocaleString() }}</small></div>
        <div class="briefing-overview-grid">
          <article><span>{{ briefing.range_label }}咨询量</span><strong>{{ briefing.overview.consultations }}</strong></article>
          <article><span>{{ briefing.range_label }}新增问题</span><strong>{{ briefing.overview.new_issues }}</strong></article>
          <article><span>{{ briefing.range === 'today' ? '当前高风险待处理' : '待处理问题' }}</span><strong>{{ briefing.range === 'today' ? briefing.overview.high_pending_issues : briefing.overview.pending_issues }}</strong></article>
          <article><span>{{ briefing.range === 'today' ? '全部待处理问题' : '本周已解决问题' }}</span><strong>{{ briefing.range === 'today' ? briefing.overview.pending_issues : briefing.overview.resolved_issues }}</strong></article>
        </div>
        <div v-if="briefing.range === 'week'" class="briefing-risk-distribution"><span>风险分布</span><el-tag type="danger" effect="plain">高 {{ briefing.summary.severity_counts.high }}</el-tag><el-tag type="warning" effect="plain">中 {{ briefing.summary.severity_counts.medium }}</el-tag><el-tag type="info" effect="plain">低 {{ briefing.summary.severity_counts.low }}</el-tag></div>
      </section>

      <section class="briefing-section">
        <div class="briefing-section-heading"><div><span>优先处理</span><h3>建议{{ briefing.range_label }}优先处理的问题</h3></div><small>按风险、{{ briefing.range_label }}咨询热度和累计信号排序</small></div>
        <div v-if="briefing.priority_issues.length" class="briefing-priority-list">
          <article v-for="item in briefing.priority_issues" :key="item.id">
            <el-tag :type="gapSeverityType(item.severity)" effect="plain">{{ gapSeverityLabel(item.severity) }}风险</el-tag>
            <div><button type="button" class="briefing-issue-link" @click="openBriefingIssue(item.id)">{{ item.title }}</button><p v-if="item.policies.length"><button v-for="policy in item.policies" :key="policy.policy_id" type="button" class="briefing-policy-link" @click="openBriefingPolicy(policy.policy_id)">{{ policy.policy_title }}</button></p><p v-else>暂未关联到具体制度</p></div>
            <span><b>{{ item.consultations }}</b> 次<br /><small>{{ briefing.range_label }}相关咨询</small></span>
            <el-button size="small" type="primary" plain @click="openBriefingIssue(item.id)">查看 / 处理</el-button>
          </article>
        </div>
        <el-empty v-else description="当前没有待处理制度问题" :image-size="52" />
      </section>

      <div class="briefing-two-column">
        <section class="briefing-section">
          <div class="briefing-section-heading"><div><span>员工最关心</span><h3>{{ briefing.range_label }}高频咨询类别</h3></div></div>
          <div v-if="briefing.concern_categories.length" class="briefing-category-list">
            <button v-for="item in briefing.concern_categories" :key="item.category" type="button" @click="openInsightsCategory(item.category)"><div><strong>{{ item.category }}</strong><small>{{ item.count }} 次 · {{ percent(item.share) }}</small></div><i><b :style="{ width: `${item.share * 100}%` }"></b></i></button>
          </div>
          <el-empty v-else :description="`${briefing.range_label}暂无员工咨询`" :image-size="46" />
        </section>

        <section v-if="briefing.range === 'week'" class="briefing-section">
          <div class="briefing-section-heading"><div><span>待完善制度</span><h3>待处理问题较多的制度</h3></div></div>
          <div v-if="briefing.weak_policies.length" class="briefing-weak-list">
            <button v-for="item in briefing.weak_policies.slice(0, 5)" :key="item.policy_id" type="button" @click="openIssuesForPolicy(item.policy_id)"><span><strong>{{ item.policy_title }}</strong><small>{{ item.category }} · 本周咨询 {{ item.consultations }} 次</small></span><em>{{ item.unresolved_count }} 个待处理<span v-if="item.high_count"> · {{ item.high_count }} 个高风险</span></em></button>
          </div>
          <el-empty v-else description="暂无可关联的待完善制度" :image-size="46" />
        </section>
      </div>

      <section v-if="briefing.range === 'week'" class="briefing-section">
        <div class="briefing-section-heading"><div><span>本周变化</span><h3>与上周同期相比</h3></div></div>
        <div class="briefing-change-list">
          <p><strong>员工咨询</strong><span>{{ briefing.changes.consultations.current }} 次，{{ changeText(briefing.changes.consultations.change).replace('个', '次') }}</span></p>
          <p><strong>新增问题</strong><span>{{ briefing.changes.new_issues.current }} 个，{{ changeText(briefing.changes.new_issues.change) }}</span></p>
          <p><strong>解决问题</strong><span>{{ briefing.changes.resolved_issues.current }} 个，{{ changeText(briefing.changes.resolved_issues.change) }}</span></p>
          <p v-if="briefing.changes.leading_category"><strong>主要咨询类别</strong><span>{{ briefing.changes.leading_category.category }} {{ briefing.changes.leading_category.count }} 次<span v-if="briefing.changes.leading_category.change">，较上周{{ briefing.changes.leading_category.change > 0 ? '增加' : '减少' }} {{ Math.abs(briefing.changes.leading_category.change) }} 次</span></span></p>
        </div>
      </section>
    </div>
    <el-empty v-else description="暂无可生成简报的数据" />
  </el-dialog>

  <el-drawer v-model="managementDrawerVisible" :title="managementDrawerTitle" size="min(760px, 96vw)" destroy-on-close>
    <div class="management-drilldown">
      <template v-if="managementDrawerMode === 'versions'">
        <p class="drawer-intro">按制度查看全部真实版本及当前发布状态。</p>
        <section v-for="policy in policies" :key="policy.id" class="version-history-group">
          <header><div><strong>{{ policy.title }}</strong><small>{{ policy.code }} · {{ policy.category }}</small></div><button type="button" class="policy-data-link" @click="openPolicyDetails(policy, 'overview')">查看制度</button></header>
          <div v-for="version in policy.versions" :key="version.id" class="drawer-version-row"><button type="button" class="policy-data-link" @click="openPolicyDetails(policy, 'versions', version)">v{{ version.version }}</button><el-tag size="small" :type="statusTag(version.status)">{{ statusLabel(version.status) }}</el-tag><span>{{ version.effective_date }}</span><button type="button" class="policy-data-link" @click="openPolicyDetails(policy, 'clauses', version)">{{ version.clause_count }} 条</button></div>
        </section>
        <el-empty v-if="!policies.length" description="暂无制度版本" />
      </template>

      <template v-else-if="managementDrawerMode === 'index'">
        <p class="drawer-intro">当前员工问答实际使用的已发布检索快照。</p>
        <dl v-if="index" class="management-detail-list"><div><dt>已发布条款数</dt><dd>{{ index.clause_count }}</dd></div><div><dt>已建立索引数</dt><dd>{{ index.clause_count }}</dd></div><div><dt>当前启用制度数</dt><dd>{{ activeVersionCount }}</dd></div><div><dt>启用制度条款数</dt><dd>{{ index.active_clause_count }}</dd></div><div><dt>Embedding 模型</dt><dd>{{ index.embedding_model }}</dd></div><div><dt>分块器版本</dt><dd>{{ index.chunker_version }}</dd></div><div><dt>最近构建时间</dt><dd>{{ index.built_at ? new Date(index.built_at).toLocaleString() : '尚未构建' }}</dd></div><div><dt>索引指纹</dt><dd class="break-value">{{ index.fingerprint || '暂无' }}</dd></div></dl>
        <el-empty v-else description="索引状态暂不可用" />
      </template>

      <template v-else-if="managementDrawerMode === 'health'">
        <p class="drawer-intro">检查启用制度、条款与检索快照是否保持一致。</p>
        <div v-if="index" class="health-check-list">
          <div :class="{ passed: !index.stale }"><span>{{ !index.stale ? '✓' : '!' }}</span><div><strong>制度版本一致性</strong><p>{{ !index.stale ? '启用制度指纹与当前索引一致' : '启用制度已变化，需要更新制度索引' }}</p></div></div>
          <div :class="{ passed: index.clause_count === index.active_clause_count }"><span>{{ index.clause_count === index.active_clause_count ? '✓' : '!' }}</span><div><strong>条款数量一致性</strong><p>已发布 {{ index.clause_count }} 条 / 当前启用 {{ index.active_clause_count }} 条</p></div></div>
          <div :class="{ passed: index.status === 'ready' && !index.error }"><span>{{ index.status === 'ready' && !index.error ? '✓' : '!' }}</span><div><strong>向量索引可用性</strong><p>{{ index.error || (index.status === 'ready' ? '当前索引可供员工问答检索' : '索引尚未就绪') }}</p></div></div>
          <div :class="{ passed: Boolean(searchResponse && searchVerdict.passed) }"><span>{{ searchResponse && searchVerdict.passed ? '✓' : '·' }}</span><div><strong>最近检索验证</strong><p v-if="searchResponse">{{ searchVerdict.label }} · {{ searchResponse.question }} · 返回 {{ searchResponse.results.length }} 条</p><p v-else>尚未运行 Top 5 检索质量验证</p></div></div>
        </div>
        <el-empty v-else description="索引健康数据暂不可用" />
      </template>

      <template v-else-if="managementDrawerMode === 'policy' && selectedPolicy">
        <section class="policy-detail-lead"><span>{{ selectedPolicy.category }}</span><h2>{{ selectedPolicy.title }}</h2><p>{{ selectedPolicy.code }} · {{ selectedPolicy.active_version_id ? '已有启用版本' : '暂无启用版本' }} · 共 {{ selectedPolicy.version_count }} 个版本</p></section>
        <nav class="policy-detail-tabs" aria-label="制度详情视图"><button v-for="tab in policyDetailTabs" :key="tab.id" type="button" :class="{ active: policyDetailTab === tab.id }" @click="selectPolicyDetailTab(tab.id)">{{ tab.label }}</button></nav>

        <dl v-if="policyDetailTab === 'overview'" class="management-detail-list"><div><dt>制度名称</dt><dd>{{ selectedPolicy.title }}</dd></div><div><dt>制度编号</dt><dd>{{ selectedPolicy.code }}</dd></div><div><dt>当前版本</dt><dd>{{ selectedPolicyVersion ? `v${selectedPolicyVersion.version}` : '暂无' }}</dd></div><div><dt>生效时间</dt><dd>{{ selectedPolicyVersion?.effective_date || '暂无' }}</dd></div><div><dt>状态</dt><dd>{{ selectedPolicyVersion ? statusLabel(selectedPolicyVersion.status) : '暂无版本' }}</dd></div><div><dt>条款数量</dt><dd>{{ selectedPolicyVersion?.clause_count ?? 0 }}</dd></div><div><dt>员工问答同步状态</dt><dd>{{ selectedPolicyVersion?.status === 'active' && !index?.stale ? '已同步最新制度依据' : '待同步最新制度依据' }}</dd></div></dl>

        <section v-else-if="policyDetailTab === 'versions'" class="policy-version-history"><div v-for="version in selectedPolicy.versions" :key="version.id" class="drawer-version-row"><button type="button" class="policy-data-link" @click="selectPolicyVersion(version)">v{{ version.version }}</button><el-tag size="small" :type="statusTag(version.status)">{{ statusLabel(version.status) }}</el-tag><span>生效 {{ version.effective_date }}</span><span>{{ version.clause_count }} 条</span><el-button size="small" @click="previewVersion(version)">预览</el-button><el-button size="small" plain @click="selectPolicyVersion(version, 'clauses')">查看条款</el-button></div></section>

        <section v-else class="clause-drilldown">
          <div class="version-picker"><span>查看版本</span><button v-for="version in selectedPolicy.versions" :key="version.id" type="button" :class="{ active: selectedPolicyVersion?.id === version.id }" @click="selectPolicyVersion(version, 'clauses')">v{{ version.version }}</button></div>
          <el-skeleton v-if="drilldownLoading" :rows="7" animated />
          <template v-else-if="drilldownReader">
            <div class="clause-directory"><button v-for="clause in drilldownReader.clauses" :key="clause.clause_id" type="button" :class="{ active: selectedClause?.clause_id === clause.clause_id }" @click="openClauseDetail(clause)"><strong>{{ clause.clause_number || '条款' }}</strong><span>{{ clause.section_path }}</span></button></div>
            <article v-if="selectedClause" class="clause-detail-panel"><header><div><span>{{ selectedClause.section_path }}</span><h3>{{ selectedClause.clause_number || '条款详情' }}</h3></div><small v-if="selectedClause.page_number">第 {{ selectedClause.page_number }} 页</small></header><p>{{ selectedClause.text }}</p><el-button type="primary" plain :loading="referenceLoading" @click="loadClauseReferenceDetails">查看问答引用</el-button>
              <section v-if="clauseReferences" class="clause-reference-results"><h4>近期问答引用</h4><p v-if="clauseReferences.total_references">该条款共被 {{ clauseReferences.total_references }} 个回答引用，关联 {{ clauseReferences.question_count }} 个问题。</p><div v-if="clauseReferences.questions.length" class="reference-question-list"><article v-for="item in clauseReferences.questions" :key="item.question"><strong>{{ item.question }}</strong><span>{{ item.reference_count }} 次</span><small>平均检索排名 {{ item.average_rank?.toFixed(1) || '暂无' }} · {{ item.last_referenced_at ? new Date(item.last_referenced_at).toLocaleString() : '暂无时间' }}</small></article></div><el-empty v-else description="当前暂无可靠问答引用记录" :image-size="48" /></section>
            </article>
            <p v-else class="drawer-empty-hint">点击左侧条款查看完整原文与真实问答引用。</p>
          </template>
          <el-empty v-else description="该版本暂无可读取条款" />
        </section>
      </template>
    </div>
  </el-drawer>

  <el-drawer v-model="attentionDrawerVisible" :title="selectedAttention ? `${selectedAttention.category}咨询详情` : '员工关注详情'" size="min(620px, 94vw)" destroy-on-close>
    <div v-if="selectedAttention" class="attention-detail-drawer">
      <section class="drawer-lead"><span class="panel-index">员工关注变化</span><h2>{{ selectedAttention.category }}</h2><p>本周 {{ selectedAttention.current }} 次 · 上周同期 {{ selectedAttention.previous }} 次 · {{ attentionChangeLabel(selectedAttention) }}</p></section>
      <section class="drawer-section"><h3>本周主要咨询</h3><div v-if="selectedAttention.questions.length" class="attention-question-list"><button v-for="item in selectedAttention.questions" :key="item.question" type="button" @click="openAttentionQuestion(item.question, item.count)"><span>{{ item.question }}</span><strong>{{ item.count }} 次</strong></button></div><el-empty v-else description="本周暂无对应问答记录" :image-size="48" /></section>
      <section v-if="selectedAttention.policy_ids.length" class="drawer-section"><h3>关联制度</h3><div class="related-policy-list"><button v-for="policyId in selectedAttention.policy_ids" :key="policyId" type="button" class="briefing-policy-link" @click="openBriefingPolicy(policyId)">{{ findPolicy(policyId)?.title || `制度 #${policyId}` }}</button></div></section>
    </div>
  </el-drawer>

  <el-drawer v-model="questionDrawerVisible" title="问题诊断详情" size="min(620px, 94vw)" destroy-on-close>
    <div v-if="selectedQuestion" class="diagnostic-drawer">
      <section class="drawer-lead"><span>真实问答日志</span><h2>{{ selectedQuestion.question }}</h2><p>累计出现 {{ selectedQuestion.count }} 次，最近一次状态为 {{ selectedQuestion.latest_status || '未知' }}。</p></section>
      <div class="diagnostic-stat-grid"><div><span>平均 Top 分数</span><strong>{{ selectedQuestion.average_top_score?.toFixed(3) || '—' }}</strong></div><div><span>检索耗时</span><strong>{{ selectedQuestion.average_retrieval_latency_ms ? `${Math.round(selectedQuestion.average_retrieval_latency_ms)} ms` : '—' }}</strong></div><div><span>总响应耗时</span><strong>{{ selectedQuestion.average_total_latency_ms ? `${Math.round(selectedQuestion.average_total_latency_ms)} ms` : '—' }}</strong></div><div><span>关联反馈</span><strong>{{ selectedQuestion.feedback_count }}</strong></div></div>
      <section class="drawer-section"><h3>状态分布</h3><div class="status-chip-list"><span v-for="(count, status) in selectedQuestion.status_counts" :key="status">{{ status }} · {{ count }}</span></div></section>
      <section class="drawer-section"><h3>命中制度</h3><div v-if="selectedQuestion.policies.length" class="related-policy-list"><span v-for="policy in selectedQuestion.policies" :key="policy.policy_id">{{ policy.policy_title }}</span></div><p v-else class="muted-copy">暂无命中制度，这通常意味着知识覆盖不足或问题条件仍不完整。</p></section>
      <section class="drawer-section"><h3>最近回答</h3><p>{{ selectedQuestion.latest_answer || '本问题尚无可展示的回答内容。' }}</p></section>
      <section v-if="selectedQuestion.ever_missed" class="drawer-action-panel"><div><strong>曾未找到制度依据</strong><p>{{ selectedQuestion.reason || '建议核验制度覆盖范围和员工问答使用的制度知识。' }}</p></div><el-button type="primary" @click="createIssueFromQuestion(selectedQuestion)">创建制度问题</el-button></section>
    </div>
  </el-drawer>

  <el-drawer v-model="issueDrawerVisible" title="制度问题详情" size="min(680px, 96vw)" destroy-on-close>
    <div v-if="selectedPolicyIssue" class="diagnostic-drawer issue-detail-drawer">
      <section class="drawer-lead"><div class="drawer-tag-row"><el-tag :type="gapSeverityType(selectedPolicyIssue.severity)">{{ gapSeverityLabel(selectedPolicyIssue.severity) }}风险</el-tag><el-tag effect="plain">{{ gapCategoryLabel(selectedPolicyIssue.category) }}</el-tag><el-tag :type="selectedPolicyIssue.status === 'resolved' ? 'success' : selectedPolicyIssue.status === 'processing' ? 'primary' : 'warning'">{{ issueStatusLabels[selectedPolicyIssue.status] }}</el-tag></div><h2>{{ selectedPolicyIssue.title }}</h2><p>{{ selectedPolicyIssue.description }}</p></section>
      <section class="drawer-section"><h3>问题来源</h3><div class="status-chip-list"><span v-for="source in selectedPolicyIssue.sources" :key="source">{{ sourceLabels[source] }}</span></div><small>首次发现 {{ new Date(selectedPolicyIssue.created_at).toLocaleString() }} · 最近出现 {{ new Date(selectedPolicyIssue.last_seen_at).toLocaleString() }}</small></section>
      <section v-if="selectedPolicyIssue.origin_question" class="drawer-section"><h3>待复测原问题</h3><p>{{ selectedPolicyIssue.origin_question }}</p></section>
      <section class="drawer-section"><h3>建议治理动作</h3><p>{{ selectedPolicyIssue.suggested_action }}</p></section>
      <section class="drawer-section"><h3>发现依据（{{ selectedPolicyIssue.evidence.length }}）</h3><div v-if="selectedPolicyIssue.evidence.length" class="gap-evidence-list"><article v-for="(evidence, index) in selectedPolicyIssue.evidence" :key="index" class="gap-evidence-card"><h4>{{ evidenceTitle(evidence) }}</h4><dl><div v-for="field in evidenceFields(evidence)" :key="field.label"><dt>{{ field.label }}</dt><dd>{{ field.value }}</dd></div></dl><div v-if="evidenceClauses(evidence).length" class="gap-evidence-clauses"><strong>关联条款</strong><p v-for="(clause, clauseIndex) in evidenceClauses(evidence)" :key="clauseIndex">{{ clause }}</p></div></article></div><p v-else class="muted-copy">暂无结构化依据。</p></section>
      <section v-if="selectedPolicyIssue.last_retest && 'passed' in selectedPolicyIssue.last_retest" class="drawer-section retest-result" :class="{ passed: selectedPolicyIssue.last_retest.passed }"><h3>最近复测：{{ selectedPolicyIssue.last_retest.passed ? '通过' : '未通过' }}</h3><p>{{ selectedPolicyIssue.last_retest.current_status }} · Top 分数 {{ selectedPolicyIssue.last_retest.top_score?.toFixed(3) || '—' }}</p><div v-if="selectedPolicyIssue.last_retest.citations.length" class="related-policy-list"><span v-for="citation in selectedPolicyIssue.last_retest.citations" :key="citation.clause_id">{{ citation.policy_title }} · {{ citation.clause_number || citation.section_path }}</span></div></section>
      <section class="drawer-section"><h3>处理说明</h3><el-input v-model="policyIssueNote" type="textarea" :rows="3" maxlength="1000" show-word-limit placeholder="记录核验结论、制度修订或制度知识同步情况" /></section>
      <div class="drawer-sticky-actions"><el-button v-if="selectedPolicyIssue.status === 'pending'" type="primary" @click="handlePolicyIssue('start_processing')">开始处理</el-button><el-button v-if="selectedPolicyIssue.status === 'resolved'" @click="handlePolicyIssue('reopen')">重新打开</el-button><el-button v-if="selectedPolicyIssue.status === 'processing'" @click="handlePolicyIssue('add_note')">保存说明</el-button><el-button v-if="selectedPolicyIssue.origin_question" type="warning" plain @click="runPolicyIssueRetest">复测原问题</el-button><el-button v-if="selectedPolicyIssue.status === 'processing'" type="success" @click="handlePolicyIssue('resolve')">标记已解决</el-button></div>
    </div>
  </el-drawer>

  <el-dialog v-model="uploadDialogVisible" title="上传制度版本" width="min(560px, 92vw)" destroy-on-close>
    <el-form label-position="top">
      <div class="form-grid"><el-form-item label="制度编号"><el-input v-model="uploadForm.code" placeholder="如 LEAVE-001" /></el-form-item><el-form-item label="版本号"><el-input v-model="uploadForm.version" placeholder="如 2.0" /></el-form-item></div>
      <el-form-item label="制度标题"><el-input v-model="uploadForm.title" placeholder="制度中文名称" /></el-form-item>
      <div class="form-grid"><el-form-item label="分类"><el-select v-model="uploadForm.category" placeholder="选择分类"><el-option v-for="item in ['考勤', '休假', '薪酬福利', '差旅', '员工关系']" :key="item" :label="item" :value="item" /></el-select></el-form-item><el-form-item label="生效日期"><input v-model="uploadForm.effective_date" class="native-input" type="date" /></el-form-item></div>
      <el-form-item label="制度文件"><label class="file-picker"><input type="file" accept=".md,.txt,.pdf,.docx" @change="selectFile" /><span>{{ uploadForm.file?.name || '选择 Markdown、TXT、PDF 或 DOCX（最大 10 MB）' }}</span></label></el-form-item>
    </el-form>
    <template #footer><el-button @click="uploadDialogVisible = false">取消</el-button><el-button type="primary" :loading="uploadLoading" @click="submitUpload">解析并保存草稿</el-button></template>
  </el-dialog>

  <el-dialog v-model="previewVisible" :title="previewReader?.policy_title || '制度预览'" width="min(850px, 94vw)">
    <div v-if="previewReader" class="preview-meta">{{ previewReader.policy_code }} · v{{ previewReader.policy_version }} · {{ previewReader.effective_date }} · {{ previewReader.clauses.length }} 条</div>
    <div v-if="previewReader" class="preview-clauses"><article v-for="clause in previewReader.clauses" :key="clause.stable_anchor"><strong>{{ clause.section_path }} / {{ clause.clause_number || '条款' }}</strong><p>{{ clause.text }}</p></article></div>
  </el-dialog>

  <el-dialog v-model="searchDetailsVisible" title="Top 5 检索诊断详情" width="min(1080px, 96vw)">
    <div v-if="searchResponse" class="search-details-dialog">
      <div class="card-heading"><div><span class="panel-index">检索验证</span><h2>{{ searchVerdict.label }}</h2><p>问题：{{ searchResponse.question }}</p></div><el-tag :type="searchVerdict.passed ? 'success' : 'danger'" effect="dark">Top {{ searchResponse.results.length }}</el-tag></div>
      <el-table :data="searchResponse.results" stripe table-layout="fixed">
        <el-table-column prop="rank" label="#" width="52" />
        <el-table-column label="制度条款" min-width="220"><template #default="scope"><strong>{{ scope.row.policy_title }}</strong><br /><small>{{ scope.row.clause_number || scope.row.section_path }}</small></template></el-table-column>
        <el-table-column prop="text" label="命中原文" min-width="360" show-overflow-tooltip />
        <el-table-column label="向量" width="96"><template #default="scope">{{ scope.row.vector_score.toFixed(3) }}<small class="rank-detail">#{{ scope.row.vector_rank }}</small></template></el-table-column>
        <el-table-column label="BM25" width="96"><template #default="scope">{{ scope.row.bm25_score.toFixed(3) }}<small class="rank-detail">#{{ scope.row.bm25_rank }}</small></template></el-table-column>
        <el-table-column label="RRF" width="100"><template #default="scope">{{ scope.row.rrf_score.toFixed(5) }}</template></el-table-column>
      </el-table>
    </div>
  </el-dialog>
</template>
